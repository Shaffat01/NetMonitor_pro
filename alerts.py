"""Persistent notification outbox. Delivery runs outside the polling job."""
import json
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.request import Request, urlopen

from flask import current_app

from models import AlertDelivery, db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def configure_alerts(app):
    env = os.environ.get
    token, chat = env('TELEGRAM_BOT_TOKEN'), env('TELEGRAM_CHAT_ID')
    host, sender, recipient = (env(k) for k in ('SMTP_HOST', 'SMTP_FROM', 'SMTP_TO'))
    username, password = env('SMTP_USERNAME'), env('SMTP_PASSWORD')
    if any((token, chat)) and not (token and chat and re.fullmatch(r'\d+:[\w-]+', token, re.ASCII)):
        raise ValueError('Configure a valid Telegram bot token and chat ID together')
    if any((host, sender, recipient, username, password)) and not (host and sender and recipient and bool(username) == bool(password)):
        raise ValueError('Configure SMTP_HOST, SMTP_FROM and SMTP_TO, plus both login fields if required')
    start, end = (env(k) for k in ('MAINTENANCE_START', 'MAINTENANCE_END'))
    window = None
    if start or end:
        try:
            def parse(value):
                stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    raise ValueError
                return stamp.astimezone(timezone.utc).replace(tzinfo=None)
            window = (parse(start), parse(end))
            if window[0] >= window[1]:
                raise ValueError
        except (AttributeError, ValueError):
            raise ValueError('Maintenance requires ordered start/end timestamps with timezone offsets') from None
    channels = {}
    if token:
        channels['telegram'] = (token, chat)
    if host:
        channels['email'] = (host, int(env('SMTP_PORT') or 587), sender, recipient, username, password)
    app.config.update(ALERT_CHANNELS=channels, ALERT_MAINTENANCE_WINDOW=window)


def muted(now):
    window = current_app.config.get('ALERT_MAINTENANCE_WINDOW')
    return bool(window and window[0] <= now < window[1])


def queue_alert(incident, event):
    """Stage a delivery in the same transaction as the downtime change."""
    channels = current_app.config.get('ALERT_CHANNELS', {})
    now = utcnow()
    if not channels or muted(now):
        return
    key = f'{incident.node_id}:{incident.timestamp.isoformat()}'
    headline = 'DOWN' if event == 'down' else 'RECOVERED'
    message = f'{headline}: {incident.node_name} ({incident.ip_address})\nIncident started: {incident.timestamp.isoformat(timespec="seconds")}Z'
    for channel in channels:
        if event == 'recovery':
            down = AlertDelivery.query.filter_by(incident=key, event='down', channel=channel).first()
            if not down or down.state not in ('pending', 'sent'):
                continue
        if AlertDelivery.query.filter_by(incident=key, event=event, channel=channel).first() is None:
            db.session.add(AlertDelivery(incident=key, event=event, channel=channel,
                                         message=message, next_attempt=now))


def _send(channel, config, message):
    if channel == 'telegram':
        token, chat = config
        data = json.dumps({'chat_id': chat, 'text': message}).encode()
        request = Request(f'https://api.telegram.org/bot{token}/sendMessage', data,
                          {'Content-Type': 'application/json'})
        with urlopen(request, timeout=8) as response:
            if not json.load(response).get('ok'):
                raise RuntimeError('Telegram rejected the notification')
    else:
        host, port, sender, recipient, username, password = config
        mail = EmailMessage()
        mail['Subject'] = 'NetMonitor Pro network alert'
        mail['From'], mail['To'] = sender, recipient
        mail.set_content(message)
        context = ssl.create_default_context()
        conn = smtplib.SMTP_SSL(host, port, timeout=8, context=context) if port == 465 else smtplib.SMTP(host, port, timeout=8)
        with conn as smtp:
            if port != 465:
                smtp.starttls(context=context)
            if username:
                smtp.login(username, password)
            smtp.send_message(mail)


def dispatch_alerts():
    """One scheduler worker sends queued notices, retrying transient failures."""
    channels = current_app.config.get('ALERT_CHANNELS', {})
    if not channels:
        return
    now = utcnow()
    if muted(now):
        # Never release deferred messages later if they were due during maintenance.
        AlertDelivery.query.filter_by(state='pending').update({'state': 'muted'})
        db.session.commit()
        return
    due = AlertDelivery.query.filter(AlertDelivery.state == 'pending',
                                     AlertDelivery.next_attempt <= now).order_by(
                                         AlertDelivery.next_attempt, AlertDelivery.id).limit(20).all()
    for delivery in due:
        if muted(utcnow()):
            break
        if delivery.channel not in channels:
            delivery.state = 'disabled'
        elif delivery.event == 'recovery' and not _ready_recovery(delivery, now):
            pass
        else:
            try:
                _send(delivery.channel, channels[delivery.channel], delivery.message)
                delivery.state = 'sent'
            except Exception as exc:
                delivery.attempts += 1
                delivery.next_attempt = utcnow() + timedelta(seconds=30 * 2 ** (delivery.attempts - 1))
                if delivery.attempts >= 5:
                    delivery.state = 'failed'
                # Raw provider exceptions can contain credentials or recipient addresses.
                current_app.logger.warning('Alert #%s delivery failed (%s, attempt %s): %s',
                                           delivery.id, delivery.channel, delivery.attempts, type(exc).__name__)
        db.session.commit()


def _ready_recovery(delivery, now):
    down = AlertDelivery.query.filter_by(incident=delivery.incident, event='down', channel=delivery.channel).first()
    if down and down.state == 'sent':
        return True
    if down and down.state == 'pending':
        delivery.next_attempt = max(down.next_attempt, now + timedelta(seconds=15))
    else:
        delivery.state = 'suppressed'
    return False
