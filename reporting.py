"""Bounded hourly probe rollups and NOC reporting (SQLite)."""
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert

from models import DowntimeLog, Node, ProbeHour, db


def hour_floor(stamp):
    return stamp.replace(minute=0, second=0, microsecond=0)


def record_probe(node_id, stamp, reachable, loss, rtt):
    table = ProbeHour.__table__
    stmt = insert(table).values(node_id=node_id, hour=hour_floor(stamp), checks=1,
                                replies=int(reachable), loss_sum=loss, rtt_sum=rtt if reachable else 0)
    db.session.execute(stmt.on_conflict_do_update(index_elements=['node_id', 'hour'], set_={
        name: table.c[name] + stmt.excluded[name]
        for name in ('checks', 'replies', 'loss_sum', 'rtt_sum')
    }))


def prune_probes(now):
    ProbeHour.query.filter(ProbeHour.hour < hour_floor(now) - timedelta(days=8)).delete(synchronize_session=False)


def remove_probes(node_id):
    ProbeHour.query.filter_by(node_id=node_id).delete(synchronize_session=False)


def report_start(now, hours):
    return hour_floor(now) - timedelta(hours=hours - 1)


def percentage(count, total):
    return round(100 * count / total, 2) if total else None


def downtime_seconds(intervals, start, end):
    """Clip incidents to the report window; never double-count overlap."""
    total = 0
    cursor = start
    for left, right in sorted(intervals):
        left, right = max(left, cursor), min(right, end)
        if right > left:
            total += (right - left).total_seconds()
            cursor = right
    return int(total)


def build_report(now, site=None):
    start24, start7 = report_start(now, 24), report_start(now, 168)
    query = Node.query
    if site is not None:
        query = query.filter(Node.site == site)
    nodes = query.order_by(Node.site, Node.node_name).all()
    base = (db.session.query(ProbeHour).join(Node, ProbeHour.node_id == Node.id)
            .filter(ProbeHour.hour >= start7, ProbeHour.hour <= hour_floor(now)))
    if site is not None:
        base = base.filter(Node.site == site)
    def summaries(start):
        rows = (base.filter(ProbeHour.hour >= start).with_entities(
            ProbeHour.node_id, func.sum(ProbeHour.replies), func.sum(ProbeHour.checks))
            .group_by(ProbeHour.node_id))
        return {node_id: (percentage(replies, checks), checks) for node_id, replies, checks in rows}
    stats24, stats7 = summaries(start24), summaries(start7)
    trend_rows = base.with_entities(ProbeHour.hour, func.sum(ProbeHour.replies), func.sum(ProbeHour.checks),
                                    func.sum(ProbeHour.rtt_sum), func.sum(ProbeHour.loss_sum)).group_by(ProbeHour.hour)
    trend_map = {hour: (round(rtt / replies, 1) if replies else None, round(loss / checks, 1), checks)
                 for hour, replies, checks, rtt, loss in trend_rows}
    trend = [(start7 + timedelta(hours=i), *trend_map.get(start7 + timedelta(hours=i), (None, None, 0)))
             for i in range(168)]
    incidents = defaultdict(list)
    logs = (DowntimeLog.query.join(Node, (Node.id == DowntimeLog.node_id) & (Node.ip_address == DowntimeLog.ip_address))
            .filter(DowntimeLog.status_change == 'Node Down', DowntimeLog.timestamp < now))
    if site is not None:
        logs = logs.filter(Node.site == site)
    for log in logs.yield_per(500):
        if log.downtime_duration is not None:
            end = log.timestamp + timedelta(seconds=log.downtime_duration)
        elif not log.is_resolved:
            end = now
        else:
            continue
        if end > start7:
            incidents[log.node_id].append((log.timestamp, end))
    groups = defaultdict(list)
    rankings = []
    for node in nodes:
        down = downtime_seconds(incidents[node.id], start7, now)
        row = (node, stats24.get(node.id, (None, 0)), stats7.get(node.id, (None, 0)), down)
        groups[node.site].append(row)
        if down:
            rankings.append(row)
    rankings.sort(key=lambda row: row[3], reverse=True)
    return groups, trend, rankings[:10]


def trend_points(trend, column, ceiling):
    """SVG points, split at missing observations so outages in telemetry show gaps."""
    segments = []
    segment = []
    for index, row in enumerate(trend):
        value = row[column]
        if value is None:
            if segment:
                segments.append(segment)
                segment = []
            continue
        x = 8 + 584 * index / max(1, len(trend) - 1)
        y = 112 - 104 * value / ceiling
        segment.append((round(x, 2), round(y, 2)))
    if segment:
        segments.append(segment)
    return segments
