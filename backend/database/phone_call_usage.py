"""
Phone call usage counters for free-tier quota enforcement.

Counters live in Redis (fail-open, auto-expiring) rather than Firestore because
the free-tier quota exists only to limit App-Review bypass and abuse; we never
need historical usage data. Keys roll over at month boundaries:

  Key:    phone_call_usage:{uid}:{YYYY-MM}
  Value:  integer call count (INCR)
  TTL:    ~40 days so the previous month expires naturally after rollover

The counter mechanics live in ``database/monthly_usage_counter.py``; this module
owns the key prefix and the failure policy. If Redis is unavailable the read
returns 0 (allow) and the increment silently skips — same fail-open posture as
the rest of ``database/redis_db.py``.
"""

from datetime import datetime, timezone
import logging
from typing import Tuple

from database import monthly_usage_counter
from database.redis_db import r, try_catch_decorator

_KEY_PREFIX = 'phone_call_usage'
logger = logging.getLogger(__name__)


@try_catch_decorator
def _read_count(uid: str, now: datetime) -> int:
    return monthly_usage_counter.read_count(r, _KEY_PREFIX, uid, now)


def get_current_month_count(uid: str) -> Tuple[int, int]:
    """Return (calls_initiated, reset_at_epoch) for the current monthly bucket."""
    now = datetime.now(timezone.utc)
    count = _read_count(uid, now) or 0
    return count, monthly_usage_counter.period_reset_epoch(now)


def reserve_current_month_slot(uid: str, monthly_limit: int) -> Tuple[bool, int, int]:
    """Atomically reserve one free-tier call slot.

    Returns (reserved, used_before_reservation, reset_at_epoch). Redis failures
    fail open to match the non-critical quota posture used by this module.
    """
    now = datetime.now(timezone.utc)
    reset_at = monthly_usage_counter.period_reset_epoch(now)
    if monthly_limit <= 0:
        return False, 0, reset_at

    try:
        reserved, used_before = monthly_usage_counter.reserve_slot(r, _KEY_PREFIX, uid, monthly_limit, now)
        return reserved, used_before, reset_at
    except Exception as e:
        logger.error(f'Error reserving phone call quota {e}')
        return True, 0, reset_at


@try_catch_decorator
def increment_current_month(uid: str) -> None:
    """Atomically bump the current month's call counter by 1."""
    monthly_usage_counter.increment(r, _KEY_PREFIX, uid, datetime.now(timezone.utc))
