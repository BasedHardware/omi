"""Rolling transcript import budgets, shared by every worker for a user."""

import os
import uuid
from typing import Optional

from database import redis_db

IMPORT_QUOTA_WINDOW_SECONDS = 30 * 24 * 60 * 60
_IMPORT_QUOTA_DEFAULTS = {'upload': 100, 'byte': 1024 * 1024 * 1024}

# Prune and reserve in one operation: two jobs cannot both spend the last bytes.
_RESERVE_IMPORT_QUOTA_LUA = '''
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local window = tonumber(ARGV[1])
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now - window)
for _, member in ipairs(expired) do
    local amount = tonumber(redis.call('HGET', KEYS[2], member) or '0')
    redis.call('HINCRBY', KEYS[2], 'total', -amount)
    redis.call('HDEL', KEYS[2], member)
end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local total = tonumber(redis.call('HGET', KEYS[2], 'total') or '0')
local amount = tonumber(ARGV[3])
if total + amount > tonumber(ARGV[2]) then
    return 0
end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('HSET', KEYS[2], ARGV[4], amount)
redis.call('HINCRBY', KEYS[2], 'total', amount)
redis.call('EXPIRE', KEYS[1], window)
redis.call('EXPIRE', KEYS[2], window)
return 1
'''

_RELEASE_IMPORT_QUOTA_LUA = '''
local amount = tonumber(redis.call('HGET', KEYS[2], ARGV[1]) or '0')
if redis.call('ZREM', KEYS[1], ARGV[1]) == 1 then
    redis.call('HDEL', KEYS[2], ARGV[1])
    redis.call('HINCRBY', KEYS[2], 'total', -amount)
end
return 1
'''


def import_quota_limit(kind: str) -> int:
    """The configured limit; uploads and bytes have the same allowance on every plan."""
    # TODO #20647: hook tier limits into users.get_existing_user_subscription and
    # utils.subscription.is_paid_plan when a cached paid-status check is available.
    default = _IMPORT_QUOTA_DEFAULTS[kind]
    return max(0, int(os.getenv(f'IMPORT_MONTHLY_{kind.upper()}_LIMIT', str(default))))


def _quota_keys(uid: str, kind: str) -> tuple[str, str]:
    key = f'import:monthly:{kind}:{{{uid}}}'
    return f'{key}:events', f'{key}:amounts'


def reserve_import_quota(uid: str, kind: str, amount: int) -> Optional[str]:
    """Reserve an upload or bytes in the last 30 days; None when the budget is spent.

    Redis errors propagate: imports must not store unmetered transcripts.
    Byte reservations are released unless conversation creation succeeds.
    Upload reservations are released when the request does not start an import.
    """
    reservation = uuid.uuid4().hex
    admitted = redis_db.r.eval(
        _RESERVE_IMPORT_QUOTA_LUA,
        2,
        *_quota_keys(uid, kind),
        IMPORT_QUOTA_WINDOW_SECONDS,
        import_quota_limit(kind),
        amount,
        reservation,
    )
    return reservation if admitted else None


def release_import_quota(uid: str, kind: str, reservation: str) -> None:
    """Drop a reservation that should not count; safe to repeat."""
    redis_db.r.eval(_RELEASE_IMPORT_QUOTA_LUA, 2, *_quota_keys(uid, kind), reservation)
