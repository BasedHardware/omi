"""Shared, token-certified batch decisions. Redis is optional acceleration."""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from math import floor, isfinite

from prometheus_client import Counter
import redis

from database.redis_connection import create_bounded_redis_client
from utils.observability.fallback import record_fallback

TTL_SECONDS = 300
MAX_IDS = 256
MAX_BYTES = 20 * 1024
REDIS_RETRY_SECONDS = 5
_redis_retry_at = 0.0
OUTCOMES = Counter(
    'omi_batch_pipeline_privacy_owner_cache_total',
    'Shared batch privacy cache outcomes',
    ['outcome'],
)
SHADOW = Counter(
    'omi_batch_pipeline_privacy_owner_shadow_total',
    'Tokenless candidate comparisons against current authority',
    ['outcome'],
)
for _outcome in ('match', 'authority_changed', 'mismatch', 'unavailable'):
    SHADOW.labels(_outcome)


@dataclass(frozen=True)
class Decision:
    started: float
    version: tuple[str, str, int]
    generation: int


@lru_cache(maxsize=1)
def _redis():
    return create_bounded_redis_client(0.05)


def available(client) -> bool:
    return (
        bool(os.getenv('REDIS_DB_HOST'))
        and isinstance(getattr(client, '_database_string', None), str)
        and not getattr(client, '_emulator_host', None)
        and time.monotonic() >= _redis_retry_at
    )


def _key(client, owner: str) -> str:
    scope = hashlib.sha256(client._database_string.encode()).hexdigest()
    return f'batch-privacy-owner:v1:{scope}:{owner}'


def _coverage(ids) -> frozenset[str]:
    return frozenset(hashlib.sha256(cid.encode()).hexdigest() for cid in ids)


def _fallback(error: Exception, *, outcome: str) -> None:
    global _redis_retry_at
    if isinstance(error, redis.RedisError):
        _redis_retry_at = time.monotonic() + REDIS_RETRY_SECONDS
    OUTCOMES.labels(outcome).inc()
    record_fallback(
        component='batch_pipeline_privacy',
        from_mode='redis_owner_cache',
        to_mode='transactional_authority',
        reason='unavailable',
        outcome='degraded',
    )


def read(client, owner: str, ids, expected_generation: int | None, *, shadow: bool = False) -> Decision | None:
    key = _key(client, owner)
    if len(ids) > MAX_IDS:
        OUTCOMES.labels('uncovered').inc()
        return None
    try:
        connection = _redis()
        OUTCOMES.labels('shadow_get_attempt' if shadow else 'certified_get_attempt').inc()
        raw = connection.get(key)
        if raw is None:
            OUTCOMES.labels('miss').inc()
            return None
        if len(raw) > MAX_BYTES:
            raise ValueError('oversized cache entry')
        started, (token, revision, nanos), generation, covered = json.loads(raw)
        if (
            type(started) not in (int, float)
            or not isfinite(started)
            or not isinstance(token, str)
            or not isinstance(revision, str)
            or type(nanos) is not int
            or type(generation) is not int
            or not isinstance(covered, list)
            or len(covered) > MAX_IDS
            or any(not isinstance(value, str) or len(value) != 64 for value in covered)
        ):
            raise ValueError('invalid cache entry')
        age = time.time() - started
        if not 0 <= age < TTL_SECONDS:
            OUTCOMES.labels('expired').inc()
            return None
        coverage = frozenset(covered)
        if (expected_generation is not None and expected_generation != generation) or not _coverage(ids) <= coverage:
            OUTCOMES.labels('uncovered').inc()
            return None
        OUTCOMES.labels('covered').inc()
        return Decision(started, (token, revision, nanos), generation)
    except (redis.RedisError, ValueError, TypeError, OverflowError) as error:
        _fallback(error, outcome='get_error')
        return None


def store(client, owner: str, ids, version, generation: int, *, started: float) -> None:
    if len(ids) > MAX_IDS or time.monotonic() < _redis_retry_at:
        return
    key = _key(client, owner)
    remaining = floor((started + TTL_SECONDS - time.time()) * 1000)
    if not 0 < remaining <= TTL_SECONDS * 1000:
        return
    payload = json.dumps((started, version, generation, sorted(_coverage(ids))), separators=(',', ':'))
    try:
        _redis().set(key, payload, px=remaining)
        OUTCOMES.labels('stored').inc()
    except (redis.RedisError, ValueError) as error:
        _fallback(error, outcome='set_error')


def compare(candidate: Decision | None, live_version, live_generation: int | None) -> None:
    if candidate is None:
        return
    if live_version is None:
        outcome = 'unavailable'
    elif live_generation == candidate.generation:
        outcome = 'match'
    else:
        # A changed revision alone cannot excuse a mismatch: the authoritative
        # mutation must be newer than the actual authority read that filled Redis.
        revision = datetime.fromisoformat(live_version[1]).timestamp()
        allowed = (
            live_version != candidate.version
            and candidate.started < revision <= time.time()
            and revision - candidate.started < TTL_SECONDS
        )
        outcome = 'authority_changed' if allowed else 'mismatch'
    SHADOW.labels(outcome).inc()
