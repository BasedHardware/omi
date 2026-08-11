"""Memory Platform API request counters for plan-quota enforcement.

Counters live in Redis (auto-expiring) rather than Firestore for the same reason
as ``database/phone_call_usage.py``: the cap exists to bound free-tier usage of a
metered API, not to produce a billing ledger, so historical retention is not
needed. Keys roll over at month boundaries:

  Key:    memory_platform_usage:{uid}:{YYYY-MM}
  Value:  integer request count (INCR)
  TTL:    ~40 days so the previous month expires naturally after rollover

A Redis outage fails open (the request is served) and is reported through the
shared ``record_fallback`` helper — a quota counter must never be the reason the
product API is down.
"""

from datetime import datetime, timezone
import logging
from typing import Tuple

from database.redis_db import r
from utils.observability.fallback import record_fallback

_TTL_SECONDS = 40 * 24 * 3600  # 40 days — comfortably past any month rollover
logger = logging.getLogger(__name__)


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
    return f"memory_platform_usage:{uid}:{period_id}"


def get_current_month_usage(uid: str) -> Tuple[int, int]:
    """Return (requests_used, reset_at_epoch) for the current monthly bucket."""
    now = datetime.now(timezone.utc)
    try:
        raw = r.get(_key(uid, _period_id(now)))
        used = int(raw) if raw else 0
    except Exception:
        record_fallback(
            component='memory_platform',
            from_mode='metered',
            to_mode='unmetered',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        used = 0
    return used, _period_reset_epoch(now)


def reserve_current_month_request(uid: str, monthly_limit: int) -> Tuple[bool, int, int]:
    """Atomically reserve one request against the month's allowance.

    Returns ``(reserved, used_before_reservation, reset_at_epoch)``. A Redis
    failure fails open (``reserved=True``) and records the degrade, so quota
    infrastructure can never take the platform API offline.
    """
    now = datetime.now(timezone.utc)
    reset_at = _period_reset_epoch(now)
    if monthly_limit <= 0:
        return False, 0, reset_at

    key = _key(uid, _period_id(now))
    try:
        used_after = int(r.incr(key, 1))
        r.expire(key, _TTL_SECONDS)
        if used_after > monthly_limit:
            r.decr(key, 1)
            return False, used_after - 1, reset_at
        return True, used_after - 1, reset_at
    except Exception:
        record_fallback(
            component='memory_platform',
            from_mode='metered',
            to_mode='unmetered',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return True, 0, reset_at
