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
import json
import logging
import os
from typing import Any, Dict, Optional

import redis as redis_pkg

from database import redis_db

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
MAX_UID_LENGTH = 128
MAX_KEY_LENGTH = 256


def _clean_uid(uid: Any) -> str:
    """Sanitize and validate user ID before Redis key formation."""
    if not isinstance(uid, str):
        return ""
    cleaned = uid.strip()
    if not cleaned or len(cleaned) > MAX_UID_LENGTH:
        return ""
    if any(c in cleaned for c in ('\r', '\n', '\0', '..')):
        return ""
    return cleaned


def _clean_key(key: Any) -> str:
    """Sanitize and validate cache keys."""
    if not isinstance(key, str):
        return ""
    cleaned = key.strip()
    if not cleaned or len(cleaned) > MAX_KEY_LENGTH:
        return ""
    if any(c in cleaned for c in ('\r', '\n', '\0')):
        return ""
    return cleaned


def list_cache_ttl_seconds() -> int:
    """Read the TTL at call time so the env var is a live operational knob."""
    raw = os.getenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', str(_TTL_DEFAULT_SECONDS)).strip()
    try:
        ttl = int(raw)
    except ValueError:
        logger.warning('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS=%r is not an integer; using default', raw)
        return _TTL_DEFAULT_SECONDS
    if ttl <= 0:
        return 0
    return min(ttl, _TTL_MAX_SECONDS)


def _version_key(uid: str) -> str:
    clean_uid = _clean_uid(uid)
    return f'{_VERSION_KEY_PREFIX}:{clean_uid}' if clean_uid else ''


def bump_action_items_list_version(uid: str) -> None:
    """Invalidate every cached list page for ``uid``.

    Called from the write paths in ``database.action_items`` after the Firestore
    mutation has committed. Fail-open: a Redis outage means the cache simply
    keeps serving until its short TTL expires.
    """
    key = _version_key(uid)
    if not key:
        return
    try:
        client = getattr(redis_db, 'r', None)
        if client is None:
            logger.warning('action-items list cache: redis client uninitialized for bump uid=%s', uid)
            return
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, _VERSION_TTL_SECONDS)
        pipe.execute()
    except (redis_pkg.exceptions.RedisError, AttributeError) as e:
        logger.warning('action-items list cache: version bump failed uid=%s: %s', uid, e)


def get_action_items_list_version(uid: str) -> Optional[int]:
    """Current invalidation version, or ``None`` when Redis cannot answer or uid is invalid.

    ``None`` means "do not use the cache for this request" — it is not the same
    as version 0, which is a legitimate never-written-yet user.
    """
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return None
    key = _version_key(clean_uid)
    try:
        client = getattr(redis_db, 'r', None)
        if client is None:
            logger.warning('action-items list cache: redis client uninitialized for version read uid=%s', clean_uid)
            return None
        raw = client.get(key)
    except (redis_pkg.exceptions.RedisError, AttributeError) as e:
        logger.warning('action-items list cache: version read failed uid=%s: %s', clean_uid, e)
        return None
    if raw is None:
        return 0
    try:
        val = int(raw)
        return max(0, val)
    except (TypeError, ValueError):
        return 0


def list_cache_key(uid: str, version: int, params: Dict[str, Any]) -> str:
    """Address one list page. Params are hashed so the key length is bounded."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return ''
    safe_version = max(0, int(version)) if isinstance(version, int) and not isinstance(version, bool) else 0
    safe_params = dict(params) if isinstance(params, dict) else {}
    fingerprint = hashlib.sha256(
        json.dumps(safe_params, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()[:16]
    return f'{_ENTRY_KEY_PREFIX}:{clean_uid}:{safe_version}:{fingerprint}'


def compute_etag(body: Dict[str, Any]) -> str:
    """Weak ETag over the exact bytes the route would return."""
    safe_body = dict(body) if isinstance(body, dict) else {}
    digest = hashlib.sha256(json.dumps(safe_body, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8'))
    return f'W/"{digest.hexdigest()[:32]}"'


def read_cached_list(key: str) -> Optional[Dict[str, Any]]:
    """Return ``{"etag": str, "body": dict}`` or ``None``. Never raises."""
    clean_key = _clean_key(key)
    if not clean_key:
        return None
    try:
        client = getattr(redis_db, 'r', None)
        if client is None:
            logger.warning('action-items list cache: redis client uninitialized for read')
            return None
        raw = client.get(clean_key)
    except (redis_pkg.exceptions.RedisError, AttributeError) as e:
        logger.warning('action-items list cache: read failed: %s', e)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get('body'), dict)
        or not isinstance(payload.get('etag'), str)
    ):
        return None
    return payload


def write_cached_list(key: str, *, body: Dict[str, Any], etag: str, ttl: int) -> None:
    """Store one list page. Never raises; a failed write just means a later miss."""
    clean_key = _clean_key(key)
    if not clean_key:
        return
    if not isinstance(body, dict) or not isinstance(etag, str) or not etag:
        return
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0:
        return
    # Guard against arbitrarily long staleness beyond operational maximum
    effective_ttl = min(ttl, _TTL_MAX_SECONDS)
    try:
        client = getattr(redis_db, 'r', None)
        if client is None:
            logger.warning('action-items list cache: redis client uninitialized for write')
            return
        client.set(clean_key, json.dumps({'etag': etag, 'body': body}, default=str), ex=effective_ttl)
    except (redis_pkg.exceptions.RedisError, AttributeError) as e:
        logger.warning('action-items list cache: write failed: %s', e)
    except (TypeError, ValueError) as e:
        logger.warning('action-items list cache: body not serializable: %s', e)


def if_none_match_matches(header_value: Optional[str], etag: str) -> bool:
    """RFC 9110 If-None-Match comparison (weak comparison, ``*`` matches)."""
    if not header_value or not etag:
        return False
    candidates = [c.strip() for c in header_value.split(',')]
    if '*' in candidates:
        return True

    def _strip_weak(tag: str) -> str:
        s = tag.strip()
        if s.startswith('W/'):
            return s[2:].strip()
        return s

    normalized_etag = _strip_weak(etag)
    for candidate in candidates:
        if _strip_weak(candidate) == normalized_etag:
            return True
    return False
