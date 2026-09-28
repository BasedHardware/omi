import logging
from datetime import datetime, timezone

import pytest

from utils.notification_dispatch import (
    APP_NOTIFICATION_LIMIT,
    APP_NOTIFICATION_RATE_LIMIT_POLICY,
    APP_NOTIFICATION_WINDOW_SECONDS,
    NotificationDispatchStatus,
    NotificationDispatcher,
    NotificationIntent,
    NotificationPolicy,
)


class _RateLimitReserve:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}
        self.calls: list[tuple[str, str, int, int]] = []

    def __call__(self, key: str, policy: str, limit: int, window: int) -> tuple[bool, int, int]:
        self.calls.append((key, policy, limit, window))
        bucket = (key, policy)
        count = self.counts.get(bucket, 0)
        if count >= limit:
            return False, 0, 177
        count += 1
        self.counts[bucket] = count
        return True, limit - count, 177


def _intent(
    *,
    user_id: str = 'user-1',
    app_id: str = 'calendar',
    policy: NotificationPolicy = NotificationPolicy.EXTERNAL_APP_HOURLY,
) -> NotificationIntent:
    return NotificationIntent.app_integration(
        user_id=user_id,
        app_name='Calendar',
        app_id=app_id,
        message='Your event starts soon',
        source='test',
        policy=policy,
    )


def _noon_utc() -> datetime:
    return datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def test_external_app_policy_delivers_full_quota_then_suppresses() -> None:
    reserve = _RateLimitReserve()
    deliveries: list[tuple[object, ...]] = []
    dispatcher = NotificationDispatcher(
        reserve=reserve, sync_delivery=lambda *args: deliveries.append(args), clock=_noon_utc
    )

    outcomes = [dispatcher.dispatch(_intent()) for _ in range(APP_NOTIFICATION_LIMIT + 1)]

    assert [outcome.status for outcome in outcomes[:APP_NOTIFICATION_LIMIT]] == [
        NotificationDispatchStatus.DISPATCHED
    ] * APP_NOTIFICATION_LIMIT
    assert outcomes[-1].status == NotificationDispatchStatus.SUPPRESSED
    assert len(deliveries) == APP_NOTIFICATION_LIMIT
    assert outcomes[0].rate_limit is not None
    assert outcomes[0].rate_limit.headers() == {
        'X-RateLimit-Limit': str(APP_NOTIFICATION_LIMIT),
        'X-RateLimit-Remaining': str(APP_NOTIFICATION_LIMIT - 1),
        'X-RateLimit-Reset': '177',
    }
    assert outcomes[-1].rate_limit is not None
    assert outcomes[-1].rate_limit.headers()['Retry-After'] == '177'
    assert reserve.calls[0] == (
        'calendar:user-1:2026-08-30-12',
        APP_NOTIFICATION_RATE_LIMIT_POLICY,
        APP_NOTIFICATION_LIMIT,
        APP_NOTIFICATION_WINDOW_SECONDS,
    )


def test_external_app_policy_isolated_by_app_and_user() -> None:
    reserve = _RateLimitReserve()
    deliveries: list[tuple[object, ...]] = []
    dispatcher = NotificationDispatcher(
        reserve=reserve, sync_delivery=lambda *args: deliveries.append(args), clock=_noon_utc
    )

    for _ in range(APP_NOTIFICATION_LIMIT):
        assert dispatcher.dispatch(_intent()).status == NotificationDispatchStatus.DISPATCHED

    assert dispatcher.dispatch(_intent(app_id='tasks')).status == NotificationDispatchStatus.DISPATCHED
    assert dispatcher.dispatch(_intent(user_id='user-2')).status == NotificationDispatchStatus.DISPATCHED
    assert len(deliveries) == APP_NOTIFICATION_LIMIT + 2


def test_external_app_policy_expires_at_next_utc_hour() -> None:
    reserve = _RateLimitReserve()
    dispatcher = NotificationDispatcher(
        reserve=reserve,
        sync_delivery=lambda *_args: None,
        clock=lambda: datetime(2026, 8, 30, 12, 45, tzinfo=timezone.utc),
    )

    dispatcher.dispatch(_intent())

    assert reserve.calls[0] == (
        'calendar:user-1:2026-08-30-12',
        APP_NOTIFICATION_RATE_LIMIT_POLICY,
        APP_NOTIFICATION_LIMIT,
        15 * 60,
    )


def test_internal_app_notification_bypasses_external_quota() -> None:
    reserve = _RateLimitReserve()
    deliveries: list[tuple[object, ...]] = []
    dispatcher = NotificationDispatcher(reserve=reserve, sync_delivery=lambda *args: deliveries.append(args))

    outcome = dispatcher.dispatch(_intent(policy=NotificationPolicy.DIRECT))

    assert outcome.status == NotificationDispatchStatus.DISPATCHED
    assert outcome.rate_limit is None
    assert reserve.calls == []
    assert len(deliveries) == 1


def test_app_intent_preserves_plugin_attribution_and_navigation() -> None:
    intent = NotificationIntent.app_integration(
        user_id='user-1',
        app_name='Calendar',
        app_id='app-123',
        message='Hello',
        target='main',
        source='test',
    )

    assert intent.title == 'Calendar says'
    assert intent.data['plugin_id'] == 'app-123'
    assert intent.data['navigate_to'] == '/chat/omi'
    assert 'app_id' not in intent.data


def test_delivery_failure_is_observable_without_logging_content(caplog: pytest.LogCaptureFixture) -> None:
    def fail(*_args: object) -> None:
        raise RuntimeError('transport unavailable')

    dispatcher = NotificationDispatcher(sync_delivery=fail)
    intent = _intent(policy=NotificationPolicy.DIRECT)

    with caplog.at_level(logging.ERROR):
        outcome = dispatcher.dispatch(intent)

    assert outcome.status == NotificationDispatchStatus.FAILED
    assert outcome.reason == 'delivery_failed'
    assert 'transport unavailable' in caplog.text
    assert intent.body not in caplog.text


@pytest.mark.asyncio
async def test_async_dispatch_uses_async_transport() -> None:
    deliveries: list[tuple[object, ...]] = []

    async def deliver(*args: object) -> None:
        deliveries.append(args)

    dispatcher = NotificationDispatcher(async_delivery=deliver)
    outcome = await dispatcher.dispatch_async(_intent(policy=NotificationPolicy.DIRECT))

    assert outcome.status == NotificationDispatchStatus.DISPATCHED
    assert len(deliveries) == 1
