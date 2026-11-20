import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from alerts import dispatch_alerts, queue_alert
from models import AlertDelivery, db


class AlertTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        app = Flask(__name__)
        app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///' + str(Path(folder.name) / 'test.db'),
                          ALERT_CHANNELS={'telegram': ('test', 'test')})
        db.init_app(app)
        context = app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        self.now = datetime(2026, 11, 19)
        self.incident = SimpleNamespace(node_id=1, timestamp=self.now, node_name='Router', ip_address='192.0.2.1')
        self.app = app

    @patch('alerts._send')
    def test_one_down_and_one_recovery_per_incident(self, send):
        with patch('alerts.utcnow', return_value=self.now):
            for event in ('down', 'down', 'recovery', 'recovery'):
                queue_alert(self.incident, event)
            db.session.commit()
            dispatch_alerts()
            dispatch_alerts()
        self.assertEqual(AlertDelivery.query.count(), 2)
        self.assertEqual(send.call_count, 2)
        self.assertTrue(send.call_args_list[0].args[-1].startswith('DOWN:'))
        self.assertTrue(send.call_args_list[1].args[-1].startswith('RECOVERED:'))

    @patch('alerts._send', side_effect=[TimeoutError, None, None])
    def test_recovery_waits_for_down_retry(self, send):
        with patch('alerts.utcnow', return_value=self.now):
            queue_alert(self.incident, 'down')
            queue_alert(self.incident, 'recovery')
            db.session.commit()
            dispatch_alerts()
            self.assertEqual(send.call_count, 1)
            self.assertEqual(AlertDelivery.query.filter_by(event='down').one().attempts, 1)
        with patch('alerts.utcnow', return_value=self.now + timedelta(seconds=30)):
            dispatch_alerts()
        self.assertEqual(send.call_count, 3)
        self.assertEqual(AlertDelivery.query.filter_by(state='sent').count(), 2)

    @patch('alerts._send')
    def test_maintenance_mutes_pending_and_new_alerts(self, send):
        with patch('alerts.utcnow', return_value=self.now):
            queue_alert(self.incident, 'down')
            db.session.commit()
        self.app.config['ALERT_MAINTENANCE_WINDOW'] = (self.now, self.now + timedelta(minutes=5))
        with patch('alerts.utcnow', return_value=self.now):
            queue_alert(self.incident, 'recovery')
            dispatch_alerts()
        with patch('alerts.utcnow', return_value=self.now + timedelta(minutes=5)):
            queue_alert(self.incident, 'recovery')
            dispatch_alerts()
        self.assertEqual(AlertDelivery.query.one().state, 'muted')
        send.assert_not_called()
