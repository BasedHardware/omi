"""Authoritative channel request clocks and observed reminder confirmations."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Provider clocks are not our processing clock. Five minutes matches the Linq
# webhook replay window; a day covers a delayed Telegram retry without letting
# an ancient or far-future stamp schedule a reminder at the wrong time.
FUTURE_SKEW = timedelta(minutes=5)
OLDEST_REQUEST = timedelta(days=1)


def parse_provider_instant(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Invalid provider time')
    text = value.strip().replace('Z', '+00:00')
    if '.' in text:
        head, tail = text.split('.', 1)
        split = next((i for i, char in enumerate(tail) if char in '+-'), len(tail))
        fraction, zone = tail[:split], tail[split:]
        digits = ''.join(char for char in fraction if char.isdigit())[:6] or '0'
        text = head + '.' + digits + zone
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        raise ValueError('Provider time must be timezone aware')
    return stamp.astimezone(timezone.utc)


def bound_provider_clock(stamp, *, now=None):
    now = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError('Provider time must be timezone aware')
    stamp = stamp.astimezone(timezone.utc)
    if stamp > now + FUTURE_SKEW:
        return now
    if stamp < now - OLDEST_REQUEST:
        return now - OLDEST_REQUEST
    return stamp


def channel_evidence(runtime, tz):
    if runtime.request_at is None:
        return list(runtime.evidence)
    local = runtime.request_at.astimezone(ZoneInfo(tz or 'UTC'))
    return [
        {
            'role': 'user',
            'content': (
                'Server-verified request clock: '
                + local.isoformat()
                + '. Resolve relative dates and reminder intervals from this original message time, '
                'not the worker processing time. For "in N minutes", use create_action_item_tool '
                'with due_in_minutes=N. If the original due time has passed, report the delay; never shift it forward.'
            ),
        },
        *runtime.evidence,
    ]


def phone_reminder_confirmation(due, tz, state):
    local = due.astimezone(ZoneInfo(tz or 'UTC'))
    stamp = local.strftime('%I:%M %p').lstrip('0') + ' on ' + local.strftime('%b %d')
    if state == 'requested':
        return "I'll remind you at " + stamp + ' on your phone through Omi.'
    if state == 'late':
        return (
            'The original reminder time ('
            + stamp
            + ') passed while this request waited. No phone reminder was scheduled.'
        )
    return 'The task was saved for ' + stamp + ', but the phone reminder could not be scheduled.'
