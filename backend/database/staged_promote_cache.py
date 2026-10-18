"""Write-invalidated negative cache of the complete staged compatibility projection.

Only an empty marker is stored, never rows or response content. The route still
reads its account-generation fence on every poll. Writers keep a non-cacheable
fence until every overlapping mutation and compatibility invalidation completes.
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

TTL_SECONDS = 3600
VERSION_TTL_SECONDS = 7 * 86400
OPERATIONS = Counter(
    'omi_staged_promote_empty_cache_total',
    'Staged promote negative-cache operations by bounded outcome',
    ['outcome'],
)
logger = logging.getLogger(__name__)
BUSY = '!busy'

# These scripts never lock a writer. Tokens prevent overlapping/late completion
# from releasing another writer's fence. Busy and poisoned state deliberately
# has no expiry: uncertainty disables caching.
_READ_VERSION = """
if redis.call('EXISTS', KEYS[2]) == 1 then return '!busy' end
local version = redis.call('GET', KEYS[1])
if not version then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return ARGV[1]
end
return version
"""
_BEGIN_WRITE = """
redis.call('SET', KEYS[1], '!busy')
if redis.call('HGET', KEYS[2], 'poison') then return 0 end
redis.call('HSET', KEYS[2], ARGV[1], '1')
return 1
"""
_END_WRITE = """
redis.call('SET', KEYS[1], '!busy')
local tracked = redis.call('HGET', KEYS[2], ARGV[1])
if not tracked or ARGV[2] ~= '1' then
    redis.call('HSET', KEYS[2], 'poison', '1')
end
redis.call('HDEL', KEYS[2], ARGV[1])
if redis.call('HLEN', KEYS[2]) == 0 then
    redis.call('SET', KEYS[1], ARGV[3], 'EX', ARGV[4])
    return 1
end
return 0
"""


@functools.lru_cache(maxsize=1)
def _redis():
    return redis_db.create_bounded_redis_client(0.1)


def _version_key(uid: str) -> str:
    return 'staged-promote-empty:v1:version:{' + hashlib.sha256(uid.encode()).hexdigest() + '}'


def compatibility_version_key(uid: str) -> str:
    # Preserve the existing compatibility-cache namespace and random-token ABI.
    return f'fsr:s5:candidates:version:{uid}'


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


def rotate_compatibility_version(uid: str, *, client=None) -> bool:
    try:
        client = client if client is not None else _redis()
        if client.set(compatibility_version_key(uid), uuid4().hex, ex=VERSION_TTL_SECONDS):
            return True
    except Exception:
        pass
    _unavailable('invalidation_unavailable')
    return False


def _begin(uid: str) -> tuple[str, bool]:
    token = ''  # An unconfirmed ticket can only poison; it can never publish.
    try:
        token = uuid4().hex
        key = _version_key(uid)
        confirmed = _redis().eval(_BEGIN_WRITE, 2, key, key + ':writers', token) == 1
        return token, confirmed
    except Exception:
        _unavailable('invalidation_unavailable')
        # Completion poisons rather than publishing after an uncertain begin.
        return token, False


def _finish(uid: str, token: str, confirmed: bool) -> None:
    try:
        key = _version_key(uid)
        _redis().eval(_END_WRITE, 2, key, key + ':writers', token, int(confirmed), uuid4().hex, VERSION_TTL_SECONDS)
        OPERATIONS.labels(outcome='invalidated').inc()
    except Exception:
        # If the script did not run, BEGIN's busy fence remains. If it completed
        # but its reply was lost, publication required all dependencies first.
        _unavailable('invalidation_unavailable')


def invalidate_around_write(fn, *, invalidate_dependency=rotate_compatibility_version):
    @functools.wraps(fn)
    def wrapped(uid, *args, **kwargs):
        token, began = _begin(uid)
        try:
            return fn(uid, *args, **kwargs)
        finally:
            # A batch may commit a prefix before raising; preserve its error
            # while fencing both pre-write readers and readers during mutation.
            try:
                dependency_rotated = invalidate_dependency(uid)
            except Exception:
                _unavailable('invalidation_unavailable')
                dependency_rotated = False
            _finish(uid, token, began and dependency_rotated)

    return wrapped


def invalidate(uid: str) -> None:
    # Public one-shot invalidation uses the same dependency and overlap fences.
    invalidate_around_write(lambda owner: None)(uid)


def load_projection(uid: str, generation: int, loader) -> list[dict]:
    if os.getenv('OMI_STAGED_TASK_PROMOTE_EMPTY_CACHE_ENABLED', '').strip().lower() == 'false':
        return loader()
    long_ttl = os.getenv('OMI_STAGED_PROMOTE_LONG_TTL_ENABLED', '').strip().lower() != 'false'
    key: str | None = None
    try:
        client = _redis()
        version_key = _version_key(uid)
        version = client.eval(_READ_VERSION, 2, version_key, version_key + ':writers', uuid4().hex, VERSION_TTL_SECONDS)
        if version in (BUSY, BUSY.encode()):
            OPERATIONS.labels(outcome='bypass').inc()
            version = None
        if version:
            token = version.decode() if isinstance(version, bytes) else str(version)
            key = f'{version_key}:{generation}:{token}'
            if long_ttl:
                # Separate markers make disabling the lever immediately stop
                # reading existing hour-long entries. Writers fence both forms.
                key += ':hour'
            if client.get(key) in (b'1', '1') and client.get(version_key) == version:
                OPERATIONS.labels(outcome='hit').inc()
                return []
    except Exception:
        _unavailable('unavailable')
        return loader()

    if key is None:
        # Run the origin outside this try so an origin error is never retried.
        return loader()

    OPERATIONS.labels(outcome='miss').inc()
    # Expiry belongs to the origin projection, never completion or queue time.
    # PXAT also prevents socket delay after SET from extending that deadline.
    ttl = TTL_SECONDS if long_ttl else 90
    expires_ms = int((time.time() + ttl) * 1000)
    started = time.monotonic()
    items = loader()
    if items:
        return items
    try:
        if time.monotonic() - started >= ttl or time.time() * 1000 >= expires_ms:
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
