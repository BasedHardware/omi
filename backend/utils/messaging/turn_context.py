"""Authoritative channel request clocks and observed reminder confirmations."""

from zoneinfo import ZoneInfo


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
