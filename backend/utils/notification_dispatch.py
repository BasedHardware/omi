"""Typed notification intents and the single policy-aware delivery boundary.

This module is intentionally small: ``utils.notifications`` remains the FCM
transport while migrations move producers here one family at a time. Policy
belongs here so a producer cannot accidentally choose a different rate limit
or bypass it by calling another router's helper.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Awaitable, Callable, Mapping, Optional

from models.notification_message import NotificationMessage

logger = logging.getLogger(__name__)

APP_NOTIFICATION_LIMIT = 10
APP_NOTIFICATION_WINDOW_SECONDS = 3600
APP_NOTIFICATION_RATE_LIMIT_POLICY = 'integration-notification'


class NotificationKind(str, Enum):
    APP_INTEGRATION = 'app_integration'


class NotificationPolicy(str, Enum):
    DIRECT = 'direct'
    EXTERNAL_APP_HOURLY = 'external_app_hourly'


class NotificationDispatchStatus(str, Enum):
    DISPATCHED = 'dispatched'
    SUPPRESSED = 'suppressed'
    FAILED = 'failed'


@dataclass(frozen=True)
class NotificationIntent:
    """A producer's delivery request, before policy or transport decisions."""

    user_id: str
    title: str
    body: str
    source: str
    kind: NotificationKind
    policy: NotificationPolicy = NotificationPolicy.DIRECT
    data: Mapping[str, Any] = field(default_factory=dict)
    app_id: Optional[str] = None

    @classmethod
    def app_integration(
        cls,
        *,
        user_id: str,
        app_name: str,
        app_id: str,
        message: str,
        target: str = 'app',
        source: str,
        policy: NotificationPolicy = NotificationPolicy.DIRECT,
    ) -> 'NotificationIntent':
        navigate_to = '/chat/omi' if target == 'main' else f'/chat/{app_id}'
        notification_message = NotificationMessage(
            text=message,
            plugin_id=app_id,
            from_integration='true',
            type='text',
            notification_type='plugin',
            navigate_to=navigate_to,
        )
        return cls(
            user_id=user_id,
            title=f'{app_name} says',
            body=message,
            source=source,
            kind=NotificationKind.APP_INTEGRATION,
            policy=policy,
            data=NotificationMessage.get_message_as_dict(notification_message),
            app_id=app_id,
        )


@dataclass(frozen=True)
class NotificationRateLimit:
    limit: int
    remaining: int
    reset_seconds: int
    retry_after_seconds: int = 0

    def headers(self) -> dict[str, str]:
        headers = {
            'X-RateLimit-Limit': str(self.limit),
            'X-RateLimit-Remaining': str(self.remaining),
            'X-RateLimit-Reset': str(self.reset_seconds),
        }
        if self.retry_after_seconds:
            headers['Retry-After'] = str(self.retry_after_seconds)
        return headers


@dataclass(frozen=True)
class NotificationDispatchOutcome:
    status: NotificationDispatchStatus
    rate_limit: Optional[NotificationRateLimit] = None
    reason: Optional[str] = None


RateLimitReserve = Callable[[str, str, int, int], tuple[bool, int, int]]
SyncDelivery = Callable[[str, str, str, Optional[dict[str, Any]]], None]
AsyncDelivery = Callable[[str, str, str, Optional[dict[str, Any]]], Awaitable[None]]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_reserve(key: str, policy: str, limit: int, window: int) -> tuple[bool, int, int]:
    # Keep Redis lazy for hermetic coordinators that use DIRECT policy only.
    from database.redis_db import reserve_rate_limit

    return reserve_rate_limit(key, policy, limit, window)


def _default_sync_delivery(user_id: str, title: str, body: str, data: Optional[dict[str, Any]]) -> None:
    # Keep the transport import lazy: intent and policy tests do not need Firebase.
    from utils.notifications import send_notification

    send_notification(user_id, title, body, data)


async def _default_async_delivery(user_id: str, title: str, body: str, data: Optional[dict[str, Any]]) -> None:
    from utils.notifications import send_notification_async

    await send_notification_async(user_id, title, body, data)


class NotificationDispatcher:
    """Own notification policy decisions, then delegate accepted intents to FCM."""

    def __init__(
        self,
        *,
        reserve: RateLimitReserve = _default_reserve,
        sync_delivery: SyncDelivery = _default_sync_delivery,
        async_delivery: AsyncDelivery = _default_async_delivery,
        clock: Clock = _utc_now,
    ) -> None:
        self._reserve = reserve
        self._sync_delivery = sync_delivery
        self._async_delivery = async_delivery
        self._clock = clock

    def _apply_policy(self, intent: NotificationIntent) -> Optional[NotificationDispatchOutcome]:
        if intent.policy == NotificationPolicy.DIRECT:
            return None
        if intent.policy != NotificationPolicy.EXTERNAL_APP_HOURLY or not intent.app_id:
            raise ValueError(f'notification policy {intent.policy.value} requires an app_id')

        now = self._clock()
        window_seconds = APP_NOTIFICATION_WINDOW_SECONDS - (int(now.timestamp()) % APP_NOTIFICATION_WINDOW_SECONDS)
        allowed, remaining, reset_seconds = self._reserve(
            f'{intent.app_id}:{intent.user_id}:{now.strftime("%Y-%m-%d-%H")}',
            APP_NOTIFICATION_RATE_LIMIT_POLICY,
            APP_NOTIFICATION_LIMIT,
            window_seconds,
        )
        rate_limit = NotificationRateLimit(
            limit=APP_NOTIFICATION_LIMIT,
            remaining=remaining,
            reset_seconds=reset_seconds,
            retry_after_seconds=0 if allowed else reset_seconds,
        )
        if allowed:
            return NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, rate_limit=rate_limit)

        logger.info(
            'notification suppressed uid=%s kind=%s source=%s reason=rate_limit',
            intent.user_id,
            intent.kind.value,
            intent.source,
        )
        return NotificationDispatchOutcome(
            NotificationDispatchStatus.SUPPRESSED,
            rate_limit=rate_limit,
            reason='rate_limit',
        )

    def dispatch(self, intent: NotificationIntent) -> NotificationDispatchOutcome:
        policy_outcome = self._apply_policy(intent)
        if policy_outcome and policy_outcome.status == NotificationDispatchStatus.SUPPRESSED:
            return policy_outcome

        try:
            self._sync_delivery(intent.user_id, intent.title, intent.body, dict(intent.data))
        except Exception:
            logger.exception(
                'notification delivery failed uid=%s kind=%s source=%s',
                intent.user_id,
                intent.kind.value,
                intent.source,
            )
            return NotificationDispatchOutcome(
                NotificationDispatchStatus.FAILED,
                rate_limit=policy_outcome.rate_limit if policy_outcome else None,
                reason='delivery_failed',
            )

        logger.info(
            'notification dispatched uid=%s kind=%s source=%s',
            intent.user_id,
            intent.kind.value,
            intent.source,
        )
        return NotificationDispatchOutcome(
            NotificationDispatchStatus.DISPATCHED,
            rate_limit=policy_outcome.rate_limit if policy_outcome else None,
        )

    async def dispatch_async(self, intent: NotificationIntent) -> NotificationDispatchOutcome:
        policy_outcome = self._apply_policy(intent)
        if policy_outcome and policy_outcome.status == NotificationDispatchStatus.SUPPRESSED:
            return policy_outcome

        try:
            await self._async_delivery(intent.user_id, intent.title, intent.body, dict(intent.data))
        except Exception:
            logger.exception(
                'notification delivery failed uid=%s kind=%s source=%s',
                intent.user_id,
                intent.kind.value,
                intent.source,
            )
            return NotificationDispatchOutcome(
                NotificationDispatchStatus.FAILED,
                rate_limit=policy_outcome.rate_limit if policy_outcome else None,
                reason='delivery_failed',
            )

        logger.info(
            'notification dispatched uid=%s kind=%s source=%s',
            intent.user_id,
            intent.kind.value,
            intent.source,
        )
        return NotificationDispatchOutcome(
            NotificationDispatchStatus.DISPATCHED,
            rate_limit=policy_outcome.rate_limit if policy_outcome else None,
        )


_dispatcher = NotificationDispatcher()


def dispatch_notification(intent: NotificationIntent) -> NotificationDispatchOutcome:
    return _dispatcher.dispatch(intent)


async def dispatch_notification_async(intent: NotificationIntent) -> NotificationDispatchOutcome:
    return await _dispatcher.dispatch_async(intent)
