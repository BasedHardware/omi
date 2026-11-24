"""Atomic fleet budgets for automatic held-audio release. No fail-open fallback.

One UTC-day counter and one token bucket, shared by every worker. As with recovery
pacing, Redis TIME prevents clock skew from minting credit, missing state starts the
bucket empty, and an ambiguous reply can waste budget but never overspend it.
"""

import logging
import math
from typing import Any

from config.backlog_release import fleet_hours_per_day, fleet_hours_per_hour
from database.redis_connection import create_bounded_redis_client

logger = logging.getLogger(__name__)
BUCKET_KEY = 'rl:backlog-release:v1:bucket'
DAY_PREFIX = 'rl:backlog-release:v1:day:'
BURST_SECONDS = 600
_client: Any = None

LUA = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local rate, per_day, cost, burst = tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), tonumber(ARGV[4])
local day_key = ARGV[5] .. math.floor(now / 86400)
local spent = tonumber(redis.call('GET', day_key)) or 0
if spent + cost > per_day then return 0 end
local previous = redis.call('HMGET', KEYS[1], 'at', 'tokens')
local at = tonumber(previous[1]) or now
local cap = math.max(rate * burst, cost)
local tokens = math.min(cap, (tonumber(previous[2]) or 0) + math.max(0, now - at) * rate)
local admitted = 0
if tokens >= cost then
    tokens = tokens - cost
    admitted = 1
    redis.call('INCRBYFLOAT', day_key, cost)
    redis.call('EXPIRE', day_key, 172800)
end
redis.call('HSET', KEYS[1], 'at', math.max(at, now), 'tokens', tokens)
return admitted
"""


def reserve(seconds: float, *, redis_client: Any = None) -> bool:
    """Spend fleet budget for this much audio. Any failure answers no: the audio stays held."""
    global _client
    try:
        if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError('invalid release cost')
        if seconds == 0:
            return True
        if redis_client is None:
            if _client is None:
                _client = create_bounded_redis_client(2)
            redis_client = _client
        admitted = redis_client.eval(
            LUA,
            1,
            BUCKET_KEY,
            fleet_hours_per_hour(),  # audio-hours per hour is audio-seconds per second
            fleet_hours_per_day() * 3600,
            seconds,
            BURST_SECONDS,
            DAY_PREFIX,
        )
        return admitted == 1
    except Exception as error:
        logger.warning('event=backlog_release_budget outcome=refused exception_type=%s', type(error).__name__)
        return False
