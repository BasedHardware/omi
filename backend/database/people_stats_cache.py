"""Bounded Redis cache for the People-stats aggregate map.

``GET /v1/users/people?include_stats=true`` aggregates the newest
conversations on every call. This module caches only that person_id -> stats
map — never Person rows or signed URLs, which stay authoritative reads. A
per-uid generation token namespaces every entry key, so a writer-side bump
retires all outstanding entries at once instead of tracking each key. Entries
carry a short TTL; the generation outlives them. Every read/write is
fail-open: a Redis outage degrades to the uncached scan, never a 500.

The cache uses its own client with bounded socket I/O. The shared
``redis_db.r`` has no socket timeout, and the invalidation runs on
conversation write paths after Firestore has committed, so a stalled Redis
must cost those writers a fraction of a second, not block them.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from database import redis_db

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

PEOPLE_STATS_CACHE_SCHEMA_VERSION = 1
PEOPLE_STATS_ENTRY_TTL_SECONDS = 60
PEOPLE_STATS_GENERATION_TTL_SECONDS = 86400
PEOPLE_STATS_MAX_ENTRY_BYTES = 262144
PEOPLE_STATS_REDIS_TIMEOUT_SECONDS = 0.25

_bounded_client: Any = None


def _redis() -> Any:
    """The shared Redis deployment, reached through a client whose socket I/O is bounded."""
    global _bounded_client
    if _bounded_client is None:
        host = os.getenv('REDIS_DB_HOST', '').strip()
        if not host:
            return None
        try:
            _bounded_client = redis_db.create_bounded_redis_client(PEOPLE_STATS_REDIS_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning('people stats Redis client construction failed error_type=%s', type(exc).__name__)
            _record_uncached()
            return None
    return _bounded_client


def _record_uncached() -> None:
    record_fallback(
        component='other',
        from_mode='cached',
        to_mode='uncached',
        reason='connection_lost',
        outcome='recovered',
        log=logger,
    )


def _entry_key(path: str) -> str:
    # Same key layout as redis_db's generic cache, so entries stay readable across this change.
    return 'cache:' + base64.b64encode(path.encode('utf-8')).decode('utf-8')


def _generation_key(uid: str) -> str:
    return f'people_stats:v1:{uid}:generation'


def _entry_path(uid: str, generation: str, scan_cap: int) -> str:
    return f'users/{uid}/people_stats/v1/{generation}/{scan_cap}'


def current_generation(uid: str) -> Optional[str]:
    """Fetch-or-create the uid's stats generation; ``None`` disables cache for this call."""
    client = _redis()
    if client is None:
        return None
    key = _generation_key(uid)
    token = uuid.uuid4().hex
    try:
        client.set(key, token, nx=True, ex=PEOPLE_STATS_GENERATION_TTL_SECONDS)
        raw = client.get(key)
    except Exception as exc:
        logger.warning('people stats generation lookup failed uid=%s error_type=%s', uid, type(exc).__name__)
        _record_uncached()
        return None
    try:
        text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
    except UnicodeDecodeError:
        return None
    return text if isinstance(text, str) and text else None


def _restore_stats(raw_stats: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    if not isinstance(raw_stats, dict):
        return None
    stats: Dict[str, Dict[str, Any]] = {}
    for person_id, entry in raw_stats.items():
        if not isinstance(person_id, str) or not isinstance(entry, dict):
            return None
        count = entry.get('conversation_count')
        auto = entry.get('auto_conversation_count')
        talk = entry.get('talk_seconds')
        heard = entry.get('last_heard_at')
        if type(count) is not int or count < 0:
            return None
        if type(auto) is not int or auto < 0 or auto > count:
            return None
        if isinstance(talk, bool) or not isinstance(talk, (int, float)) or not math.isfinite(talk) or talk < 0:
            return None
        heard_at: Optional[datetime] = None
        if heard is not None:
            if not isinstance(heard, str):
                return None
            try:
                heard_at = datetime.fromisoformat(heard)
            except ValueError:
                return None
            if heard_at.tzinfo is None:
                heard_at = heard_at.replace(tzinfo=timezone.utc)
        stats[person_id] = {
            'conversation_count': count,
            'last_heard_at': heard_at,
            'talk_seconds': float(talk),
            'auto_conversation_count': auto,
        }
    return stats


def read_people_stats_cache(uid: str, generation: Optional[str], scan_cap: int) -> Optional[Dict[str, Dict[str, Any]]]:
    """Decoded stats map for the current generation; ``None`` on miss or any invalid payload."""
    if generation is None:
        return None
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.get(_entry_key(_entry_path(uid, generation, scan_cap)))
        payload = json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning('people stats cache read failed uid=%s error_type=%s', uid, type(exc).__name__)
        _record_uncached()
        return None
    if not isinstance(payload, dict) or payload.get('schema_version') != PEOPLE_STATS_CACHE_SCHEMA_VERSION:
        return None
    try:
        if len(json.dumps(payload, default=str).encode('utf-8')) > PEOPLE_STATS_MAX_ENTRY_BYTES:
            return None
        return _restore_stats(payload.get('stats'))
    except (TypeError, ValueError, OverflowError):
        return None


def write_people_stats_cache(
    uid: str, generation: Optional[str], scan_cap: int, stats: Dict[str, Dict[str, Any]]
) -> None:
    """Best-effort store of one aggregate map under the given generation."""
    if generation is None:
        return
    try:
        serialized: Dict[str, Dict[str, Any]] = {}
        for person_id, entry in stats.items():
            heard = entry.get('last_heard_at')
            serialized[str(person_id)] = {
                'conversation_count': entry.get('conversation_count', 0),
                'last_heard_at': heard.isoformat() if isinstance(heard, datetime) else None,
                'talk_seconds': float(entry.get('talk_seconds') or 0.0),
                'auto_conversation_count': entry.get('auto_conversation_count', 0),
            }
        payload = {'schema_version': PEOPLE_STATS_CACHE_SCHEMA_VERSION, 'stats': serialized}
        if len(json.dumps(payload).encode('utf-8')) > PEOPLE_STATS_MAX_ENTRY_BYTES:
            return
        if _restore_stats(serialized) is None:
            return
    except (TypeError, ValueError, OverflowError):
        return
    client = _redis()
    if client is None:
        return
    try:
        client.set(
            _entry_key(_entry_path(uid, generation, scan_cap)),
            json.dumps(payload, default=str),
            ex=PEOPLE_STATS_ENTRY_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning('people stats cache write failed uid=%s error_type=%s', uid, type(exc).__name__)
        _record_uncached()


def invalidate_people_stats_cache(uid: str) -> None:
    """Bump the uid's generation so every outstanding stats entry becomes unreachable."""
    client = _redis()
    if client is None:
        return
    try:
        client.set(_generation_key(uid), uuid.uuid4().hex, ex=PEOPLE_STATS_GENERATION_TTL_SECONDS)
    except Exception as exc:
        logger.warning('people stats cache invalidation failed uid=%s error_type=%s', uid, type(exc).__name__)
        _record_uncached()
