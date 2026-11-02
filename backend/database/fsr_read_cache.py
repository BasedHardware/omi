"""Default-off serving caches with request lifetime and writer generation fences.

Redis is an optimization only. A writer token is deliberately not expired: a
crashed writer sacrifices cache hits for that user rather than reopening an
entitlement or usage race. TTL caps bound staleness even when both invalidations fail.
"""

import copy
import json
import inspect
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache, wraps
from typing import Any

from config.firestore_read_levers import lever_enabled
from database import redis_db
from database.firestore_cache_metrics import record_request
from database.fsr_cache_telemetry import record_fallback

logger = logging.getLogger(__name__)


@dataclass
class RequestReads:
    values: dict = field(default_factory=dict)
    lock: Any = field(default_factory=threading.RLock)
    closed: bool = False


_request: ContextVar[RequestReads | None] = ContextVar('s4_request_reads', default=None)
_bypass: ContextVar[bool] = ContextVar('s4_fresh_reads', default=False)
_fresh_families: ContextVar[frozenset[str]] = ContextVar('s4_fresh_families', default=frozenset())


async def request_read_scope():
    """Async FastAPI dependency: children in the sync pool share this holder."""
    holder = RequestReads()
    token = _request.set(holder)
    try:
        yield
    finally:
        with holder.lock:
            holder.closed = True
            holder.values.clear()
        try:
            _request.reset(token)
        except ValueError:
            # FastAPI may tear down yield dependencies in another Context (streaming responses);
            # the closed holder already stops reuse there.
            pass


@contextmanager
def fresh_reads():
    """Purchases and payment recovery must always consult durable state."""
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


@contextmanager
def fresh_cache_reads(uid, *families):
    """Fresh entitlements for client payment refreshes, retaining request dedupe."""
    if lever_enabled('request_read_dedupe', uid) or any(lever_enabled(family, uid) for family in families):
        _forget(uid)  # Auth may already have memoized a cached BYOK/user snapshot.
    token = _fresh_families.set(_fresh_families.get().union(families))
    try:
        yield
    finally:
        _fresh_families.reset(token)


def fresh_reader(fn):
    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def async_wrapped(*args, **kwargs):
            with fresh_reads():
                return await fn(*args, **kwargs)

        return async_wrapped

    @wraps(fn)
    def wrapped(*args, **kwargs):
        with fresh_reads():
            return fn(*args, **kwargs)

    return wrapped


def memo(uid, key, fetch):
    holder = _request.get()
    if _bypass.get() or holder is None or holder.closed or not lever_enabled('request_read_dedupe', uid):
        return fetch()
    with holder.lock:
        if holder.closed:
            return fetch()
        scoped_key = (uid, key)
        if scoped_key not in holder.values:
            _event('request_read_dedupe', 'miss')
            holder.values[scoped_key] = copy.deepcopy(fetch())
        else:
            _event('request_read_dedupe', 'hit')
        return copy.deepcopy(holder.values[scoped_key])


def user_snapshot(uid, client, fields=None):
    # Only opted-in requests use a shared entitlement projection so subscription,
    # BYOK and the Stripe customer id share one user-document read without
    # retaining unrelated fields.
    holder = _request.get()
    if not _bypass.get() and holder is not None and not holder.closed and lever_enabled('request_read_dedupe', uid):
        # SDK snapshots contain clients/locks and cannot be deep-copied. Retain
        # the immutable snapshot and let to_dict() provide isolated payloads.
        with holder.lock:
            key = (uid, ('user_snapshot', plane_id(client)))
            if key not in holder.values:
                _event('request_read_dedupe', 'snapshot_miss')
                holder.values[key] = (
                    client.collection('users').document(uid).get(['subscription', 'byok', 'stripe_customer_id'])
                )
            else:
                _event('request_read_dedupe', 'snapshot_hit')
            return holder.values[key]
    ref = client.collection('users').document(uid)
    return ref.get(fields) if fields is not None else ref.get()


def plane_id(client):
    project = getattr(client, 'project', None)
    database = getattr(client, '_database', None)
    if isinstance(project, str) and isinstance(database, str):
        return json.dumps([project, database], separators=(',', ':'))
    return str(id(client))


def _forget(uid):
    holder = _request.get()
    if holder is not None:
        with holder.lock:
            for key in list(holder.values):
                if key[0] == uid:
                    del holder.values[key]


def forget_request_reads(uid):
    """Drop this request's memoized reads after a durable write.

    Request dedupe has no Redis generation of its own. Writers of a document
    that ``memo`` may have already returned call this so a later read in the
    same request sees the write. No request scope is a no-op.
    """
    _forget(uid)


# These are correctness limits, not merely tunable defaults.
_CACHE_TTLS = {
    'deletion_marker_cache': ('FSR_DELETION_NEGATIVE_TTL_SECONDS', 30),
    'subscription_cache': ('FSR_SUBSCRIPTION_TTL_SECONDS', 60),
    'usage_month_cache': ('FSR_USAGE_MONTH_TTL_SECONDS', 60),
    'serving_config_cache': ('FSR_SERVING_CONFIG_TTL_SECONDS', 300),
}


def ttl(name, default):
    maximum = next((limit for env, limit in _CACHE_TTLS.values() if env == name), None)
    try:
        value = max(1, int(os.getenv(name, str(default))))
    except ValueError:
        value = max(1, default)
    return min(value, maximum) if maximum is not None else value


@lru_cache(maxsize=1)
def _redis():
    # Optional caches and writer fences must not hold auth or durable writes open.
    return redis_db.create_bounded_redis_client(0.1)


def _failure(family, operation):
    _event(family, operation + '_error')
    try:
        record_fallback(
            component='firestore_read_cache',
            from_mode=family,
            to_mode='firestore',
            reason=f'redis_{operation}_error',
            outcome='degraded',
            log=logger,
        )
    except Exception:
        logger.warning('Firestore read cache fallback family=%s operation=%s', family, operation)


def _event(family, result):
    try:
        record_request('fsr_s4_' + family, result)
    except Exception:
        pass  # Instrumentation cannot change the source-of-truth behavior.


def _generation_ttl(family):
    env_name, default = _CACHE_TTLS[family]
    return 2 * ttl(env_name, default)


def _root(family, uid):
    # JSON encoding prevents delimiter collisions in externally supplied UIDs.
    return 'fsr:s4:v2:' + json.dumps([family, uid], separators=(',', ':'))


_READ = """
if redis.call('SCARD', KEYS[2]) > 0 then return {} end
redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2])
local now = redis.call('TIME')
return {redis.call('GET', KEYS[1]), redis.call('GET', KEYS[3]) or '', now[1] * 1000 + math.floor(now[2] / 1000)}
"""
_PUBLISH = """
if redis.call('SCARD', KEYS[2]) == 0 and redis.call('GET', KEYS[1]) == ARGV[1] then
    local now = redis.call('TIME')
    local remaining = tonumber(ARGV[3]) - (now[1] * 1000 + math.floor(now[2] / 1000))
    if remaining > 0 then
        return redis.call('SET', KEYS[3], ARGV[2], 'PX', remaining)
    end
end
return 0
"""
_BEGIN = """
redis.call('SADD', KEYS[2], ARGV[1])
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
"""
_END = """
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
redis.call('SREM', KEYS[2], ARGV[1])
return 1
"""


def _decode(value):
    return value.decode() if isinstance(value, bytes) else value


def _json_default(value):
    if isinstance(value, datetime):
        return {'__s4_datetime__': value.isoformat()}
    raise TypeError('unsupported cache payload')


def _json_hook(value):
    if set(value) == {'__s4_datetime__'}:
        return datetime.fromisoformat(value['__s4_datetime__'])
    return value


def cached_read(family, uid, variant, fetch, *, seconds=60, cacheable=lambda value: True, validate=lambda value: True):
    """CAS publication prevents a read started before a write from repopulating."""
    if _bypass.get() or family in _fresh_families.get() or not lever_enabled(family, uid):
        return fetch()
    env_name, maximum = _CACHE_TTLS[family]
    seconds = min(max(1, seconds), ttl(env_name, maximum))
    root = _root(family, uid)
    keys = (root + ':generation', root + ':writers', root + ':data:' + variant)
    try:
        state = _redis().eval(_READ, 3, *keys, uuid.uuid4().hex, _generation_ttl(family))
        generation, raw, observed_ms = map(_decode, state) if state else (None, None, None)
        if generation is not None and raw:
            envelope = json.loads(raw, object_hook=_json_hook)
            if (
                envelope['generation'] == generation
                and cacheable(envelope['payload'])
                and validate(envelope['payload'])
            ):
                _event(family, 'hit')
                return copy.deepcopy(envelope['payload'])
    except Exception:
        _failure(family, 'read')
        return fetch()
    if generation is None:
        _event(family, 'writer_fenced')
        return fetch()
    _event(family, 'miss')
    started = time.monotonic()
    value = fetch()
    # A slow durable read must not extend the accepted age from observation.
    remaining_ms = int((seconds - (time.monotonic() - started)) * 1000)
    if remaining_ms > 0 and cacheable(value):
        try:
            encoded = json.dumps({'generation': generation, 'payload': value}, default=_json_default)
            # Redis time anchors expiry before the durable read: neither client clock
            # skew nor delayed serialization/network publication can extend the bound.
            deadline_ms = int(observed_ms or 0) + int(seconds * 1000)
            result = _redis().eval(_PUBLISH, 3, *keys, generation, encoded, deadline_ms)
            _event(family, 'publish' if result else 'publish_fenced')
        except Exception:
            _failure(family, 'publish')
    return copy.deepcopy(value)


@contextmanager
def writing(family, uid):
    """Invalidate both sides of a durable write, including same-request reads.

    The generation fence runs regardless of this writer's lever: readers on other revisions or cohorts may
    already be caching this UID, so only cache reads are cohort-gated.
    """
    _forget(uid)
    root = _root(family, uid)
    token = uuid.uuid4().hex
    begun = False
    try:
        _redis().eval(_BEGIN, 2, root + ':generation', root + ':writers', token, _generation_ttl(family))
        begun = True
    except Exception:
        _failure(family, 'invalidate')
    try:
        yield
    finally:
        _forget(uid)
        try:
            # Even when begin failed, advance the generation after the write.
            _redis().eval(
                _END, 2, root + ':generation', root + ':writers', token, uuid.uuid4().hex, _generation_ttl(family)
            )
            _event(family, 'invalidate')
        except Exception:
            _failure(family, 'invalidate')
            # A successful begin leaves a persistent writer fence on failure.
            if begun:
                logger.warning('Firestore read cache writer fence retained family=%s', family)


def cache_writer(family):
    def decorate(fn):
        @wraps(fn)
        def wrapped(uid, *args, **kwargs):
            with writing(family, uid):
                return fn(uid, *args, **kwargs)

        return wrapped

    return decorate


_configs = {}
_config_lock = threading.RLock()


def serving_config_key():
    host = os.getenv('HOSTNAME')
    if host:
        return host
    revision = os.getenv('K_REVISION')
    instance = os.getenv('INSTANCE_ID') or os.getenv('GAE_INSTANCE')
    return f'{revision}:{instance}' if revision and instance else None


def serving_config(name, fetch, *, identity=None):
    key = serving_config_key()
    if not lever_enabled('serving_config_cache', key):
        return fetch()
    with _config_lock:
        cache_key = (name, identity)
        entry = _configs.get(cache_key)
        if entry is not None and entry[0] > time.monotonic():
            _event('serving_config_cache', 'hit')
            return copy.deepcopy(entry[1])
        _event('serving_config_cache', 'miss')
        value = fetch()  # Exceptions never renew or return an expired entry.
        # Normally two entries per process; cap injected/test identities too.
        if len(_configs) >= 32:
            _configs.clear()
        _configs[cache_key] = (time.monotonic() + ttl('FSR_SERVING_CONFIG_TTL_SECONDS', 60), copy.deepcopy(value))
        return copy.deepcopy(value)
