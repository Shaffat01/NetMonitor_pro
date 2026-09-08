"""
Windows Desktop Notification Module
Sends real Windows toast notifications with sound when nodes go DOWN/UP (Windows only)
"""
import platform

IS_WINDOWS = platform.system().lower() == 'windows'


def _play_alert_sound():
    """Play Windows system sound for alerts (Down/Warning)."""
    if not IS_WINDOWS:
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception as e:
        print(f"[SOUND ERROR] {e}")


def _play_up_sound():
    """Play Windows system sound for recovery (Up)."""
    if not IS_WINDOWS:
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception as e:
        print(f"[SOUND ERROR] {e}")


def send_windows_notification(title, message, sound_type='alert'):
    """Send a Windows desktop notification safely."""
    if not IS_WINDOWS:
        return

    # 1. Sound
    if sound_type == 'alert':
        _play_alert_sound()
    elif sound_type == 'up':
        _play_up_sound()

    # 2. Toast Notification
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name='NetMonitor Pro',
            timeout=5
        )
    except Exception as e:
        print(f"[WINDOWS NOTIFY ERROR] {e}")


def notify_node_down(node_name, ip_address):
    """Send DOWN notification with alert sound."""
    send_windows_notification(
        title='🔴 Node DOWN - NetMonitor Pro',
        message=f'{node_name} ({ip_address}) is DOWN!',
        sound_type='alert'
    )


def notify_node_up(node_name, ip_address, duration_str=None):
    """Send UP notification with recovery sound."""
    duration_info = f' | Down for: {duration_str}' if duration_str else ''
    send_windows_notification(
        title='🟢 Node UP - NetMonitor Pro',
        message=f'{node_name} ({ip_address}) is back UP!{duration_info}',
        sound_type='up'
    )


def notify_warning(node_name, ip_address):
    """Send Warning notification with sound."""
    send_windows_notification(
        title='🟡 Warning - NetMonitor Pro',
        message=f'{node_name} ({ip_address}) - High packet loss/latency',
        sound_type='alert'
    )
