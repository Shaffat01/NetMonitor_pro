# NetMonitor Pro

Flask dashboard for ICMP reachability, latency, packet loss and downtime history.

## Windows (local)

Use Python 3.11. In PowerShell, from the repository directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The launcher may request administrator privileges for ICMP. Open
`http://localhost:3000`. Desktop notifications run on the monitoring host.

## Docker / Linux

```sh
docker compose up --build -d
docker compose logs -f netmonitor
```

Open `http://localhost:3000` on the host. Keep one Gunicorn worker because the
polling scheduler runs inside it. The default SQLite database is `data/nodes.db`
on the host (`/app/data/nodes.db` in Docker). Keep `./data` across rebuilds.
`DATABASE_URL` overrides the default; the checked-in root `nodes.db` is **not**
the default active database. Do not overwrite an existing database to migrate it.

## Shared LAN access (HTTPS)

Windows and Compose bind to loopback by default. To share the app, keep that
binding and configure an HTTPS reverse proxy on the host to forward to
`http://127.0.0.1:3000`. Apply login rate limits at the proxy. Do not expose
port 3000 directly or allow unauthenticated access from the LAN.

Set `NETMON_AUTH=1`, a random `SECRET_KEY`, and both `NETMON_ADMIN_HASH` and
`NETMON_VIEWER_HASH` in the process environment (or in a local `.env` file for
Compose). Generate the secret and each password hash locally:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass()))"
```

Use distinct strong passwords. In a Compose `.env` file, single-quote password
hashes so their `$` characters stay literal. Keep the environment file out of Git.
Sign in at the HTTPS URL as `admin` (manage nodes, trigger checks, clear logs)
or `viewer` (read-only dashboard and logs). Login cookies require HTTPS. Rotate
`SECRET_KEY` if you need to invalidate existing sessions.

## Backup and restore (SQLite)

From the host, use Python 3 with the active SQLite path. The backup uses SQLite's
online backup API, so committed WAL data is included without copying sidecar files:

```sh
python db_snapshot.py data/nodes.db nodes-backup.db
```

To restore, **stop the app first** (`docker compose stop` on Docker; exit the
process on Windows), then move the current database and any matching `-wal` and
`-shm` files together to a safe directory. Restore into the now-empty path:

```sh
python db_snapshot.py nodes-backup.db data/nodes.db
```

Restart after verifying the path and file permissions. Keep backups outside Git.
The command refuses to overwrite existing files.

## Monitoring freshness and tests

A probe error does not count as a failed node ping or update `Last checked`.
Enabled nodes with no successful measurement (including measured packet loss)
show `Stale` once their last measurement is missing or 45 seconds old by default.
Override the age with `STALE_AFTER_SECONDS` if needed. Stale and disabled nodes
are excluded from the current up/down/warning counts.

Run isolated tests without starting the scheduler or using the live database:

```sh
python -m unittest discover -s tests -v
```

## DOWN and recovery notifications

Windows desktop notifications continue to work without remote settings. To add
remote delivery, set either or both of these groups in the process environment
(or Compose `.env`) and restart the monitor:

| Channel | Settings |
| --- | --- |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (the bot must be able to post in that chat) |
| Email | `SMTP_HOST`, `SMTP_FROM`, `SMTP_TO`, optional `SMTP_PORT` (587 by default, STARTTLS; 465 uses implicit TLS), and `SMTP_USERNAME` / `SMTP_PASSWORD` if required |

The monitoring host needs outbound access to the selected provider. Keep tokens
and passwords out of Git. Remote alerts are only for confirmed DOWN incidents
and their recovery. Repeated polls do not enqueue duplicate deliveries. The
SQLite outbox survives restarts, and the single scheduler worker retries failed
deliveries up to five total attempts. A provider timeout after accepting a
message, or a crash before the worker records success, can still cause a duplicate.
Clearing downtime logs during an active outage can prevent its recovery alert.

For one global maintenance window, set both `MAINTENANCE_START` and
`MAINTENANCE_END` to ISO 8601 timestamps with an explicit offset, for example
`2026-11-20T01:00:00+06:00` and `2026-11-20T02:00:00+06:00`. Restart with these
settings before the window begins. The start is inclusive and the end exclusive.
Monitoring and logging continue; desktop alerts and new remote alerts are
muted. Pending remote deliveries present when the worker runs during the
window are discarded, not sent when the window ends. A muted DOWN is not
backfilled, and does not produce a standalone remote recovery notice.

## NOC reports

Open **NOC Reports** in the toolbar. Assign a **Site / Branch** on a node's
Add/Edit form or use the optional `site` (or `branch`) CSV column. Older nodes
appear under **Unassigned** until edited. Restarting after the update adds the
site column and creates the reporting table automatically; back up first.

- **24-hour / 7-day uptime:** percentage of measured probes with a reply, with
  sample counts. These are 24 or 168 UTC hourly buckets, including the current
  partial hour, not a time-based SLA. Missing probes and monitor errors do not
  count as successful or failed checks. No measurements display as **N/A**.
- **Trends:** average latency of probes with replies and average packet loss of
  all measured probes, grouped by UTC hour for the selected site(s). Gaps mean
  missing data. History begins after the update; hourly rollups are retained
  for approximately eight days.
- **Top downtime:** confirmed DOWN incidents from the downtime log, clipped to
  the selected seven-day report window. Open incidents count through the report
  time. Clearing logs removes their contribution to this ranking.

## Synthetic performance benchmark

Run from the repository with the Python dependencies installed:

```sh
python benchmark_monitor.py --nodes 300 --viewers 5 --ticks 10 --scenario healthy
python benchmark_monitor.py --nodes 300 --viewers 5 --ticks 10 --scenario timeout
```

The script uses temporary SQLite data, simulated probe results and Flask's
in-process HTTP test client. It sends no pings or alerts. `timeout` simulates
50% nonreplying nodes. It measures polling and persistence through the actual
fallback worker pool, including concurrent dashboard API reads, but does not
measure OS ping subprocess startup, live network latency or browser rendering.
Results are JSON on stdout; app diagnostics are on stderr. Defaults model a
15-second polling cadence and a five-second dashboard refresh interval. Check
cycle p95/max, skipped ticks, peak stale count and each API's p95. Use longer
runs and verify live polling on the deployment host before setting capacity
expectations. For a quick overload test, use `--interval 1 --scenario timeout`.

### Reachability status

Live health uses UP/DOWN only: any reply counts as reachable, even with partial
packet loss. Three consecutive no-reply checks confirm DOWN; two consecutive
checks with replies confirm UP. Packet loss and latency remain visible. On the
first startup after upgrading, prior Warning nodes are reset for rechecking;
existing downtime log entries are preserved. Stale and Disabled are shown
separately so missing data is not mistaken for an outage.
