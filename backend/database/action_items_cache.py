"""Read-free repeat polls for ``GET /v1/action-items``.

Why this module exists
----------------------
``action_items_list`` was 48.8% of every billable Firestore document read in the
project (~$328/day) before #12258 exempted the ``action_items:list`` policy from
``RATE_LIMIT_BOOST`` and restored its 12/min per-uid cap. That cut the *frequency*
of the stale ``omi-windows`` hot loop from ~97 req/min to 12 and took the family
from ~6,600 docs/sec to ~690 docs/sec (24h mean, 2026-09-02).

What is left is not frequency, it is *fan-out*: the surviving traffic is a small
number of large-backlog accounts, and documents-per-operation rose from 54.5 to
~223 because the cheap requests are the ones the cap removed. Each remaining
allowed poll re-reads a whole backlog that did not change. A per-uid response
cache keyed on a write-bumped version turns those repeats into zero Firestore
reads, which is the only thing that moves this line further without asking a
client fleet we cannot observe to update.

Design
------
* **Key** — ``ail:{uid}:{version}:{query fingerprint}``. The version is a per-uid
  counter bumped by every action-item write, so a write invalidates every cached
  page for that user in one ``INCR`` with no key enumeration and no per-mutation
  invalidation list to keep in sync.
* **TTL is the safety net, not the mechanism.** If a writer is ever added that
  forgets to bump the version, the worst case is bounded staleness of
  ``ACTION_ITEMS_LIST_CACHE_TTL_SECONDS`` (default 30s), not a permanently wrong
  list. The version key's own TTL is deliberately far longer than any response
  TTL so a version cannot expire back onto a live cached entry.
* **Fail-open.** Redis is fail-open for first-party paths (backend/AGENTS.md).
  Every helper here swallows Redis errors and reports "no cache", which degrades
  to today's behaviour — a Firestore read — never to a wrong answer.
* **ETag** is derived from the cached body, so a client that sends
  ``If-None-Match`` gets a 304 with no body and no Firestore read.

Rollback: ``ACTION_ITEMS_LIST_CACHE_TTL_SECONDS=0`` disables the cache entirely
(reads go straight to Firestore) without a deploy of new code.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import logging
import os
from typing import Any, Dict, Optional

import redis as redis_pkg

from database import redis_db

try:  # pragma: no cover - exercised by the missing-module unit test
    from config.firestore_read_levers import lever_enabled
except ImportError:  # pragma: no cover
    # Environment tiers without the levers module (or a partially-synced checkout)
    # must not fail at import time. Treat every lever as disabled: the conservative
    # choice, since an unknown lever can only ever be an opt-in override.
    lever_enabled = None


# Every failure mode Redis can raise here. The module promises fail-open, so the
# except clauses must cover connection-level errors too (ConnectionError,
# OSError, socket.timeout) and not only the driver's own RedisError.
_REDIS_FAILURES: tuple = (redis_pkg.exceptions.RedisError,)
for _extra in (ConnectionError, OSError, TimeoutError, ValueError, TypeError):
    if _extra not in _REDIS_FAILURES:  # type: ignore[operator]
        _REDIS_FAILURES = _REDIS_FAILURES + (_extra,)  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Response TTL. 0 disables the cache (the documented rollback). Capped so a
# misconfigured value cannot make the list arbitrarily stale.
_TTL_MAX_SECONDS = 300
_TTL_DEFAULT_SECONDS = 30

# The version counter must outlive any response entry by a wide margin: if it
# expired while a cached page was still live, the counter would restart at 1 and
# could re-address that stale page. Seven days against a <=300s response TTL.
_VERSION_TTL_SECONDS = 7 * 24 * 3600

_VERSION_KEY_PREFIX = 'ail:ver'
_ENTRY_KEY_PREFIX = 'ail'

# Characters that must never appear in a Redis key. Whitespace is rejected
# outright (it is never meaningful in a uid and makes keys ambiguous), and the
# CRLF pair is rejected because it is the classic Redis protocol injection
# vector. Control characters are rejected for the same reason.
_FORBIDDEN_UID_CHARS = ('\r', '\n', ' ', '\t')


def _sanitize_uid(uid: Any) -> Optional[str]:
    """Return a safe uid, or ``None`` when the input cannot be used as a key part.

    Rejects non-strings, empty/whitespace-only values, and any uid containing
    characters that would let a caller shape the Redis key topology (or inject
    protocol bytes). Returning ``None`` (rather than raising) keeps every caller
    fail-open: an unusable uid simply disables caching for that request.
    """
    if not isinstance(uid, str):
        return None
    if not uid or not uid.strip():
        return None
    for char in _FORBIDDEN_UID_CHARS:
        if char in uid:
            return None
    return uid


def _lever_is_enabled(name: str, uid: str) -> bool:
    """Best-effort lever check that never raises when the levers module is absent."""
    if lever_enabled is None:
        return False
    try:
        return bool(lever_enabled(name, uid))
    except Exception:  # pragma: no cover - defensive: levers are advisory
        return False


@lru_cache(maxsize=1)
def _default_redis():
    """Lazy, bounded I/O for every best-effort cache operation."""
    return redis_db.create_bounded_redis_client(0.1)


def _redis(redis_client: Any = None):
    """Resolve the client to use: injected (tests) or the module default."""
    return redis_client if redis_client is not None else _default_redis()


def list_cache_ttl_seconds(uid: str = '', *, redis_client: Any = None) -> int:
    """Read the TTL at call time so the env var is a live operational knob."""
    del redis_client  # TTL is not Redis-dependent; kept for call-site symmetry
    raw = os.getenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', str(_TTL_DEFAULT_SECONDS)).strip()
    try:
        ttl = int(raw)
    except ValueError:
        logger.warning('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS=%r is not an integer; using default', raw)
        return _TTL_DEFAULT_SECONDS
    if ttl <= 0:
        return 0
    if uid and _lever_is_enabled('action_items_page', uid):
        override = os.getenv('ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS', str(ttl)).strip()
        try:
            ttl = int(override)
        except ValueError:
            logger.warning('ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS is not an integer; using base TTL')
    return max(0, min(ttl, _TTL_MAX_SECONDS))


def _version_key(uid: str) -> str:
    safe = _sanitize_uid(uid)
    if safe is None:
        raise ValueError('uid is not usable as a cache key part')
    return f'{_VERSION_KEY_PREFIX}:{safe}'


def bump_action_items_list_version(uid: str, *, redis_client: Any = None) -> None:
    """Invalidate every cached list page for ``uid``.

    Called from the write paths in ``database.action_items`` after the Firestore
    mutation has committed. Fail-open: a Redis outage means the cache simply
    keeps serving until its short TTL expires.
    """
    if _sanitize_uid(uid) is None:
        return
    try:
        key = _version_key(uid)
        pipe = _redis(redis_client).pipeline()
        pipe.incr(key)
        pipe.expire(key, _VERSION_TTL_SECONDS)
        pipe.execute()
    except _REDIS_FAILURES as e:
        logger.warning('action-items list cache: version bump failed uid=%s: %s', uid, e)


def get_action_items_list_version(uid: str, *, redis_client: Any = None) -> Optional[int]:
    """Current invalidation version, or ``None`` when Redis cannot answer.

    ``None`` means "do not use the cache for this request" — it is not the same
    as version 0, which is a legitimate never-written-yet user.
    """
    if _sanitize_uid(uid) is None:
        return None
    try:
        raw = _redis(redis_client).get(_version_key(uid))
    except _REDIS_FAILURES as e:
        logger.warning('action-items list cache: version read failed uid=%s: %s', uid, e)
        return None
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def list_cache_key(uid: str, version: int, params: Dict[str, Any], *, redis_client: Any = None) -> str:
    """Address one list page. Params are hashed so the key length is bounded."""
    del redis_client  # key shape does not depend on the client; kept for symmetry
    safe = _sanitize_uid(uid)
    if safe is None:
        raise ValueError('uid is not usable as a cache key part')
    fingerprint = hashlib.sha256(
        json.dumps(params, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()[:16]
    return f'{_ENTRY_KEY_PREFIX}:{safe}:{version}:{fingerprint}'


def compute_etag(body: Dict[str, Any]) -> str:
    """Weak ETag over the exact bytes the route would return."""
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8'))
    return f'W/"{digest.hexdigest()[:32]}"'


def read_cached_list(key: str, *, redis_client: Any = None) -> Optional[Dict[str, Any]]:
    """Return ``{"etag": str, "body": dict}`` or ``None``. Never raises."""
    try:
        raw = _redis(redis_client).get(key)
    except _REDIS_FAILURES as e:
        logger.warning('action-items list cache: read failed: %s', e)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or 'body' not in payload or 'etag' not in payload:
        return None
    return payload


def write_cached_list(key: str, *, body: Dict[str, Any], etag: str, ttl: int, redis_client: Any = None) -> None:
    """Store one list page. Never raises; a failed write just means a later miss."""
    if ttl <= 0:
        return
    try:
        _redis(redis_client).set(key, json.dumps({'etag': etag, 'body': body}, default=str), ex=ttl)
    except _REDIS_FAILURES as e:
        logger.warning('action-items list cache: write failed: %s', e)
    except (TypeError, ValueError) as e:
        logger.warning('action-items list cache: body not serializable: %s', e)


def if_none_match_matches(header_value: Optional[str], etag: str) -> bool:
    """RFC 9110 If-None-Match comparison (weak comparison, ``*`` matches)."""
    if not header_value:
        return False
    candidates = [c.strip() for c in header_value.split(',')]
    if '*' in candidates:
        return True
    normalized = _normalize_validator(etag)
    for candidate in candidates:
        if _normalize_validator(candidate) == normalized:
            return True
    return False


def _normalize_validator(value: str) -> str:
    """Strip the weak ``W/`` prefix and wrapping quotes so validators compare equal.

    RFC 9110 weak comparison compares opaque tags, so a client that sends an
    unquoted tag, or one wrapped in quotes, still matches the stored validator.
    """
    stripped = value.strip()
    if stripped.startswith('W/'):
        stripped = stripped[2:].strip()
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        stripped = stripped[1:-1]
    return stripped
