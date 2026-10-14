"""Shared authenticated listen presence. Unknown, stale or mixed sessions require vendors.

Redis TIME owns leases. Stale members remain visible until explicit close or a
24-hour idle-key expiry: a failed heartbeat must never look like hidden demand.
No audio, transcript, credentials or user identifiers enter metric labels.
"""

import asyncio
import hashlib
import os
from typing import Any, NamedTuple

import redis.asyncio as aioredis

from config.live_stt_state import stage

PRESENCE = """
local key = KEYS[1]
local id = ARGV[1]
local now = tonumber(redis.call('TIME')[1])
if ARGV[2] == 'close' then
  redis.call('HDEL', key, id)
  return 1
end
if redis.call('HEXISTS', key, id) == 0 and redis.call('HLEN', key) >= 32 then
  redis.call('HSET', key, 'overflow', 'unknown:' .. (now + 30))
  redis.call('EXPIRE', key, 86400)
  return 1
end
redis.call('HSET', key, id, ARGV[2] .. ':' .. (now + 30))
redis.call('EXPIRE', key, 86400)
local members = redis.call('HVALS', key)
for _, value in ipairs(members) do
  local state, expiry = string.match(value, '^(%a+):(%d+)$')
  if state ~= 'hidden' or not expiry or tonumber(expiry) <= now then return 1 end
end
return 0
"""


class PresenceSnapshot(NamedTuple):
    visible: bool
    unavailable: bool = False


_client: Any = None


def _key(uid: str) -> str:
    digest = hashlib.sha256(uid.encode()).hexdigest()
    return f'omi:live-stt:demand-v1:{stage()}:{digest}'


async def update_presence(uid: str, socket_id: str, state: str) -> PresenceSnapshot:
    """Visible requires a vendor; dependency failures retain visible admission."""
    global _client
    if state not in {'hidden', 'visible', 'unknown', 'close'}:
        state = 'unknown'
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
        result = await asyncio.wait_for(_client.eval(PRESENCE, 1, _key(uid), socket_id, state), timeout=0.15)
        if type(result) is not int or result not in (0, 1):
            raise ValueError('Invalid demand presence result')
        return PresenceSnapshot(bool(result))
    except Exception:
        return PresenceSnapshot(True, unavailable=True)
