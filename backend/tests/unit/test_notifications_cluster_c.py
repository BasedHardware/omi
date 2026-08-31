"""cubic review 4939247683 — notifications cluster C regressions.

C1: _send_to_user_async must isolate invalid-token cleanup like the sync path (B5) — a
remove_bulk_tokens failure AFTER a confirmed delivery must not be caught and zero success_count.
C4: the daily-summary fan-out resolves the push backend once and carries it, so send_bulk_notification
does not re-resolve (which would record a config-typo fallback twice).

Reuses the behavioral harness from test_notification_token_cleanup (stub firebase/db, load fresh).
"""

from __future__ import annotations

import asyncio

from tests.unit.test_notification_token_cleanup import (
    _FakeBatchResponse,
    _FakeMessagingException,
    _FakeResponse,
    _loaded_notifications,
)


def test_send_to_user_async_isolates_cleanup_failure_keeps_delivered_count():
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['dead-token', 'live-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('NOT_FOUND')),
                _FakeResponse(success=True),
            ]
        )
        notification_db.remove_bulk_tokens.side_effect = RuntimeError('cleanup boom')

        # 1 delivered; cleanup then raises. Pre-fix the shared try caught it and returned 0.
        count = asyncio.run(notifications._send_to_user_async('user-1', 'tag', data={'k': 'v'}))
        assert count == 1
        notification_db.remove_bulk_tokens.assert_called_once_with(['dead-token'])


def test_send_to_user_async_send_failure_still_returns_zero():
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['t']
        messaging.send_each.side_effect = RuntimeError('send boom')  # the SEND fails
        count = asyncio.run(notifications._send_to_user_async('user-1', 'tag', data={'k': 'v'}))
        assert count == 0  # a genuine send failure still returns 0


def test_send_bulk_notification_carries_backend_without_re_resolving(monkeypatch):
    with _loaded_notifications() as (notifications, _notification_db, _messaging):
        calls = []

        def _spy():
            calls.append(1)
            return 'fcm'

        monkeypatch.setattr(notifications, 'resolve_push_backend', _spy)
        # An explicit push_backend must be used as-is; resolve_push_backend must NOT be called.
        asyncio.run(notifications.send_bulk_notification([], 't', 'b', push_backend='fcm'))
        assert calls == []


def test_send_bulk_notification_unifiedpush_cleanup_failure_does_not_propagate(monkeypatch):
    # UnifiedPush bulk send / dead-endpoint cleanup failure must be caught like the FCM path, not abort
    # the whole notification job (cubic review 4939247683).
    import utils.notifications as notifications
    import utils.push.unifiedpush as up

    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')

    async def _boom(endpoints, message):
        raise RuntimeError('dead endpoint cleanup failed')

    monkeypatch.setattr(up, 'send_bulk', _boom)
    # Must NOT raise despite the cleanup blowing up.
    asyncio.run(notifications.send_bulk_notification(['http://ntfy/x?up=1'], 'title', 'body'))
