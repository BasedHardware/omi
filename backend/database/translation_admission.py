"""Fail-closed Redis admission shared by live and explicit detail translation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
from typing import Any
import uuid

from database import redis_db

_RESERVE = """
if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('EXISTS', KEYS[2]) == 1 then return 0 end
local uid = tonumber(redis.call('GET', KEYS[3]) or '0')
local global = tonumber(redis.call('GET', KEYS[4]) or '0')
local amount = tonumber(ARGV[3])
if uid + amount > tonumber(ARGV[4]) or global + amount > tonumber(ARGV[5]) then return -1 end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[2])
redis.call('INCRBY', KEYS[3], amount)
redis.call('INCRBY', KEYS[4], amount)
redis.call('EXPIRE', KEYS[3], ARGV[6])
redis.call('EXPIRE', KEYS[4], ARGV[6])
return 1
"""

_RELEASE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1], KEYS[2])
local refund = tonumber(ARGV[2])
if refund > 0 then
  redis.call('DECRBY', KEYS[3], refund)
  redis.call('DECRBY', KEYS[4], refund)
end
return 1
"""

MAX_ID_LENGTH = 128
MAX_REVISION_LENGTH = 256
MAX_POLICY_LENGTH = 64
MAX_TARGET_LENGTH = 32


def _clean_id(value: Any, max_len: int = MAX_ID_LENGTH) -> str:
    """Normalize and validate identifier strings against delimiter injection and overflow."""
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len or any(c in cleaned for c in ("\0", "\r", "\n", " ", ":")):
        return ""
    return cleaned


def _clean_str(value: Any, max_len: int = 128) -> str:
    """Normalize general string parameter."""
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len or "\0" in cleaned:
        return ""
    return cleaned


def _clean_date(day: Any) -> str:
    """Normalize or generate UTC YYYYMMDD date string."""
    if isinstance(day, str):
        cleaned = day.strip()
        if len(cleaned) == 8 and cleaned.isdigit():
            return cleaned
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _clean_int(value: Any, min_val: int = 1, max_val: int = 10_000_000) -> int | None:
    """Sanitize integer ensuring strictly integer (not bool), within safe bounds."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < min_val or value > max_val:
        return None
    return value


def _clean_deadline(seconds: Any, default: float = 3.0, min_val: float = 0.1, max_val: float = 300.0) -> float:
    """Sanitize provider deadline seconds, guarding against NaN, Inf, and out-of-range values."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return default
    if math.isnan(seconds) or math.isinf(seconds):
        return default
    if seconds < min_val:
        return min_val
    if seconds > max_val:
        return max_val
    return float(seconds)


def _resolve_redis(client: Any = None) -> Any:
    """Resolve Redis client instance with dependency injection fallback."""
    if client is not None:
        return client
    try:
        return redis_db.r
    except Exception:
        return None


@dataclass(frozen=True)
class TranslationReservation:
    keys: tuple[str, str, str, str]
    token: str
    reserved_chars: int


def reserve_translation(
    uid: str,
    conversation_id: str,
    target: str,
    source_revision: str,
    policy_version: str,
    reserved_chars: int,
    uid_daily_limit: int,
    global_daily_limit: int,
    *,
    client: Any = None,
    day: str | None = None,
    provider_deadline_seconds: float = 3.0,
) -> tuple[TranslationReservation | None, str]:
    clean_uid = _clean_id(uid)
    clean_cid = _clean_id(conversation_id)
    clean_target = _clean_str(target, max_len=MAX_TARGET_LENGTH)
    clean_rev = _clean_str(source_revision, max_len=MAX_REVISION_LENGTH)
    clean_policy = _clean_str(policy_version, max_len=MAX_POLICY_LENGTH)

    clean_reserved = _clean_int(reserved_chars, min_val=1)
    clean_uid_limit = _clean_int(uid_daily_limit, min_val=1)
    clean_global_limit = _clean_int(global_daily_limit, min_val=1)

    if (
        not clean_uid
        or not clean_cid
        or clean_reserved is None
        or clean_uid_limit is None
        or clean_global_limit is None
    ):
        return None, "budget_denied"

    store = _resolve_redis(client)
    if store is None or not hasattr(store, "eval"):
        return None, "redis_unavailable"

    date = _clean_date(day)
    digest = hashlib.sha256(
        f"{clean_uid}\0{clean_cid}\0{clean_target}\0{clean_rev}\0{clean_policy}".encode("utf-8")
    ).hexdigest()
    keys = (
        f"translation:viewed:v1:uid:{clean_uid}:inflight",
        f"translation:viewed:v1:content:{digest}",
        f"translation:viewed:v1:budget:uid:{clean_uid}:{date}",
        f"translation:viewed:v1:budget:global:{date}",
    )
    token = uuid.uuid4().hex
    deadline = _clean_deadline(provider_deadline_seconds)
    ttl = math.ceil(deadline + 12)

    try:
        raw_result = store.eval(
            _RESERVE,
            4,
            *keys,
            token,
            ttl,
            clean_reserved,
            clean_uid_limit,
            clean_global_limit,
            172800,
        )
        result = int(raw_result)
    except Exception:
        return None, "redis_unavailable"

    if result != 1:
        return None, "duplicate_suppressed" if result == 0 else "budget_denied"
    return TranslationReservation(keys, token, clean_reserved), "admitted"


def release_translation(reservation: TranslationReservation, actual_chars: int, *, client: Any = None) -> bool:
    try:
        keys = reservation.keys
        token = reservation.token
        reserved = reservation.reserved_chars
        if not keys or len(keys) != 4 or not token:
            return False
    except (AttributeError, TypeError):
        return False

    if type(actual_chars) is bool:
        safe_actual = 0
    else:
        try:
            val = float(actual_chars)
            safe_actual = 0 if (math.isnan(val) or math.isinf(val)) else max(0, int(val))
        except (TypeError, ValueError, OverflowError):
            safe_actual = 0

    refund = max(0, reserved - safe_actual)
    try:
        store = _resolve_redis(client)
        if store is None or not hasattr(store, "eval"):
            return False
        res = store.eval(_RELEASE, 4, *keys, token, refund)
        return bool(res)
    except Exception:
        return False


def reservation_is_current(reservation: TranslationReservation, *, client: Any = None) -> bool:
    try:
        keys = reservation.keys
        token = reservation.token
        if not keys or len(keys) < 2 or not token:
            return False
        key0, key1 = keys[0], keys[1]
    except (AttributeError, TypeError, IndexError):
        return False

    try:
        store = _resolve_redis(client)
        if store is None or not hasattr(store, "get"):
            return False

        expected_str = token
        expected_bytes = token.encode("utf-8")

        val1 = store.get(key0)
        val2 = store.get(key1)

        match1 = val1 == expected_str or val1 == expected_bytes
        match2 = val2 == expected_str or val2 == expected_bytes

        return bool(match1 and match2)
    except Exception:
        return False
