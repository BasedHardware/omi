"""The daily summary is a PERSISTED document, so its creation must not depend on push deliverability.

`send_daily_summary_notification` built its fan-out as "eligible users that have a deliverable
recipient", and the per-user path both CREATES the summary (daily_summaries_db.create_daily_summary) and
delivers it. So a user with no recipient never got a summary generated at all — and
`/v1/users/daily-summaries`, which the app reads, stayed empty for them.

Two ways to have no recipient, and on-prem both are ordinary:
  * PUSH_NOTIFICATION_BACKEND=disabled — a first-class option (ADR-0011), and `_recipients_by_uid` had no
    branch for it, so it fell through to a full FCM-token read that returns nothing;
  * any backend, user simply has no token registered (push off in the OS, web-only user).

Delivery for those users is already a safe no-op: `_send_to_user` returns 0 on DISABLED and on an empty
token list. Nothing had to change there — only the filter that also gated generation.
"""

from __future__ import annotations

import asyncio

import pytest

from utils.other import notifications as notif
from utils.push.base import DISABLED, FCM, UNIFIEDPUSH


@pytest.fixture
def captured(monkeypatch):
    """Capture the fan-out instead of generating and sending."""
    seen: dict = {'fan_out': None, 'recipient_reads': []}

    async def fake_send_bulk(users, push_backend=None):
        seen['fan_out'] = list(users)
        seen['backend'] = push_backend

    monkeypatch.setattr(notif, '_send_bulk_summary_notification', fake_send_bulk)
    monkeypatch.setattr(notif, '_get_timezones_grouped_by_hour', lambda: {9: ['UTC']})

    async def fake_users(timezones, target_hour):
        return [('u-with', {}, 'UTC'), ('u-without', {}, 'UTC')]

    monkeypatch.setattr(notif, '_get_users_for_daily_summary', fake_users)

    def fake_fcm(users):
        seen['recipient_reads'].append('fcm')
        return {'u-with': ['token-1']}

    def fake_unifiedpush(timezones):
        seen['recipient_reads'].append('unifiedpush')
        return {'u-with': [object()]}

    monkeypatch.setattr(notif.notification_db, 'get_fcm_tokens_for_users', fake_fcm)
    monkeypatch.setattr(notif.notification_db, 'get_unifiedpush_endpoints_by_uid', fake_unifiedpush)
    return seen


def _uids(fan_out):
    return sorted(entry[0] for entry in fan_out)


def test_a_user_without_a_recipient_is_still_summarised_on_fcm(captured, monkeypatch):
    monkeypatch.setattr(notif, 'resolve_push_backend', lambda: FCM)
    asyncio.run(notif.send_daily_summary_notification())
    assert _uids(captured['fan_out']) == ['u-with', 'u-without']


def test_with_push_disabled_every_eligible_user_is_still_summarised(captured, monkeypatch):
    monkeypatch.setattr(notif, 'resolve_push_backend', lambda: DISABLED)
    asyncio.run(notif.send_daily_summary_notification())
    assert _uids(captured['fan_out']) == ['u-with', 'u-without']


def test_with_push_disabled_no_recipient_lookup_happens_at_all(captured, monkeypatch):
    """The other half: an hourly full FCM-token read for a backend that will never deliver."""
    monkeypatch.setattr(notif, 'resolve_push_backend', lambda: DISABLED)
    asyncio.run(notif.send_daily_summary_notification())
    assert captured['recipient_reads'] == []


def test_recipients_still_reach_the_sender_when_they_exist(captured, monkeypatch):
    """Generation for everyone must not cost delivery for anyone."""
    monkeypatch.setattr(notif, 'resolve_push_backend', lambda: UNIFIEDPUSH)
    asyncio.run(notif.send_daily_summary_notification())
    by_uid = {entry[0]: entry[1] for entry in captured['fan_out']}
    assert by_uid['u-with'], 'the deliverable user lost their recipients'
    assert by_uid['u-without'] == [], 'a user with no recipient must carry an empty list, not None'
    assert captured['recipient_reads'] == ['unifiedpush']


def test_an_empty_recipient_list_is_a_safe_no_op_for_delivery():
    """Why the fan-out can safely carry them: _send_to_user already returns 0 for both cases."""
    from utils import notifications as sender

    assert sender._send_to_user('u1', 'tag', tokens=[], push_backend=DISABLED) == 0
    assert sender._send_to_user('u1', 'tag', tokens=[], push_backend='fcm') == 0
