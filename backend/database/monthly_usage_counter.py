"""Shared monthly Redis usage counter used by per-feature quota modules.

A counter is a plain Redis integer keyed ``{prefix}:{uid}:{YYYY-MM}`` with a TTL
comfortably past a month rollover, so the previous month expires by itself. This
module owns only the counter mechanics: period identity, rollover epoch, key
shape, and the atomic INCR/EXPIRE/over-limit-DECR reservation.

It deliberately does **not** own failure policy. Every function here propagates
Redis errors, and it takes the Redis client as an argument rather than importing
one, so each caller keeps its own key prefix, fail-open posture, and reporting
(``record_fallback`` vs. logging) and stays independently patchable in tests.
"""

from datetime import datetime, timezone
from typing import Tuple

TTL_SECONDS = 40 * 24 * 3600  # 40 days — comfortably past any month rollover


def period_id(now: datetime) -> str:
    """Return the ``YYYY-MM`` bucket identifier for ``now``."""
    return f"{now.year}-{now.month:02d}"


def period_reset_epoch(now: datetime) -> int:
    """Epoch seconds at which the current monthly bucket rolls over."""
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return int(next_month.timestamp())


def key_for(prefix: str, uid: str, now: datetime) -> str:
    """Return the Redis key holding ``uid``'s counter for ``now``'s month."""
    return f"{prefix}:{uid}:{period_id(now)}"


def read_count(redis_client, prefix: str, uid: str, now: datetime) -> int:
    """Return the counter value for the month containing ``now``."""
    raw = redis_client.get(key_for(prefix, uid, now))
    return int(raw) if raw else 0


def reserve_slot(redis_client, prefix: str, uid: str, monthly_limit: int, now: datetime) -> Tuple[bool, int]:
    """Atomically reserve one unit against the month's allowance.

    Returns ``(reserved, used_before_reservation)``. The reservation is made by
    INCR first and rolled back with DECR when it would exceed ``monthly_limit``,
    so concurrent callers can never both take the last slot.
    """
    key = key_for(prefix, uid, now)
    used_after = int(redis_client.incr(key, 1))
    redis_client.expire(key, TTL_SECONDS)
    if used_after > monthly_limit:
        redis_client.decr(key, 1)
        return False, used_after - 1
    return True, used_after - 1


def increment(redis_client, prefix: str, uid: str, now: datetime) -> None:
    """Bump the month's counter by 1 without any limit check."""
    key = key_for(prefix, uid, now)
    pipe = redis_client.pipeline()
    pipe.incr(key, 1)
    pipe.expire(key, TTL_SECONDS)
    pipe.execute()
