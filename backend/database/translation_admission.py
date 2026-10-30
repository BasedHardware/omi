"""Fail-closed Redis admission shared by live and explicit detail translation."""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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
    if not uid or not conversation_id or reserved_chars <= 0 or uid_daily_limit <= 0 or global_daily_limit <= 0:
        return None, 'budget_denied'
    date = day or datetime.now(timezone.utc).strftime('%Y%m%d')
    digest = hashlib.sha256(
        f'{uid}\0{conversation_id}\0{target}\0{source_revision}\0{policy_version}'.encode('utf-8')
    ).hexdigest()
    keys = (
        f'translation:viewed:v1:uid:{uid}:inflight',
        f'translation:viewed:v1:content:{digest}',
        f'translation:viewed:v1:budget:uid:{uid}:{date}',
        f'translation:viewed:v1:budget:global:{date}',
    )
    token = uuid.uuid4().hex
    try:
        result = int(
            (client or redis_db.r).eval(
                _RESERVE,
                4,
                *keys,
                token,
                math.ceil(provider_deadline_seconds + 12),
                reserved_chars,
                uid_daily_limit,
                global_daily_limit,
                172800,
            )
        )
    except Exception:
        return None, 'redis_unavailable'
    if result != 1:
        return None, 'duplicate_suppressed' if result == 0 else 'budget_denied'
    return TranslationReservation(keys, token, reserved_chars), 'admitted'


def release_translation(reservation: TranslationReservation, actual_chars: int, *, client: Any = None) -> bool:
    refund = max(0, reservation.reserved_chars - max(0, actual_chars))
    try:
        return bool((client or redis_db.r).eval(_RELEASE, 4, *reservation.keys, reservation.token, refund))
    except Exception:
        return False


def reservation_is_current(reservation: TranslationReservation, *, client: Any = None) -> bool:
    try:
        store = client or redis_db.r
        return store.get(reservation.keys[0]) == reservation.token.encode('utf-8') and store.get(
            reservation.keys[1]
        ) == reservation.token.encode('utf-8')
    except Exception:
        return False
