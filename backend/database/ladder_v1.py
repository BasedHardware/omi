"""Per-UID daily request counts shared by MCP and developer API keys.

The counter is one Redis key per uid per UTC date. INCR and EXPIREAT run in
the same Lua call as the API-key rate limiter, so a hot poller does not take a
Firestore transaction. A request already at the cap does not increment.
Redis errors propagate; the admission caller maps them to a retryable 503.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from database.redis_db import r

_KEY_PREFIX = 'ladder_v1:api_daily'

# Returns {admitted, used}. Denied requests do not increment. EXPIREAT is the
# next 00:00 UTC and is reapplied when a key has lost its TTL.
_RESERVE_LUA = r.register_script("""
local key = KEYS[1]
local cap = tonumber(ARGV[1])
local expire_at = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', key) or '0')
if current >= cap then
    if redis.call('TTL', key) < 0 then
        redis.call('EXPIREAT', key, expire_at)
    end
    return {0, current}
end
current = redis.call('INCR', key)
if current == 1 or redis.call('TTL', key) < 0 then
    redis.call('EXPIREAT', key, expire_at)
end
return {1, current}
""")


def _as_int(raw: Any) -> int:
    if raw is None:
        return 0
    if isinstance(raw, bytes):
        raw = raw.decode()
    return int(raw)


def _window(now: datetime | None) -> tuple[datetime, int]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reset = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return current, int(reset.timestamp())


def _key(uid: str, now: datetime) -> str:
    return f'{_KEY_PREFIX}:{uid}:{now.date().isoformat()}'


def _state(used: int, cap: int, *, allowed: bool) -> str:
    if not allowed:
        return 'cap'
    if cap > 0 and used * 100 >= cap * 80:
        return 'nudge'
    return 'within'


def reserve_daily_request(uid: str, cap: int, *, now: datetime | None = None, redis_client: Any = None) -> dict:
    current, reset_at = _window(now)
    admitted, used = _RESERVE_LUA(keys=[_key(uid, current)], args=[cap, reset_at], client=redis_client)
    allowed = bool(_as_int(admitted))
    used = _as_int(used)
    return {
        'allowed': allowed,
        'used': used,
        'limit': cap,
        'reset_at': reset_at,
        'state': _state(used, cap, allowed=allowed),
    }


def daily_cap_reached(uid: str, cap: int, *, now: datetime | None = None, redis_client: Any = None) -> bool:
    """Presentation-only read: never reserve requests from a storefront visit."""
    current, _reset_at = _window(now)
    client = r if redis_client is None else redis_client
    return _as_int(client.get(_key(uid, current))) >= cap
