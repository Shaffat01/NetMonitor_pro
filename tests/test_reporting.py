import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask

from models import DowntimeLog, Node, db
from reporting import build_report, downtime_seconds, record_probe, trend_points


class ReportingTest(unittest.TestCase):
    def test_downtime_clips_and_merges(self):
        start = datetime(2026, 11, 19)
        minute = timedelta(minutes=1)
        self.assertEqual(downtime_seconds([(start - minute, start + 2 * minute),
                                          (start + minute, start + 4 * minute),
                                          (start + 3 * minute, start + 6 * minute)],
                                         start, start + 5 * minute), 300)

    def test_trend_keeps_missing_hours_as_gaps(self):
        trend = [(None, 10), (None, None), (None, 0)]
        self.assertEqual([len(group) for group in trend_points(trend, 1, 10)], [1, 1])

    def test_rollups_site_filter_and_window(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Flask(__name__)
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + str(Path(folder) / 'report.db')
            db.init_app(app)
            with app.app_context():
                try:
                    db.create_all()
                    router = Node(node_name='Router', ip_address='192.0.2.1', site='Gazipur')
                    other = Node(node_name='Other', ip_address='192.0.2.2', site='Dhaka')
                    db.session.add_all([router, other])
                    db.session.flush()
                    now = datetime(2026, 11, 19, 12, 30)
                    record_probe(router.id, now, True, 50, 20)
                    record_probe(router.id, now, False, 100, 0)
                    record_probe(router.id, now - timedelta(days=2), True, 0, 10)
                    record_probe(other.id, now, True, 0, 999)
                    db.session.add(DowntimeLog(node_id=router.id, node_name=router.node_name,
                                               ip_address=router.ip_address, status_change='Node Down',
                                               timestamp=now - timedelta(minutes=5)))
                    db.session.commit()
                    groups, trend, rankings = build_report(now, 'Gazipur')
                    self.assertEqual(list(groups), ['Gazipur'])
                    self.assertEqual(groups['Gazipur'][0][1:3], ((50.0, 2), (66.67, 3)))
                    self.assertEqual(trend[-1][1:], (20.0, 75.0, 2))
                    self.assertEqual(rankings[0][3], 300)
                    all_groups, _, _ = build_report(now + timedelta(days=9))
                    self.assertEqual(all_groups['Gazipur'][0][1], (None, 0))
                finally:
                    db.session.remove()
                    db.engine.dispose()
