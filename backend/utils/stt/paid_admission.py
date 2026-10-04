"""Fleet budget for router-promoted paid dials after Parakeet capacity refusal.

Denial (including unavailable Redis) restores configured selection. This bounds
router-induced spillover, not paid dials already required by the static chain.
Redis TIME owns the minute boundary; all endpoints/accounts share a provider budget.
"""

import asyncio
import os
from typing import Any

import redis.asyncio as aioredis

from config.live_stt_state import stage
from utils.stt.live_metrics import PAID_SPILLOVER_ADMISSIONS

ADMIT = """
local minute = math.floor(tonumber(redis.call('TIME')[1]) / 60)
local old = tonumber(redis.call('HGET', KEYS[1], 'minute') or '-1')
if old ~= minute then
  redis.call('HSET', KEYS[1], 'minute', minute, 'count', 0)
end
local count = tonumber(redis.call('HGET', KEYS[1], 'count') or '0')
redis.call('EXPIRE', KEYS[1], 120)
if count >= tonumber(ARGV[1]) then return 0 end
redis.call('HINCRBY', KEYS[1], 'count', 1)
return 1
"""
_client: Any = None


def enabled() -> bool:
    return os.getenv('STT_PAID_SPILLOVER_BUDGET_ENABLED', 'false').lower() == 'true'


def limit(provider: str) -> int:
    configured = {
        'soniox': os.getenv('STT_PAID_SPILLOVER_SONIOX_PER_MINUTE', '30'),
        'modulate': os.getenv('STT_PAID_SPILLOVER_MODULATE_PER_MINUTE', '30'),
        'deepgram': os.getenv('STT_PAID_SPILLOVER_DEEPGRAM_PER_MINUTE', '30'),
    }
    try:
        return min(10000, max(0, int(configured[provider])))
    except ValueError:
        return 30


async def admit(provider: str) -> bool:
    global _client
    try:
        if _client is None:
            _client = aioredis.Redis(
                host=os.getenv('REDIS_DB_HOST') or 'localhost',
                port=int(os.getenv('REDIS_DB_PORT', '6379')),
                password=os.getenv('REDIS_DB_PASSWORD'),
                socket_connect_timeout=0.1,
                socket_timeout=0.1,
                retry_on_timeout=False,
            )
        # Endpoint/credential rotations must not reset the fleet spend cap.
        key = f'omi:live-stt:paid-spillover-v1:{stage()}:{provider}'
        allowed = bool(await asyncio.wait_for(_client.eval(ADMIT, 1, key, limit(provider)), timeout=0.15))
        outcome = 'admitted' if allowed else 'denied'
    except Exception:
        allowed, outcome = False, 'unavailable'
    PAID_SPILLOVER_ADMISSIONS.labels(provider=provider, outcome=outcome).inc()
    return allowed
