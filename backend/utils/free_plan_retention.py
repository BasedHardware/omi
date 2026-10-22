"""Free-plan retention lock (``FREE_RETENTION_LOCK_DAYS``).

A Free (``basic``) account keeps full access to conversations created within
the window; older ones are *retention locked*: still listed, still exportable,
but their detail read answers 402 ``retention_locked``. Paid plans (including
Stripe trials, which carry a paid plan type) are never locked. Distinct from
``is_locked``, which means "held behind the usage cap".
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, MutableMapping, Optional

import database.users as users_db
from config.free_plan import free_retention_lock_days
from models.users import PlanType

logger = logging.getLogger(__name__)

RETENTION_LOCKED_FIELD = 'retention_locked'


def retention_lock_days_for_user(uid: str) -> int:
    """Days of retention this user's plan grants; ``0`` when the lock does not apply.

    Only the Free plan is locked. An unreadable plan fails open for the user
    (``0``): a lookup error must never hide someone's conversations.
    """
    days = free_retention_lock_days()
    if days <= 0:
        return 0
    try:
        subscription = users_db.get_user_valid_subscription(uid)
    except Exception as exc:  # noqa: BLE001 - never lock on an unreadable plan
        logger.warning('retention lock: subscription unavailable for uid=%s: %s', uid, type(exc).__name__)
        return 0
    if subscription is not None and subscription.plan != PlanType.basic:
        return 0
    return days


def _created_at(conversation: Mapping[str, Any]) -> Optional[datetime]:
    value = conversation.get('created_at')
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def is_retention_locked(conversation: Mapping[str, Any], days: int, *, now: Optional[datetime] = None) -> bool:
    """Whether ``conversation`` is older than ``days``; a missing ``created_at`` is never locked."""
    if days <= 0:
        return False
    created = _created_at(conversation)
    if created is None:
        return False
    current = now or datetime.now(timezone.utc)
    return created < current - timedelta(days=days)


def annotate_retention_lock(
    uid: str, conversations: Iterable[MutableMapping[str, Any]], *, now: Optional[datetime] = None
) -> None:
    """Stamp ``retention_locked`` on list rows for a Free account; a no-op while the lock is off."""
    days = retention_lock_days_for_user(uid)
    if days <= 0:
        return
    for conversation in conversations:
        conversation[RETENTION_LOCKED_FIELD] = is_retention_locked(conversation, days, now=now)
