import unittest
from datetime import datetime, timedelta

from health import is_stale, next_status


class HealthTest(unittest.TestCase):
    def test_fail_and_recover_after_thresholds(self):
        self.assertEqual(next_status('Node Up', 'failure', 2, 0), 'Node Up')
        self.assertEqual(next_status('Node Up', 'failure', 3, 0), 'Node Down')
        self.assertEqual(next_status('Node Down', 'healthy', 0, 1), 'Node Down')
        self.assertEqual(next_status('Node Down', 'healthy', 0, 2), 'Node Up')

    def test_warning_and_recovery(self):
        self.assertEqual(next_status('Node Up', 'degraded', 0, 2), 'Node Up')
        self.assertEqual(next_status('Node Up', 'degraded', 0, 3), 'Warning')
        self.assertEqual(next_status('Warning', 'failure', 2, 0), 'Warning')
        self.assertEqual(next_status('Warning', 'failure', 3, 0), 'Node Down')
        self.assertEqual(next_status('Warning', 'healthy', 0, 2), 'Node Up')
        self.assertEqual(next_status('Node Down', 'degraded', 0, 3), 'Node Down')

    def test_freshness(self):
        now = datetime(2026, 11, 19)
        self.assertTrue(is_stale(True, None, now, 45))
        self.assertFalse(is_stale(False, None, now, 45))
        self.assertFalse(is_stale(True, now - timedelta(seconds=44), now, 45))
        self.assertTrue(is_stale(True, now - timedelta(seconds=45), now, 45))
