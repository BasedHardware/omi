"""Bound the optional LEGACY fresh lane by upload count and server-measured bytes.

Redis failure demotes to backfill: availability never grants unbounded fresh
capacity. A token costs one upload or one MiB, whichever is larger. Retries
consume budget too; admission never trusts a client duration or timestamp for
the charge. Invoke from the database executor, not the event loop.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import logging
import math
import os

from config.rollout_cohorts import in_rollout_cohort
from typing import Any, Iterable

from database.redis_db import create_bounded_redis_client
from utils.sync import stage
from utils.sync.lanes import CaptureTimeTrust, SyncLane, SyncLaneDecision

logger = logging.getLogger(__name__)
MIB = 1024 * 1024
redis_client: Any = None


def _get_redis_client() -> Any:
    global redis_client
    if redis_client is None:
        redis_client = create_bounded_redis_client(1.0)
    return redis_client


def enabled_for(uid: str) -> bool:
    """Master kill switch plus the final-pass policy's stable SHA-256 UID cohort."""
    if not uid or os.getenv('SYNC_LEGACY_FRESH_ENABLED', 'false').strip().lower() != 'true':
        return False
    if in_rollout_cohort(uid, 'sync-legacy-fresh'):
        return True
    try:
        percent = float(os.getenv('SYNC_LEGACY_FRESH_PERCENT', '0'))
    except ValueError:
        return False
    if not math.isfinite(percent):
        return False
    percent = max(0.0, min(100.0, percent))
    bucket = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:4], 'big') / 2**32 * 100
    return bucket < percent


# Redis TIME gives all replicas one refill clock. The single hash has bounded
# size and expires only after a full refill interval without admission. Rejections do not spend.
_RESERVE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local burst = tonumber(ARGV[1])
local rate = tonumber(ARGV[2]) / 3600
local cost = tonumber(ARGV[3])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(state[1]) or burst
local updated = tonumber(state[2]) or now
tokens = math.min(burst, tokens + math.max(0, now - updated) * rate)
if cost > tokens then return 0 end
redis.call('HSET', KEYS[1], 'tokens', tokens - cost, 'updated', now)
redis.call('EXPIRE', KEYS[1], math.max(7200, math.ceil(burst / rate) + 3600))
return 1
"""


def admit(uid: str, decision: SyncLaneDecision, file_sizes: Iterable[int | None]) -> SyncLaneDecision:
    if decision.lane != SyncLane.FRESH or decision.trust != CaptureTimeTrust.LEGACY:
        return decision
    reason = 'legacy_fresh_budget_unavailable'
    try:
        sizes = list(file_sizes)
        # UploadFile.size is populated by the multipart parser, not a header.
        if not sizes or any(size is None or size < 0 for size in sizes):
            return replace(decision, lane=SyncLane.BACKFILL, reason=reason)
        cost = max(1, math.ceil(sum(size for size in sizes if size is not None) / MIB))
        burst = int(os.getenv('SYNC_LEGACY_FRESH_BURST_TOKENS', '10'))
        hourly = int(os.getenv('SYNC_LEGACY_FRESH_HOURLY_TOKENS', '60'))
        # Bad/zero config closes promotion instead of disabling the limiter.
        if not 1 <= burst <= 60 or not 1 <= hourly <= 120:
            return replace(decision, lane=SyncLane.BACKFILL, reason=reason)
        if cost > burst:
            return replace(decision, lane=SyncLane.BACKFILL, reason='legacy_fresh_budget_exceeded')
        allowed = _get_redis_client().eval(
            _RESERVE_SCRIPT, 1, stage.redis_key(f'sync_legacy_fresh:budget:{uid}'), burst, hourly, cost
        )
        if int(allowed) == 1:
            return decision
        reason = 'legacy_fresh_budget_exceeded'
    except Exception as error:
        logger.warning('event=sync_legacy_fresh_budget outcome=unavailable exception_type=%s', type(error).__name__)
    return replace(decision, lane=SyncLane.BACKFILL, reason=reason)
