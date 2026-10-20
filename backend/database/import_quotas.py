"""Rolling transcript import budgets, shared by every worker for a user."""

import os
import uuid
from typing import Optional

from database import redis_db

IMPORT_QUOTA_WINDOW_SECONDS = 30 * 24 * 60 * 60
_IMPORT_QUOTA_DEFAULTS = {'upload': 100, 'byte': 1024 * 1024 * 1024}
_QUOTA_KINDS = frozenset(_IMPORT_QUOTA_DEFAULTS)
_MAX_UID_LENGTH = 128
_MAX_RESERVATION_LENGTH = 64
_RESERVED_SEGMENTS = frozenset({'', '.', '..', '__reserved__'})

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


def _clean_quota_token(value: object, *, max_length: int, label: str) -> str:
    """A token that is safe inside a Redis Cluster hash tag and a key segment."""
    if not isinstance(value, str) or isinstance(value, bool):
        raise ValueError(f'invalid import quota {label}')
    token = value.strip()
    if token in _RESERVED_SEGMENTS or len(value) > max_length:
        raise ValueError(f'invalid import quota {label}')
    if any(char in token for char in '{}/\\:') or '..' in token:
        raise ValueError(f'invalid import quota {label}')
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        raise ValueError(f'invalid import quota {label}')
    return token


def clean_quota_uid(uid: object) -> str:
    """The Redis Cluster hash-tag component; an unusable uid would collapse slots."""
    return _clean_quota_token(uid, max_length=_MAX_UID_LENGTH, label='uid')


def clean_quota_kind(kind: object) -> str:
    if not isinstance(kind, str) or kind not in _QUOTA_KINDS:
        raise ValueError(f'unknown import quota kind: {kind!r}')
    return kind


def clean_quota_amount(amount: object) -> Optional[int]:
    """A positive integer budget spend; booleans are not integers here."""
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return None
    return amount


def clean_quota_reservation(reservation: object) -> Optional[str]:
    if not isinstance(reservation, str) or isinstance(reservation, bool):
        return None
    token = reservation.strip()
    if not token or token != reservation or len(token) > _MAX_RESERVATION_LENGTH:
        return None
    if any(char in token for char in '{}/\\:') or '..' in token:
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        return None
    return token


def import_quota_limit(kind: str) -> int:
    """The configured limit; uploads and bytes have the same allowance on every plan."""
    # TODO #20647: hook tier limits into users.get_existing_user_subscription and
    # utils.subscription.is_paid_plan when a cached paid-status check is available.
    kind = clean_quota_kind(kind)
    default = _IMPORT_QUOTA_DEFAULTS[kind]
    raw = os.getenv(f'IMPORT_MONTHLY_{kind.upper()}_LIMIT')
    try:
        limit = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        limit = default
    return max(0, limit)


def _quota_keys(uid: str, kind: str) -> tuple[str, str]:
    uid = clean_quota_uid(uid)
    kind = clean_quota_kind(kind)
    key = f'import:monthly:{kind}:{{{uid}}}'
    return f'{key}:events', f'{key}:amounts'


def reserve_import_quota(uid: str, kind: str, amount: int) -> Optional[str]:
    """Reserve an upload or bytes in the last 30 days; None when the budget is spent.

    Redis errors propagate: imports must not store unmetered transcripts.
    Byte reservations are released unless conversation creation succeeds.
    Upload reservations are released when the request does not start an import.
    An unusable uid, kind or amount reserves nothing and reports the budget as spent.
    """
    try:
        keys = _quota_keys(uid, kind)
    except ValueError:
        return None
    spend = clean_quota_amount(amount)
    if spend is None:
        return None
    reservation = uuid.uuid4().hex
    admitted = redis_db.r.eval(
        _RESERVE_IMPORT_QUOTA_LUA,
        2,
        *keys,
        IMPORT_QUOTA_WINDOW_SECONDS,
        import_quota_limit(kind),
        spend,
        reservation,
    )
    return reservation if admitted else None


def release_import_quota(uid: str, kind: str, reservation: str) -> None:
    """Drop a reservation that should not count; safe to repeat."""
    cleaned = clean_quota_reservation(reservation)
    if cleaned is None:
        return
    try:
        keys = _quota_keys(uid, kind)
    except ValueError:
        return
    redis_db.r.eval(_RELEASE_IMPORT_QUOTA_LUA, 2, *keys, cleaned)
