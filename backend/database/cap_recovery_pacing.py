"""Atomic cross-pod audio + intent token buckets. No fail-open fallback.

Redis Lua is also used by redis_db's cross-pod request limiters. This dedicated
bounded client deliberately does not inherit their callers' fail-open policy.
The single, versioned key is shared by API and sync workers and by all owners.
"""

import logging
import math
from dataclasses import dataclass
from typing import Any

from config.cap_recovery_pacing import BURST_SECONDS, UNAVAILABLE_RETRY_SECONDS, limits
from database.redis_connection import create_bounded_redis_client

logger = logging.getLogger(__name__)
KEY = 'rl:cap-hold-recovery:v1:global'
_client: Any = None

# Redis TIME prevents worker clock skew from minting credits. Keep a partially
# depleted bucket until it is full again; never expire on a fixed short TTL.
# Missing/evicted state starts EMPTY, so Redis loss cannot mint a fresh burst.
LUA = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local audio_rate, hold_rate = tonumber(ARGV[1]), tonumber(ARGV[2])
local cost, burst = tonumber(ARGV[3]), tonumber(ARGV[4])
local audio_cap, hold_cap = audio_rate * burst, math.max(1, hold_rate * burst)
if cost > audio_cap then return {2, 60000} end
local previous = redis.call('HMGET', KEYS[1], 'at', 'audio', 'holds')
local at = tonumber(previous[1]) or now
local elapsed = math.max(0, now - at)
local audio = math.min(audio_cap, (tonumber(previous[2]) or 0) + elapsed * audio_rate)
local holds = math.min(hold_cap, (tonumber(previous[3]) or 0) + elapsed * hold_rate)
local wait = math.max(0, (cost - audio) / audio_rate, (1 - holds) / hold_rate)
local admitted = 0
if wait <= 0 then
    audio, holds = audio - cost, holds - 1
    admitted = 1
end
redis.call('HSET', KEYS[1], 'at', math.max(at, now), 'audio', audio, 'holds', holds)
-- No TTL: eviction/restart starts empty; idle time refills this one fixed key.
return {admitted, math.ceil(wait * 1000)}
"""


@dataclass(frozen=True)
class Decision:
    outcome: str  # granted | deferred | refused
    retry_after: float = 0
    reason: str = 'capacity'  # capacity | unavailable | invalid | oversized


def reserve(seconds: float, *, redis_client: Any = None) -> Decision:
    """Spend both budgets before each *new* provider intent, including retries.

    No refund: an ambiguous reply/write can waste capacity but never cause a
    burst. A cached provider result is settled without calling this function.
    """
    global _client
    try:
        capacity = limits()
        if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('invalid recovery audio cost')
    except (ValueError, TypeError, OverflowError):
        return Decision('refused', UNAVAILABLE_RETRY_SECONDS, 'invalid')
    try:
        if redis_client is None:
            if _client is None:
                _client = create_bounded_redis_client(2)
            redis_client = _client
        result, wait_ms = redis_client.eval(
            LUA, 1, KEY, capacity.audio_per_second, capacity.holds_per_second, seconds, BURST_SECONDS
        )
        if result == 1 and wait_ms == 0:
            return Decision('granted')
        if result == 2:
            return Decision('refused', UNAVAILABLE_RETRY_SECONDS, 'oversized')
        if result != 0 or not math.isfinite(float(wait_ms)) or wait_ms <= 0:
            raise ValueError('invalid pacing response')
        return Decision('deferred', max(0.001, wait_ms / 1000))
    except Exception as error:
        logger.warning('event=cap_recovery_pacing outcome=refused exception_type=%s', type(error).__name__)
        return Decision('refused', UNAVAILABLE_RETRY_SECONDS, 'unavailable')
