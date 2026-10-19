"""Rolling transcript import budgets, shared by every worker for a user."""

import logging
import os
import uuid
from typing import Any, Optional

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


def _sanitize_uid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('uid must be a non-empty string')
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '{', '}', ':', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        raise ValueError('uid must be a safe quota key identifier')
    return cleaned


def _sanitize_kind(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("kind must be 'upload' or 'byte'")
    cleaned = value.strip().lower()
    if cleaned not in _IMPORT_QUOTA_DEFAULTS:
        raise ValueError("kind must be 'upload' or 'byte'")
    return cleaned


def _sanitize_amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('amount must be a positive integer')
    return value


def import_quota_limit(kind: str) -> int:
    """The configured limit; uploads and bytes have the same allowance on every plan."""
    # TODO #20647: hook tier limits into users.get_existing_user_subscription and
    # utils.subscription.is_paid_plan when a cached paid-status check is available.
    clean_kind = _sanitize_kind(kind)
    default = _IMPORT_QUOTA_DEFAULTS[clean_kind]
    raw_env = os.getenv(f'IMPORT_MONTHLY_{clean_kind.upper()}_LIMIT', str(default))
    try:
        parsed = int(str(raw_env).strip())
    except (TypeError, ValueError):
        logger.warning('Invalid IMPORT_MONTHLY_%s_LIMIT=%r; falling back to %d', clean_kind.upper(), raw_env, default)
        parsed = default
    return max(0, parsed)


def _quota_keys(uid: str, kind: str) -> tuple[str, str]:
    clean_uid = _sanitize_uid(uid)
    clean_kind = _sanitize_kind(kind)
    key = f'import:monthly:{clean_kind}:{{{clean_uid}}}'
    return f'{key}:events', f'{key}:amounts'


def reserve_import_quota(uid: str, kind: str, amount: int, *, redis_client: Optional[Any] = None) -> Optional[str]:
    """Reserve an upload or bytes in the last 30 days; None when the budget is spent.

    Redis errors propagate: imports must not store unmetered transcripts.
    Byte reservations are released unless conversation creation succeeds.
    Upload reservations are released when the request does not start an import.
    """
    clean_uid = _sanitize_uid(uid)
    clean_kind = _sanitize_kind(kind)
    clean_amount = _sanitize_amount(amount)
    client = redis_client if redis_client is not None else redis_db.r
    reservation = uuid.uuid4().hex
    admitted = client.eval(
        _RESERVE_IMPORT_QUOTA_LUA,
        2,
        *_quota_keys(clean_uid, clean_kind),
        IMPORT_QUOTA_WINDOW_SECONDS,
        import_quota_limit(clean_kind),
        clean_amount,
        reservation,
    )
    return reservation if admitted else None


def release_import_quota(uid: str, kind: str, reservation: str, *, redis_client: Optional[Any] = None) -> None:
    """Drop a reservation that should not count; safe to repeat."""
    clean_uid = _sanitize_uid(uid)
    clean_kind = _sanitize_kind(kind)
    if not isinstance(reservation, str):
        return
    clean_reservation = reservation.strip()
    if not clean_reservation or any(ch in clean_reservation for ch in ('\x00', '\r', '\n')):
        return
    client = redis_client if redis_client is not None else redis_db.r
    client.eval(_RELEASE_IMPORT_QUOTA_LUA, 2, *_quota_keys(clean_uid, clean_kind), clean_reservation)
