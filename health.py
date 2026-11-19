"""Pure monitoring decisions, independent of Flask, ICMP and the database."""


def next_status(status, outcome, failures, successes, *, fail=3, recover=2, warn=3):
    if outcome == 'failure' and failures >= fail:
        return 'Node Down'
    if outcome == 'healthy' and successes >= recover:
        return 'Node Up'
    if outcome == 'degraded' and successes >= warn and status != 'Node Down':
        return 'Warning'
    return status


def is_stale(enabled, last_checked, now, max_age):
    return bool(enabled and (last_checked is None or
                             (now - last_checked).total_seconds() >= max_age))
