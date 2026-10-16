"""Versioned compatibility-scan cache; task Candidate writers invalidate it.

Only staged-compatible task/create records are cached. Workstream resolution
writes outside candidates.py cannot change this projection. Historical staged
rows and the account-generation fence are always read by the caller.
"""

import functools
import json
import logging
import os
from uuid import uuid4

from prometheus_client import Counter
from pydantic import ValidationError
from redis.exceptions import RedisError

from database import redis_db
from database.read_boundary import MalformedDocError, parse_payload_strict
from models.candidate import CandidateRecord
from utils.firestore_read_levers import lever_enabled
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
CACHE_OPERATIONS = Counter(
    'omi_candidates_compatibility_cache_total',
    'Candidate compatibility cache operations by bounded outcome',
    ['outcome'],
)


def _cache_unavailable(outcome: str) -> None:
    CACHE_OPERATIONS.labels(outcome=outcome).inc()
    record_fallback(
        component='firestore_read',
        from_mode='cached',
        to_mode='uncached',
        reason='unavailable',
        outcome='degraded' if outcome == 'invalidation_unavailable' else 'recovered',
        log=logger,
    )


def _ttl() -> int:
    try:
        return max(0, min(300, int(os.getenv('CANDIDATES_COMPATIBILITY_CACHE_TTL_SECONDS', '30'))))
    except ValueError:
        return 30


def _version_key(uid: str) -> str:
    return f'fsr:s5:candidates:version:{uid}'


def invalidate_after_write(fn):
    @functools.wraps(fn)
    def wrapped(uid, *args, **kwargs):
        result = fn(uid, *args, **kwargs)
        if lever_enabled('candidates_page', uid):
            try:
                # Random generations cannot expire back onto a live entry or
                # reuse an old counter following version-key eviction.
                redis_db.r.set(_version_key(uid), uuid4().hex, ex=7 * 86400)
                CACHE_OPERATIONS.labels(outcome='invalidated').inc()
            except RedisError:
                _cache_unavailable('invalidation_unavailable')
                logger.warning('Candidate compatibility cache invalidation unavailable')
        return result

    return wrapped


def load_compatibility_candidates(uid: str, generation: int, loader) -> list[CandidateRecord]:
    ttl = _ttl() if lever_enabled('candidates_page', uid) else 0
    if ttl <= 0:
        return loader()
    try:
        version_key = _version_key(uid)
        redis_db.r.set(version_key, uuid4().hex, nx=True, ex=7 * 86400)
        version = redis_db.r.get(version_key)
        if not version:
            return loader()
        token = version.decode() if isinstance(version, bytes) else str(version)
        key = f'fsr:s5:candidates:{uid}:{generation}:{token}'
        raw = redis_db.r.get(key)
        if raw:
            try:
                payload = json.loads(raw)
                if isinstance(payload, list):
                    records = [
                        parse_payload_strict(CandidateRecord, row, document_path=f'redis:{key}') for row in payload
                    ]
                    if (
                        all(row.account_generation == generation for row in records)
                        and redis_db.r.get(version_key) == version
                    ):
                        CACHE_OPERATIONS.labels(outcome='hit').inc()
                        return records
            except (ValueError, TypeError, ValidationError, MalformedDocError):
                pass
    except RedisError:
        _cache_unavailable('unavailable')
        logger.warning('Candidate compatibility cache read unavailable')
        return loader()

    CACHE_OPERATIONS.labels(outcome='miss').inc()
    records = loader()
    try:
        # Always address the version captured BEFORE Firestore. A concurrent
        # write cannot bless an older scan under its new invalidation version.
        if redis_db.r.get(version_key) == version:
            redis_db.r.set(key, json.dumps([row.model_dump(mode='json') for row in records]), ex=ttl)
    except (RedisError, TypeError, ValueError):
        # Fill is best-effort: a serialization or Redis fault must never fail a request the scan already served.
        _cache_unavailable('unavailable')
        logger.warning('Candidate compatibility cache fill unavailable')
    return records
