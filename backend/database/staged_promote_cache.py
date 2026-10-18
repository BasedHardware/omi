"""Write-invalidated negative cache of the complete staged compatibility projection.

Only an empty marker is stored, never rows or response content. The route still
reads its account-generation fence on every poll. Writers rotate an independent
random UID version before mutation and in finally, including partial failures.
"""

import functools
import hashlib
import logging
import os
import time
from uuid import uuid4

from prometheus_client import Counter

from database import redis_db
from utils.observability.fallback import record_fallback

TTL_SECONDS = 90
VERSION_TTL_SECONDS = 7 * 86400
OPERATIONS = Counter(
    'omi_staged_promote_empty_cache_total',
    'Staged promote negative-cache operations by bounded outcome',
    ['outcome'],
)
logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _redis():
    return redis_db.create_bounded_redis_client(0.1)


def _version_key(uid: str) -> str:
    return 'staged-promote-empty:v1:version:' + hashlib.sha256(uid.encode()).hexdigest()


def _unavailable(outcome: str) -> None:
    OPERATIONS.labels(outcome=outcome).inc()
    record_fallback(
        component='firestore_read',
        from_mode='cached',
        to_mode='uncached',
        reason='unavailable',
        outcome='degraded' if outcome == 'invalidation_unavailable' else 'recovered',
        log=logger,
    )


def invalidate(uid: str) -> None:
    # Unconditional even on flag-off writers: other revisions can have entries.
    try:
        _redis().set(_version_key(uid), uuid4().hex, ex=VERSION_TTL_SECONDS)
        OPERATIONS.labels(outcome='invalidated').inc()
    except Exception:
        _unavailable('invalidation_unavailable')


def invalidate_around_write(fn):
    @functools.wraps(fn)
    def wrapped(uid, *args, **kwargs):
        invalidate(uid)
        try:
            return fn(uid, *args, **kwargs)
        finally:
            # A batch may commit a prefix before raising; preserve its error
            # while fencing both pre-write readers and readers during mutation.
            invalidate(uid)

    return wrapped


def load_projection(uid: str, generation: int, loader) -> list[dict]:
    if os.getenv('OMI_STAGED_TASK_PROMOTE_EMPTY_CACHE_ENABLED', '').strip().lower() == 'false':
        return loader()
    try:
        client = _redis()
        version_key = _version_key(uid)
        client.set(version_key, uuid4().hex, nx=True, ex=VERSION_TTL_SECONDS)
        version = client.get(version_key)
        if not version:
            # Eviction never means a fixed, reusable default token.
            raise ValueError('cache version unavailable')
        token = version.decode() if isinstance(version, bytes) else str(version)
        key = f'{version_key}:{generation}:{token}'
        if client.get(key) in (b'1', '1') and client.get(version_key) == version:
            OPERATIONS.labels(outcome='hit').inc()
            return []
    except Exception:
        _unavailable('unavailable')
        return loader()

    OPERATIONS.labels(outcome='miss').inc()
    # Expiry belongs to the origin projection, never completion or queue time.
    # PXAT also prevents socket delay after SET from extending that deadline.
    expires_ms = int((time.time() + TTL_SECONDS) * 1000)
    started = time.monotonic()
    items = loader()
    if items:
        return items
    try:
        if time.monotonic() - started >= TTL_SECONDS or time.time() * 1000 >= expires_ms:
            OPERATIONS.labels(outcome='expired').inc()
        elif client.get(version_key) != version:
            OPERATIONS.labels(outcome='version_changed').inc()
        else:
            # Always address the captured version. A write after the comparison
            # can only strand this fill at an unreachable old key, never bless it.
            client.set(key, '1', pxat=expires_ms)
            OPERATIONS.labels(outcome='stored').inc()
    except Exception:
        _unavailable('unavailable')
    return items
