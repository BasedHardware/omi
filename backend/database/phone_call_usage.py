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
from typing import Any, Optional, Tuple

from database.redis_db import r, try_catch_decorator

_TTL_SECONDS = 40 * 24 * 3600  # 40 days — comfortably past any month rollover
logger = logging.getLogger(__name__)


def _clean_uid(uid: Optional[str]) -> str:
    """Validate and sanitize user ID to prevent key injection and invalid keys."""
    if not isinstance(uid, str):
        return ""
    cleaned = uid.strip()
    if not cleaned or len(cleaned) > 128 or any(c in cleaned for c in (":", "\r", "\n", " ", "\t")):
        return ""
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


def _get_redis_client(redis_client: Any = None) -> Any:
    return redis_client if redis_client is not None else r


def _read_count(uid: str, period_id: str, *, redis_client: Any = None) -> int:
    client = _get_redis_client(redis_client)
    try:
        raw = client.get(_key(uid, period_id))
        if not raw:
            return 0
        return max(0, int(raw))
    except Exception as e:
        logger.warning("Error reading phone call usage for uid=%s: %s", uid, e)
        return 0


def get_current_month_count(uid: str, *, redis_client: Any = None) -> Tuple[int, int]:
    """Return (calls_initiated, reset_at_epoch) for the current monthly bucket."""
    now = datetime.now(timezone.utc)
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return 0, _period_reset_epoch(now)
    count = _read_count(clean_uid, _period_id(now), redis_client=redis_client)
    return count, _period_reset_epoch(now)


def reserve_current_month_slot(
    uid: str,
    monthly_limit: int,
    *,
    redis_client: Any = None,
) -> Tuple[bool, int, int]:
    """Atomically reserve one free-tier call slot.

    Returns (reserved, used_before_reservation, reset_at_epoch). Redis failures
    fail open to match the non-critical quota posture used by this module.
    """
    now = datetime.now(timezone.utc)
    reset_at = _period_reset_epoch(now)
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return False, 0, reset_at

    try:
        limit = int(monthly_limit)
    except (ValueError, TypeError):
        return False, 0, reset_at

    if limit <= 0:
        return False, 0, reset_at

    client = _get_redis_client(redis_client)
    key = _key(clean_uid, _period_id(now))
    try:
        used_after = int(client.incr(key, 1))
        client.expire(key, _TTL_SECONDS)
        if used_after > limit:
            try:
                client.decr(key, 1)
            except Exception as decr_err:
                logger.warning("Error rolling back over-quota counter for %s: %s", clean_uid, decr_err)
            return False, max(0, used_after - 1), reset_at
        return True, max(0, used_after - 1), reset_at
    except Exception as e:
        logger.error("Error reserving phone call quota: %s", e)
        return True, 0, reset_at


def increment_current_month(uid: str, *, redis_client: Any = None) -> None:
    """Atomically bump the current month's call counter by 1."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return
    now = datetime.now(timezone.utc)
    key = _key(clean_uid, _period_id(now))
    client = _get_redis_client(redis_client)
    try:
        pipe = client.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, _TTL_SECONDS)
        pipe.execute()
    except Exception as e:
        logger.warning("Error incrementing current month usage for %s: %s", clean_uid, e)


def reset_current_month_usage(uid: str, *, redis_client: Any = None) -> bool:
    """Clear usage counter for the current month (e.g. on test cleanup or admin override)."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return False
    now = datetime.now(timezone.utc)
    key = _key(clean_uid, _period_id(now))
    client = _get_redis_client(redis_client)
    try:
        client.delete(key)
        return True
    except Exception as e:
        logger.warning("Error resetting phone call usage for %s: %s", clean_uid, e)
        return False
