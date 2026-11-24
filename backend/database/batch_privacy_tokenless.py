"""Expiring Redis evidence for a projection precheck. Never a write credential."""

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import hashlib
import json
import math
import os
import time
from uuid import uuid4

from prometheus_client import Counter
from redis.exceptions import RedisError

from config.firestore_read_levers import lever_enabled, lever_percent
from database.batch_account_authority_schema import PRIVACY_COLLECTION
from database.privacy_ttl_cache import disabled
from database.redis_connection import create_bounded_redis_client

WINDOW = 300
CLOCK_MARGIN = 5
MAX_IDS = 256
MAX_BYTES = 20 * 1024
CACHE = Counter('omi_batch_pipeline_tokenless_cache_total', 'Tokenless precheck observations', ['site', 'outcome'])
SHADOW = Counter('omi_batch_pipeline_tokenless_shadow_total', 'Tokenless versus live authority', ['site', 'outcome'])
INVALIDATION = Counter('omi_batch_pipeline_tokenless_invalidation_total', 'Post-commit owner markers', ['outcome'])


@lru_cache(maxsize=1)
def _redis():
    return create_bounded_redis_client(0.05)


def mode(client, uid, *, precheck):
    shadow = lever_enabled('bpp_tokenless_owner_shadow', uid)
    enforce = (
        precheck
        and lever_percent('bpp_tokenless_owner_shadow') == 0
        and lever_enabled('bpp_tokenless_owner_cache', uid)
    )
    if not (
        (shadow or enforce)
        and lever_percent('privacy_checks_shadow') == 0
        and lever_percent('bpp_shared_owner_shadow') == 0
        and os.getenv('REDIS_DB_HOST')
        and not getattr(client, '_emulator_host', None)
        and isinstance(getattr(client, '_database_string', None), str)
        and not disabled()
    ):
        return None
    return 'shadow' if shadow else 'enforce'


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _key(database, owner):
    return f'batch-privacy-precheck:v1:{_hash(database)}:{owner}'


def _valid_ids(ids, *, allow_empty=False):
    return (
        (allow_empty or bool(ids))
        and len(ids) <= MAX_IDS
        and all(isinstance(value, str) and 0 < len(value.encode()) <= 256 and '/' not in value for value in ids)
    )


def snapshot_timestamp(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        return None
    try:
        stamp = value.timestamp()
    except (OverflowError, OSError, ValueError):
        return None
    return stamp if math.isfinite(stamp) else None


@dataclass(frozen=True)
class EnforcedHit:
    ids: frozenset[str]
    generation: int
    read_at: float
    deadline: float


@dataclass(frozen=True)
class Probe:
    key: str
    raw: bytes | None
    ids: tuple[str, ...]
    generation: int
    started: float
    site: str

    def candidate(self, read_time):
        """Return the evidence timestamp and deadline if this exact scope is usable now."""
        now = time.time()
        stamp = snapshot_timestamp(read_time)
        if stamp is None or abs(stamp - now) > CLOCK_MARGIN:
            CACHE.labels(self.site, 'clock_uncertain').inc()
            return None
        if not self.raw or self.raw.startswith(b'changed:'):
            return None
        try:
            key, generation, ids, covered, started, read_at, deadline = json.loads(self.raw)
            if (
                key != self.key
                or type(generation) is not int
                or generation != self.generation
                or ids != list(self.ids)
                or not isinstance(covered, list)
                or not 0 < len(covered) <= MAX_IDS
                or any(not isinstance(value, str) or len(value) != 64 for value in covered)
                or not set(ids) <= set(covered)
                or type(started) not in (float, int)
                or not math.isfinite(started)
                or type(read_at) not in (int, float)
                or not started <= read_at <= started + CLOCK_MARGIN
                or deadline != started + WINDOW
            ):
                raise ValueError('invalid precheck proof')
            if read_at > stamp or max(stamp, now) >= deadline:
                CACHE.labels(self.site, 'expired_or_future').inc()
                return None
            return read_at, deadline
        except (ValueError, TypeError, OverflowError):
            CACHE.labels(self.site, 'invalid_or_uncovered').inc()
            return None

    def observe(self, snapshot, candidate, *, allowed, verified, version):
        if candidate is not None:
            revision = snapshot_timestamp(getattr(snapshot, 'update_time', None))
            if allowed:
                outcome = 'match'
            elif revision is None:
                outcome = 'unavailable'
            elif candidate[0] < revision <= min(candidate[1], time.time()):
                outcome = 'authority_changed'
            else:
                outcome = 'mismatch'
            SHADOW.labels(self.site, outcome).inc()
            # Even in shadow, a cache hit never renews its original evidence.
            return
        if not (allowed and version and (self.raw is None or not self.raw.startswith(b'changed:'))):
            return
        stamp = snapshot_timestamp(getattr(snapshot, 'read_time', None))
        if stamp is None or abs(stamp - self.started) > CLOCK_MARGIN or not _valid_ids(verified):
            return
        if self.raw:
            try:
                prior_read_at = json.loads(self.raw)[5]
                if type(prior_read_at) in (float, int) and stamp <= prior_read_at:
                    return  # A slower transaction must never replace newer evidence.
            except (ValueError, TypeError, KeyError, IndexError):
                pass
        scope = sorted(_hash(value) for value in verified)
        if not set(self.ids) <= set(scope):
            return
        started = min(stamp, self.started)
        deadline = started + WINDOW
        remaining = math.floor((deadline - time.time()) * 1000)
        if not 0 < remaining <= WINDOW * 1000:
            return
        payload = json.dumps(
            [self.key, self.generation, self.ids, scope, started, stamp, deadline], separators=(',', ':')
        )
        try:
            # Compare the prior state and replace it atomically. A post-commit
            # marker wins against an older walk even if it read an empty key.
            with _redis().pipeline() as pipe:
                pipe.watch(self.key)
                if pipe.get(self.key) != self.raw:
                    return
                pipe.multi()
                pipe.set(self.key, payload, px=remaining)
                pipe.execute()
            CACHE.labels(self.site, 'stored').inc()
        except (RedisError, ValueError):
            CACHE.labels(self.site, 'fill_fallback').inc()


def lookup(client, owner, ids, generation, site):
    if type(generation) is not int or generation < 0 or not _valid_ids(ids):
        return None
    key = _key(client._database_string, owner)
    started = time.time()
    CACHE.labels(site, 'lookup').inc()
    try:
        raw = _redis().get(key)
        if raw is not None and (not isinstance(raw, bytes) or len(raw) > MAX_BYTES):
            CACHE.labels(site, 'invalid_or_uncovered').inc()
            return None
        if raw and raw.startswith(b'changed:'):
            CACHE.labels(site, 'recently_changed').inc()
        return Probe(key, raw, tuple(sorted(_hash(value) for value in ids)), generation, started, site)
    except (RedisError, ValueError):
        CACHE.labels(site, 'lookup_fallback').inc()
        return None


def invalidate(paths):
    """Overwrite proof after acknowledged authority commits, even on reader-off roles."""
    if not os.getenv('REDIS_DB_HOST') or os.getenv('FIRESTORE_EMULATOR_HOST'):
        return
    try:
        with _redis().pipeline(transaction=False) as pipe:
            for path in paths:
                database, _, owner = path.partition(f'/documents/{PRIVACY_COLLECTION}/')
                pipe.set(_key(database, owner), 'changed:' + uuid4().hex, ex=WINDOW + 2 * CLOCK_MARGIN)
            results = pipe.execute(raise_on_error=False)
        for result in results:
            INVALIDATION.labels('marked' if result is True else 'error').inc()
    except (RedisError, ValueError):
        INVALIDATION.labels('error').inc(len(paths))
