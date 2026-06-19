"""Conservative Redis read-through cache for Firestore projections.

The cache is intentionally projection-oriented. Do not use it to cache whole
``users/{uid}`` documents: user docs mix low-risk preferences with entitlement,
BYOK, privacy consent, and data-protection fields that require stricter
correctness guarantees.
"""

import base64
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional, cast

from database.redis_db import r
from database.firestore_cache_metrics import observe_fetch, observe_payload, record_request

logger = logging.getLogger(__name__)

_GLOBAL_VERSION = os.getenv('FIRESTORE_CACHE_GLOBAL_VERSION', '1')


@dataclass(frozen=True)
class CachePolicy:
    """Policy for one typed Firestore cache namespace."""

    namespace: str
    version: int = 1
    ttl_seconds: int = 60
    jitter_ratio: float = 0.10
    enabled_env_var: str = 'FIRESTORE_CACHE_ENABLED'
    max_payload_bytes: int = 256_000


def is_enabled(policy: CachePolicy) -> bool:
    """Return whether cache reads/writes are enabled for this policy.

    Global flag defaults to false. A per-namespace override can also enable or
    disable a single policy, e.g. FIRESTORE_CACHE_USER_LANGUAGE_ENABLED=true.
    """

    namespace_flag = f"FIRESTORE_CACHE_{policy.namespace.upper()}_ENABLED"
    namespace_value = os.getenv(namespace_flag)
    if namespace_value is not None:
        return namespace_value.lower() in {'1', 'true', 'yes', 'on'}
    return os.getenv(policy.enabled_env_var, '').lower() in {'1', 'true', 'yes', 'on'}


def make_cache_key(policy: CachePolicy, entity_id: str) -> str:
    """Build a deterministic, versioned key for a typed projection.

    Entity IDs are base64url encoded instead of sanitized with string
    replacement so cache keys are collision-free. For example, ``a:b`` and
    ``a_b`` must not map to the same Redis key because this cache can hold
    per-user projections.
    """

    encoded_id = base64.urlsafe_b64encode(str(entity_id).encode('utf-8')).decode('ascii').rstrip('=')
    return f'fs:v{_GLOBAL_VERSION}:{policy.namespace}:v{policy.version}:b64:{encoded_id}'


def invalidate(policy: CachePolicy, entity_id: str) -> None:
    """Best-effort invalidation. Redis failures are logged and swallowed."""
    if not is_enabled(policy):
        return

    key = make_cache_key(policy, entity_id)
    try:
        r.delete(key)
        record_request(policy.namespace, 'invalidate')
    except Exception as e:
        logger.warning('Firestore cache invalidate failed namespace=%s error=%s', policy.namespace, e)
        record_request(policy.namespace, 'invalidate_error')


def get_or_fetch(policy: CachePolicy, entity_id: str, fetch_fn: Callable[[], Any]) -> Any:
    """Return cached projection or call ``fetch_fn`` and populate Redis.

    Correctness source remains Firestore. If cache is disabled, Redis is down,
    the cached value is malformed/stale, or serialization fails, this function
    falls back to ``fetch_fn`` and returns its result.
    """

    if not is_enabled(policy):
        record_request(policy.namespace, 'disabled')
        return _fetch(policy, fetch_fn)

    key = make_cache_key(policy, entity_id)
    now = time.time()

    try:
        raw = r.get(key)
    except Exception as e:
        logger.warning('Firestore cache read failed namespace=%s error=%s', policy.namespace, e)
        record_request(policy.namespace, 'redis_error')
        return _fetch(policy, fetch_fn)

    if raw:
        try:
            raw_str = raw.decode('utf-8') if isinstance(raw, bytes) else cast(str, raw)
            envelope = json.loads(raw_str, object_hook=_json_object_hook)
            if envelope.get('v') == policy.version and envelope.get('fresh_until', 0) >= now:
                record_request(policy.namespace, 'hit')
                return envelope.get('payload')
            record_request(policy.namespace, 'stale')
        except Exception as e:
            logger.warning('Firestore cache decode failed namespace=%s error=%s', policy.namespace, e)
            record_request(policy.namespace, 'decode_error')
    else:
        record_request(policy.namespace, 'miss')

    payload = _fetch(policy, fetch_fn)
    now = time.time()
    _set(policy, key, payload, now)
    return payload


def _fetch(policy: CachePolicy, fetch_fn: Callable[[], Any]) -> Any:
    start = time.monotonic()
    try:
        return fetch_fn()
    finally:
        observe_fetch(policy.namespace, time.monotonic() - start)


def _ttl_with_jitter(policy: CachePolicy) -> int:
    ttl = max(1, policy.ttl_seconds)
    if policy.jitter_ratio <= 0:
        return ttl
    spread = max(1, int(ttl * policy.jitter_ratio))
    return max(1, ttl + random.randint(-spread, spread))


def _set(policy: CachePolicy, key: str, payload: Any, now: Optional[float] = None) -> None:
    now = now or time.time()
    ttl = _ttl_with_jitter(policy)
    envelope = {
        'v': policy.version,
        'kind': 'value',
        'created_at': now,
        'fresh_until': now + ttl,
        'payload': payload,
    }

    try:
        encoded = json.dumps(envelope, default=_json_default)
        payload_bytes = len(encoded.encode('utf-8'))
        observe_payload(policy.namespace, payload_bytes)
        if payload_bytes > policy.max_payload_bytes:
            record_request(policy.namespace, 'payload_too_large')
            return
        r.set(key, encoded, ex=ttl)
        record_request(policy.namespace, 'set')
    except Exception as e:
        logger.warning('Firestore cache set failed namespace=%s error=%s', policy.namespace, e)
        record_request(policy.namespace, 'set_error')


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return {'__firestore_cache_type__': 'datetime', 'iso': value.isoformat()}
    raise TypeError(f'Object of type {type(value).__name__} is not JSON serializable')


def _json_object_hook(value: dict) -> Any:
    if value.get('__firestore_cache_type__') == 'datetime':
        return datetime.fromisoformat(value['iso'])
    return value
