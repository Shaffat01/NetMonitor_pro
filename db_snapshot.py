"""Copy a SQLite database safely, including committed WAL data."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def snapshot(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        # Exclusive creation prevents overwriting a live database or a backup.
        with destination.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    raise RuntimeError('Snapshot failed SQLite integrity check')
        except BaseException:
            destination.unlink()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination', help='New file; must not already exist')
    args = parser.parse_args()
    snapshot(args.source, args.destination)
