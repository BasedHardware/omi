"""Memory Platform API request counters for plan-quota enforcement.

Counters live in Redis (auto-expiring) rather than Firestore for the same reason
as ``database/phone_call_usage.py``: the cap exists to bound free-tier usage of a
metered API, not to produce a billing ledger, so historical retention is not
needed. Keys roll over at month boundaries:

  Key:    memory_platform_usage:{uid}:{YYYY-MM}
  Value:  integer request count (INCR)
  TTL:    ~40 days so the previous month expires naturally after rollover

The counter mechanics live in ``database/monthly_usage_counter.py``; this module
owns the key prefix and the failure policy. A Redis outage fails open (the
request is served) and is reported through the shared ``record_fallback`` helper
— a quota counter must never be the reason the product API is down.
"""

from datetime import datetime, timezone
import logging
from typing import Tuple

from database import monthly_usage_counter
from database.redis_db import r
from utils.observability.fallback import record_fallback

_KEY_PREFIX = 'memory_platform_usage'
logger = logging.getLogger(__name__)


def _record_outage() -> None:
    record_fallback(
        component='memory_platform',
        from_mode='metered',
        to_mode='unmetered',
        reason='other',
        outcome='degraded',
        log=logger,
    )


def get_current_month_usage(uid: str) -> Tuple[int, int]:
    """Return (requests_used, reset_at_epoch) for the current monthly bucket."""
    now = datetime.now(timezone.utc)
    try:
        used = monthly_usage_counter.read_count(r, _KEY_PREFIX, uid, now)
    except Exception:
        _record_outage()
        used = 0
    return used, monthly_usage_counter.period_reset_epoch(now)


def reserve_current_month_request(uid: str, monthly_limit: int) -> Tuple[bool, int, int]:
    """Atomically reserve one request against the month's allowance.

    Returns ``(reserved, used_before_reservation, reset_at_epoch)``. A Redis
    failure fails open (``reserved=True``) and records the degrade, so quota
    infrastructure can never take the platform API offline.
    """
    now = datetime.now(timezone.utc)
    reset_at = monthly_usage_counter.period_reset_epoch(now)
    if monthly_limit <= 0:
        return False, 0, reset_at

    try:
        reserved, used_before = monthly_usage_counter.reserve_slot(r, _KEY_PREFIX, uid, monthly_limit, now)
        return reserved, used_before, reset_at
    except Exception:
        _record_outage()
        return True, 0, reset_at
