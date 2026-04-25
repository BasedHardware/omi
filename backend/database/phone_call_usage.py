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
from typing import Tuple

from database.redis_db import r, try_catch_decorator

_TTL_SECONDS = 40 * 24 * 3600  # 40 days — comfortably past any month rollover


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
def _read_count(uid: str, period_id: str) -> int:
    raw = r.get(_key(uid, period_id))
    return int(raw) if raw else 0


def get_current_month_count(uid: str) -> Tuple[int, int]:
    """Return (calls_initiated, reset_at_epoch) for the current monthly bucket."""
    now = datetime.now(timezone.utc)
    count = _read_count(uid, _period_id(now)) or 0
    return count, _period_reset_epoch(now)


@try_catch_decorator
def increment_current_month(uid: str) -> None:
    """Atomically bump the current month's call counter by 1."""
    now = datetime.now(timezone.utc)
    key = _key(uid, _period_id(now))
    pipe = r.pipeline()
    pipe.incr(key, 1)
    pipe.expire(key, _TTL_SECONDS)
    pipe.execute()
