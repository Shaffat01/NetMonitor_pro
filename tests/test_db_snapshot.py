import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from db_snapshot import snapshot


class SnapshotTest(unittest.TestCase):
    def test_wal_backup_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'nodes.db'
            target = Path(tmp) / 'backup.db'
            with closing(sqlite3.connect(source)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE nodes (id INTEGER)')
                db.execute('INSERT INTO nodes VALUES (42)')
                db.commit()
                snapshot(source, target)
                with self.assertRaises(FileExistsError):
                    snapshot(source, target)
                with closing(sqlite3.connect(target)) as restored:
                    self.assertEqual(restored.execute('SELECT id FROM nodes').fetchall(), [(42,)])
