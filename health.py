"""Pure monitoring decisions, independent of Flask, ICMP and the database."""


def next_status(status, reachable, failures, successes, *, fail=3, recover=2):
    if not reachable and failures >= fail:
        return 'Node Down'
    if reachable and successes >= recover:
        return 'Node Up'
    return status


def is_stale(enabled, last_checked, now, max_age):
    return bool(enabled and (last_checked is None or
                             (now - last_checked).total_seconds() >= max_age))
