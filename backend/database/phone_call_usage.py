"""
Phone call usage counters for free-tier quota enforcement.

Counters live in Redis (fail-open, auto-expiring) rather than Firestore because
the free-tier quota exists only to limit App-Review bypass and abuse; we never
need historical usage data. Keys roll over at month boundaries:

  Key:    phone_call_usage:{uid}:{YYYY-MM}
  Value:  integer call count (INCR)
  TTL:    ~40 days so the previous month expires naturally after rollover

If Redis is unavailable the read returns 0 (allow) and the increment silently
skips — same fail-open posture as the rest of ``database/redis_db.py``.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Tuple

from database.redis_db import r, try_catch_decorator

_TTL_SECONDS = 40 * 24 * 3600  # 40 days — comfortably past any month rollover
logger = logging.getLogger(__name__)


def _clean_uid(uid: object) -> str | None:
    """Normalize and guard user identifier.

    Strips leading/trailing whitespace, and rejects None, empty strings,
    non-string inputs, or excessively long identifiers (>128 chars).
    """
    if uid is None or not isinstance(uid, str):
        return None
    cleaned = uid.strip()
    if not cleaned or len(cleaned) > 128:
        return None
    return cleaned


def _period_id(now: datetime) -> str:
    return f"{now.year}-{now.month:02d}"


def _period_reset_epoch(now: datetime) -> int:
    """Epoch seconds at which the current monthly bucket rolls over."""
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return int(next_month.timestamp())


def _key(uid: str, period_id: str) -> str:
    return f"phone_call_usage:{uid}:{period_id}"


@try_catch_decorator
def _read_count(uid: str, period_id: str, client: Any = None) -> int:
    redis_instance = client if client is not None else r
    raw = redis_instance.get(_key(uid, period_id))
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def get_current_month_count(uid: object, *, client: Any = None) -> Tuple[int, int]:
    """Return (calls_initiated, reset_at_epoch) for the current monthly bucket.

    Fails open by returning (0, reset_at_epoch) when uid is invalid.
    """
    now = datetime.now(timezone.utc)
    clean_uid = _clean_uid(uid)
    if clean_uid is None:
        return 0, _period_reset_epoch(now)
    count = _read_count(clean_uid, _period_id(now), client=client) or 0
    return count, _period_reset_epoch(now)


def reserve_current_month_slot(uid: object, monthly_limit: object, *, client: Any = None) -> Tuple[bool, int, int]:
    """Atomically reserve one free-tier call slot.

    Returns (reserved, used_before_reservation, reset_at_epoch).
    Fails open on invalid uid or Redis infrastructure errors to prevent
    blocking calls. Fails closed (False) when monthly_limit is non-positive or invalid.
    """
    now = datetime.now(timezone.utc)
    reset_at = _period_reset_epoch(now)

    clean_uid = _clean_uid(uid)
    if clean_uid is None:
        return True, 0, reset_at

    if isinstance(monthly_limit, bool) or not isinstance(monthly_limit, int) or monthly_limit <= 0:
        return False, 0, reset_at

    key = _key(clean_uid, _period_id(now))
    redis_instance = client if client is not None else r
    try:
        used_after = int(redis_instance.incr(key, 1))
        redis_instance.expire(key, _TTL_SECONDS)
        if used_after > monthly_limit:
            redis_instance.decr(key, 1)
            return False, used_after - 1, reset_at
        return True, used_after - 1, reset_at
    except Exception as e:
        logger.error(f"Error reserving phone call quota: {e}")
        return True, 0, reset_at


@try_catch_decorator
def increment_current_month(uid: object, *, client: Any = None) -> None:
    """Atomically bump the current month's call counter by 1."""
    clean_uid = _clean_uid(uid)
    if clean_uid is None:
        return
    now = datetime.now(timezone.utc)
    key = _key(clean_uid, _period_id(now))
    redis_instance = client if client is not None else r
    pipe = redis_instance.pipeline()
    pipe.incr(key, 1)
    pipe.expire(key, _TTL_SECONDS)
    pipe.execute()
