"""Run a no-network monitoring benchmark against an isolated temporary database."""
import argparse
import ipaddress
import json
import math
import os
import tempfile
import sys
from contextlib import redirect_stdout
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * fraction) - 1] if ordered else None


def run(args):
    with tempfile.TemporaryDirectory(prefix='netmonitor-benchmark-') as temp:
        env = {key: '' for key in ('NETMON_AUTH', 'NETMON_ADMIN_HASH', 'NETMON_VIEWER_HASH',
                                   'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'SMTP_HOST',
                                   'SMTP_FROM', 'SMTP_TO', 'SMTP_USERNAME', 'SMTP_PASSWORD',
                                   'MAINTENANCE_START', 'MAINTENANCE_END')}
        env.update(DATABASE_URL='sqlite:///' + (Path(temp) / 'benchmark.db').as_posix(),
                   NETMON_DISABLE_BACKGROUND='1', STALE_AFTER_SECONDS=str(args.stale_seconds))
        with patch.dict(os.environ, env):
            from app import app, monitor
            from models import Node, db
            from config import Config
            app.testing = True
            monitor.app = app
            # Exercise the existing fallback thread pool without starting any ping processes.
            monitor._use_system_ping = True
            first = ipaddress.IPv4Address('198.18.0.1')
            with app.app_context():
                engine = db.engine
                db.session.add_all([Node(node_name=f'Bench {i + 1}', ip_address=str(first + i),
                                         site=f'Site {i % 10}', status='Node Up')
                                    for i in range(args.nodes)])
                db.session.commit()
            stop = threading.Event()

            def reader():
                timings = {'nodes': [], 'stats': []}
                stale_peak = 0
                with app.test_client() as client:
                    while not stop.is_set():
                        for route in timings:
                            start = time.perf_counter()
                            response = client.get('/api/' + route)
                            if response.status_code != 200:
                                raise RuntimeError(f'{route}: HTTP {response.status_code}')
                            timings[route].append(1000 * (time.perf_counter() - start))
                            if route == 'stats':
                                stale_peak = max(stale_peak, response.get_json()['stale'])
                        stop.wait(args.dashboard_interval)
                return timings, stale_peak

            def probe(address, count=2, timeout=1):
                unresponsive = args.scenario == 'timeout' and (int(ipaddress.IPv4Address(address)) - int(first)) % 2 == 0
                time.sleep(args.timeout_delay if unresponsive else args.healthy_delay)
                return {'address': address, 'is_alive': not unresponsive,
                        'avg_rtt': 0.0 if unresponsive else 4.0, 'packet_loss': float(unresponsive)}

            def cycle():
                started = time.perf_counter()
                monitor.monitor_all_nodes()
                return time.perf_counter() - started

            try:
                with patch.object(monitor, '_system_ping', side_effect=probe), \
                     patch('monitor.notify_node_down'), patch('monitor.notify_node_up'), patch('monitor.notify_warning'):
                    cycle()  # warm up and populate last_checked outside measured cycles
                    with ThreadPoolExecutor(max_workers=args.viewers + 1) as pool:
                        readers = [pool.submit(reader) for _ in range(args.viewers)]
                        active = None
                        cycles, skipped = [], 0
                        start = time.perf_counter()
                        try:
                            for tick in range(args.ticks):
                                delay = start + tick * (args.interval or Config.PING_INTERVAL) - time.perf_counter()
                                if delay > 0:
                                    time.sleep(delay)
                                if active and not active.done():
                                    skipped += 1
                                    continue
                                if active:
                                    cycles.append(active.result())
                                active = pool.submit(cycle)
                            if active:
                                cycles.append(active.result())
                        finally:
                            stop.set()
                        results = [r.result() for r in readers]
                with app.test_client() as client:
                    final = client.get('/api/stats').get_json()
                expected_down = (args.nodes + 1) // 2 if args.scenario == 'timeout' and len(cycles) + 1 >= Config.FAIL_THRESHOLD else 0
                if final['total'] != args.nodes or (not final['stale'] and final['down'] != expected_down):
                    raise RuntimeError(f'Unexpected final monitoring state: {final}')
                return {'nodes': args.nodes, 'viewers': args.viewers, 'scenario': args.scenario,
                        'scheduled_ticks': args.ticks, 'cycles_completed': len(cycles), 'ticks_skipped': skipped,
                        'poll_interval_s': args.interval or Config.PING_INTERVAL,
                        'cycle_p95_s': percentile(cycles, .95), 'cycle_max_s': max(cycles),
                        'stale_peak': max([final['stale'], *(peak for _, peak in results)]),
                        'final_status': final,
                        'api': {route: {'samples': len(samples), 'p95_ms': percentile(samples, .95)}
                                for route in ('nodes', 'stats')
                                for samples in [[ms for timings, _ in results for ms in timings[route]]]}}
            finally:
                engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nodes', type=int, default=300)
    parser.add_argument('--viewers', type=int, default=5)
    parser.add_argument('--ticks', type=int, default=6)
    parser.add_argument('--scenario', choices=('healthy', 'timeout'), default='healthy')
    parser.add_argument('--interval', type=float, help='Override the simulated scheduler cadence (seconds)')
    parser.add_argument('--dashboard-interval', type=float, default=5)
    parser.add_argument('--stale-seconds', type=float, default=45)
    parser.add_argument('--healthy-delay', type=float, default=.02)
    parser.add_argument('--timeout-delay', type=float, default=2.2)
    args = parser.parse_args()
    if not (1 <= args.nodes <= 65534 and 0 <= args.viewers <= 50 and args.ticks > 0
            and args.dashboard_interval > 0 and args.stale_seconds >= 1
            and args.healthy_delay >= 0 and args.timeout_delay >= 0
            and (args.interval is None or args.interval > 0)):
        parser.error('Invalid node/viewer count, tick count, interval, or delay')
    args.stale_seconds = int(args.stale_seconds)
    with redirect_stdout(sys.stderr):
        results = run(args)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
