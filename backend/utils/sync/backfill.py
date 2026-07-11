"""Redis-backed admission and daily spend guards for historical sync recovery."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from database.redis_db import r as redis_client

logger = logging.getLogger(__name__)

BACKFILL_SLOT_TTL_SECONDS = 2 * 24 * 60 * 60


def per_user_daily_limit_ms() -> int:
    return max(0, int(float(os.getenv('SYNC_BACKFILL_USER_DAILY_HOURS', '4')) * 60 * 60 * 1000))


def global_daily_limit_ms() -> int:
    return max(0, int(float(os.getenv('SYNC_BACKFILL_GLOBAL_DAILY_HOURS', '555')) * 60 * 60 * 1000))


def retry_after_next_utc_day() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


def _day_suffix() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%d')


def try_acquire_backfill_slot(uid: str, job_id: str) -> bool:
    key = f'sync_backfill:inflight:{uid}'
    acquired = redis_client.set(key, job_id, nx=True, ex=BACKFILL_SLOT_TTL_SECONDS)
    if acquired:
        return True
    existing = redis_client.get(key)
    if isinstance(existing, bytes):
        existing = existing.decode()
    return existing == job_id


_RELEASE_SLOT_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def release_backfill_slot(uid: str, job_id: str) -> None:
    redis_client.eval(_RELEASE_SLOT_SCRIPT, 1, f'sync_backfill:inflight:{uid}', job_id)


@dataclass(frozen=True)
class BackfillReservation:
    allowed: bool
    reason: Optional[str] = None
    retry_after: Optional[int] = None
    global_used_ms: int = 0


_RESERVE_SCRIPT = """
local existing = redis.call('get', KEYS[3])
if existing then
    return {1, tonumber(redis.call('get', KEYS[2]) or '0')}
end
local user_used = tonumber(redis.call('get', KEYS[1]) or '0')
local global_used = tonumber(redis.call('get', KEYS[2]) or '0')
local amount = tonumber(ARGV[1])
local user_limit = tonumber(ARGV[2])
local global_limit = tonumber(ARGV[3])
if user_limit > 0 and user_used + amount > user_limit then
    return {-1, global_used}
end
if global_limit > 0 and global_used + amount > global_limit then
    return {-2, global_used}
end
redis.call('incrby', KEYS[1], amount)
redis.call('expire', KEYS[1], ARGV[4])
redis.call('incrby', KEYS[2], amount)
redis.call('expire', KEYS[2], ARGV[4])
redis.call('set', KEYS[3], amount, 'EX', ARGV[4])
return {1, global_used + amount}
"""


def reserve_backfill_speech(uid: str, job_id: str, speech_ms: int) -> BackfillReservation:
    if speech_ms <= 0:
        return BackfillReservation(allowed=True)
    retry_after = retry_after_next_utc_day()
    suffix = _day_suffix()
    raw_result = redis_client.eval(
        _RESERVE_SCRIPT,
        3,
        f'sync_backfill:daily:{uid}:{suffix}',
        f'sync_backfill:daily:global:{suffix}',
        f'sync_backfill:reservation:{job_id}',
        speech_ms,
        per_user_daily_limit_ms(),
        global_daily_limit_ms(),
        retry_after + 3600,
    )
    if isinstance(raw_result, (list, tuple)):
        result = int(raw_result[0])
        global_used_ms = int(raw_result[1])
    else:
        result = int(raw_result)
        global_used_ms = 0
    if result == -1:
        return BackfillReservation(False, 'backfill_paced', retry_after, global_used_ms)
    if result == -2:
        return BackfillReservation(False, 'backfill_capacity', retry_after, global_used_ms)

    global_limit = global_daily_limit_ms()
    if global_limit > 0:
        for threshold in (70, 90):
            if global_used_ms * 100 < global_limit * threshold:
                continue
            alert_key = f'sync_backfill:budget_alert:{suffix}:{threshold}'
            if redis_client.set(alert_key, '1', nx=True, ex=retry_after + 3600):
                logger.warning(
                    'sync_backfill_budget_threshold threshold=%s used_ms=%s limit_ms=%s',
                    threshold,
                    global_used_ms,
                    global_limit,
                )
    return BackfillReservation(True, global_used_ms=global_used_ms)
