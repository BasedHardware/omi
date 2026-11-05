"""Rolling transcript import budgets, shared by every worker for a user."""

import logging
import os
import uuid
from typing import Optional

from database import redis_db

logger = logging.getLogger(__name__)

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


def _has_control_chars(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _sanitize_uid(uid) -> str:
    if not isinstance(uid, str):
        raise ValueError('uid must be a string')
    if not uid.strip():
        raise ValueError('uid must not be empty or whitespace-only')
    for forbidden in ('{', '}', ':', '/', '\\', '..'):
        if forbidden in uid:
            raise ValueError('uid must not contain forbidden characters')
    if _has_control_chars(uid):
        raise ValueError('uid must not contain control characters')
    return uid


def _sanitize_kind(kind) -> str:
    try:
        if kind not in _IMPORT_QUOTA_DEFAULTS:
            raise KeyError(kind)
    except TypeError as exc:
        raise KeyError(kind) from exc
    return kind


def _sanitize_amount(amount) -> int:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValueError('amount must be a positive int')
    if amount <= 0:
        raise ValueError('amount must be a positive int')
    return amount


def import_quota_limit(kind: str) -> int:
    """The configured limit; uploads and bytes have the same allowance on every plan."""
    # TODO #20647: hook tier limits into users.get_existing_user_subscription and
    # utils.subscription.is_paid_plan when a cached paid-status check is available.
    kind = _sanitize_kind(kind)
    default = _IMPORT_QUOTA_DEFAULTS[kind]
    env_name = f'IMPORT_MONTHLY_{kind.upper()}_LIMIT'
    raw = os.getenv(env_name)
    if raw is None:
        return max(0, int(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            'Invalid %s value %r; falling back to default %d',
            env_name,
            raw,
            default,
        )
        return max(0, int(default))
    return max(0, value)


def _quota_keys(uid: str, kind: str) -> tuple[str, str]:
    uid = _sanitize_uid(uid)
    kind = _sanitize_kind(kind)
    key = f'import:monthly:{kind}:{{{uid}}}'
    return f'{key}:events', f'{key}:amounts'


def reserve_import_quota(uid: str, kind: str, amount: int, redis_client=None) -> Optional[str]:
    """Reserve an upload or bytes in the last 30 days; None when the budget is spent.

    Redis errors propagate: imports must not store unmetered transcripts.
    Byte reservations are released unless conversation creation succeeds.
    Upload reservations are released when the request does not start an import.
    """
    uid = _sanitize_uid(uid)
    kind = _sanitize_kind(kind)
    amount = _sanitize_amount(amount)

    client = redis_db.r if redis_client is None else redis_client
    reservation = uuid.uuid4().hex
    admitted = client.eval(
        _RESERVE_IMPORT_QUOTA_LUA,
        2,
        *_quota_keys(uid, kind),
        IMPORT_QUOTA_WINDOW_SECONDS,
        import_quota_limit(kind),
        amount,
        reservation,
    )
    return reservation if admitted else None


def release_import_quota(uid: str, kind: str, reservation, redis_client=None) -> None:
    """Drop a reservation that should not count; safe to repeat."""
    # Skip the Redis round-trip for missing/blank/control-character reservations.
    if reservation is None:
        return
    if not isinstance(reservation, str):
        return
    if not reservation.strip():
        return
    if _has_control_chars(reservation):
        return

    uid = _sanitize_uid(uid)
    kind = _sanitize_kind(kind)
    client = redis_db.r if redis_client is None else redis_client
    client.eval(
        _RELEASE_IMPORT_QUOTA_LUA,
        2,
        *_quota_keys(uid, kind),
        reservation,
    )
