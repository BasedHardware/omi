"""Redis owner decisions for token certification and bounded projection prechecks."""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from math import floor, isfinite

from prometheus_client import Counter
from redis.exceptions import RedisError, WatchError

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


def _fallback(error: Exception, *, outcome: str, counter: Counter = OUTCOMES) -> None:
    global _redis_retry_at
    if isinstance(error, RedisError):
        _redis_retry_at = time.monotonic() + REDIS_RETRY_SECONDS
    counter.labels(outcome).inc()
    record_fallback(
        component='batch_pipeline_privacy',
        from_mode='redis_owner_cache',
        to_mode='transactional_authority',
        reason='unavailable',
        outcome='degraded',
    )


def _decision(payload) -> tuple[Decision, frozenset[str]]:
    started, (token, revision, nanos), generation, covered = payload
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
    return Decision(started, (token, revision, nanos), generation), frozenset(covered)


def read(client, owner: str, ids, expected_generation: int | None, *, shadow: bool = False) -> Decision | None:
    key = _key(client, owner)
    if len(ids) > MAX_IDS:
        OUTCOMES.labels('uncovered').inc()
        return None
    try:
        redis = _redis()
        OUTCOMES.labels('shadow_get_attempt' if shadow else 'certified_get_attempt').inc()
        raw = redis.get(key)
        if raw is None:
            OUTCOMES.labels('miss').inc()
            return None
        if len(raw) > MAX_BYTES:
            raise ValueError('oversized cache entry')
        candidate, coverage = _decision(json.loads(raw))
        age = time.time() - candidate.started
        if not 0 <= age < TTL_SECONDS:
            OUTCOMES.labels('expired').inc()
            return None
        if (expected_generation is not None and expected_generation != candidate.generation) or not _coverage(
            ids
        ) <= coverage:
            OUTCOMES.labels('uncovered').inc()
            return None
        OUTCOMES.labels('covered').inc()
        return candidate
    except (RedisError, ValueError, TypeError, OverflowError) as error:
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
    except (RedisError, ValueError) as error:
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


# One Redis cell per owner holds the revision of its most recent invalidation
# and the decision. Eviction therefore cannot leave behind a detached ALLOW.
TOKENLESS = Counter(
    'omi_batch_pipeline_privacy_tokenless_owner_cache_total',
    'Five-minute batch owner decision cache outcomes',
    ['outcome'],
)
TOKENLESS_SHADOW = Counter(
    'omi_batch_pipeline_privacy_tokenless_owner_shadow_total',
    'Five-minute batch owner decisions compared with live authority',
    ['outcome'],
)
for _outcome in ('match', 'changed_within_window', 'mismatch_outside_window', 'unavailable'):
    TOKENLESS_SHADOW.labels(_outcome)


@dataclass(frozen=True)
class TokenlessLookup:
    key: str
    raw: bytes | None
    changed: int
    decision: Decision | None


def _tokenless_key(database: str, owner: str) -> str:
    return f'batch-privacy-window:v1:{database}:{owner}'


def _revision(value: datetime) -> int:
    return int(value.timestamp()) * 1_000_000_000 + getattr(value, 'nanosecond', value.microsecond * 1000)


def _cell(raw: bytes | None):
    if raw is None:
        return 0, None
    if len(raw) > MAX_BYTES:
        raise ValueError('oversized tokenless privacy entry')
    changed, payload = json.loads(raw)
    if type(changed) is not int or changed < 0:
        raise ValueError('invalid tokenless privacy revision')
    return changed, payload


def read_tokenless(client, owner: str, ids: frozenset[str], expected_generation: int | None) -> TokenlessLookup | None:
    TOKENLESS.labels('eligible').inc()
    if len(ids) > MAX_IDS:
        TOKENLESS.labels('uncovered').inc()
        return None
    try:
        key = _tokenless_key(client._database_string, owner)
        raw = _redis().get(key)
        changed, payload = _cell(raw)
        if payload is None:
            TOKENLESS.labels('invalidated' if changed else 'miss').inc()
            return TokenlessLookup(key, raw, changed, None)
        candidate, coverage = _decision(payload)
        decision = None
        if not 0 <= time.time() - candidate.started < TTL_SECONDS:
            TOKENLESS.labels('expired').inc()
        elif (expected_generation is not None and expected_generation != candidate.generation) or not _coverage(
            ids
        ) <= coverage:
            TOKENLESS.labels('uncovered').inc()
        else:
            TOKENLESS.labels('covered').inc()
            decision = candidate
        return TokenlessLookup(key, raw, changed, decision)
    except (RedisError, ValueError, TypeError, OverflowError) as error:
        _fallback(error, outcome='get_error', counter=TOKENLESS)
        return None


def store_tokenless(lookup: TokenlessLookup, ids: frozenset[str], snapshot, version, generation: int, started: float):
    # A Firestore transaction may have fixed its view before the Redis lookup.
    # Do not republish that view after an invalidation we have already seen.
    read_time = getattr(snapshot, 'read_time', None)
    if len(ids) > MAX_IDS or read_time is None or _revision(read_time) < lookup.changed:
        return
    started = min(started, read_time.timestamp())
    payload = json.dumps(
        (lookup.changed, (started, version, generation, sorted(_coverage(ids)))), separators=(',', ':')
    )
    try:
        with _redis().pipeline() as pipe:
            pipe.watch(lookup.key)
            if pipe.get(lookup.key) != lookup.raw:
                TOKENLESS.labels('fill_race').inc()
                return
            remaining = floor((started + TTL_SECONDS - time.time()) * 1000)
            if not 0 < remaining <= TTL_SECONDS * 1000:
                return
            pipe.multi()
            pipe.set(lookup.key, payload, px=remaining)
            pipe.execute()
        TOKENLESS.labels('stored').inc()
    except WatchError:
        TOKENLESS.labels('fill_race').inc()
    except (RedisError, ValueError) as error:
        _fallback(error, outcome='set_error', counter=TOKENLESS)


def invalidate_tokenless(paths, commit_time: datetime) -> None:
    """Invalidate after an acknowledged authority commit; errors leave the hard TTL."""
    if not os.getenv('REDIS_DB_HOST') or time.monotonic() < _redis_retry_at:
        return
    revision = _revision(commit_time)
    for path in paths:
        database, owner = path.split('/documents/batch_pipeline_privacy/', 1)
        key = _tokenless_key(database, owner)
        for _attempt in range(3):
            try:
                with _redis().pipeline() as pipe:
                    pipe.watch(key)
                    changed, _ = _cell(pipe.get(key))
                    if changed >= revision:
                        break
                    pipe.multi()
                    # The marker outlives every pre-change decision. A cache
                    # refill may replace it only from a post-change snapshot.
                    pipe.set(key, json.dumps((revision, None)), ex=TTL_SECONDS + 30)
                    pipe.execute()
                TOKENLESS.labels('invalidation').inc()
                break
            except WatchError:
                continue
            except (RedisError, ValueError, TypeError) as error:
                _fallback(error, outcome='invalidation_error', counter=TOKENLESS)
                if isinstance(error, RedisError):
                    return
                break
        else:
            TOKENLESS.labels('invalidation_race').inc()


def compare_tokenless(candidate: Decision | None, snapshot, version, generation: int | None) -> None:
    if candidate is None:
        return
    if generation == candidate.generation:
        outcome = 'match'
    else:
        changed_at = getattr(snapshot, 'update_time', None)
        now = time.time()
        within_window = (
            version != candidate.version
            and changed_at is not None
            and candidate.started < changed_at.timestamp() <= now < candidate.started + TTL_SECONDS
        )
        outcome = 'changed_within_window' if within_window else 'mismatch_outside_window'
    TOKENLESS_SHADOW.labels(outcome).inc()
