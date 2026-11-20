import unittest
from datetime import datetime, timedelta

from health import is_stale, next_status


class HealthTest(unittest.TestCase):
    def test_fail_and_recover_after_thresholds(self):
        self.assertEqual(next_status('Node Up', False, 2, 0), 'Node Up')
        self.assertEqual(next_status('Node Up', False, 3, 0), 'Node Down')
        self.assertEqual(next_status('Node Down', True, 0, 1), 'Node Down')
        self.assertEqual(next_status('Node Down', True, 0, 2), 'Node Up')

    def test_unconfirmed_node_requires_replies_or_failures(self):
        self.assertEqual(next_status('Unknown', True, 0, 1), 'Unknown')
        self.assertEqual(next_status('Unknown', True, 0, 2), 'Node Up')
        self.assertEqual(next_status('Unknown', False, 2, 0), 'Unknown')
        self.assertEqual(next_status('Unknown', False, 3, 0), 'Node Down')

    def test_freshness(self):
        now = datetime(2026, 11, 19)
        self.assertTrue(is_stale(True, None, now, 45))
        self.assertFalse(is_stale(False, None, now, 45))
        self.assertFalse(is_stale(True, now - timedelta(seconds=44), now, 45))
        self.assertTrue(is_stale(True, now - timedelta(seconds=45), now, 45))
