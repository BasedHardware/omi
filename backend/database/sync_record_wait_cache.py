"""Short Redis memos of registered-record custody waits.

Owns one bounded Redis key per (uid, conversation) whose record is still
waiting on conversation-level state (no record jobs yet, owner reservation
pending). A repeat upload for that conversation inside the window is answered
with the same retryable wait before any file save, archive or decode, so a hot
client loop costs almost nothing. It never pauses the account and never
releases audio: a hit only repeats a 503 that keeps local audio. Redis errors
fail open to the full check (a pure cache miss, no mode change).

Coverage waits use a separate hashed (owner, conversation, WAL, record jobs)
key. Only a completed negative comparison writes it, once per 30-second TTL;
coverage hits never refresh expiry or affect other WALs.
"""

from typing import Optional

from database.redis_connection import create_bounded_redis_client
from utils.observability.fallback import record_fallback
from database.redis_db import delete_generic_cache, get_generic_cache, set_generic_cache

RECORD_WAIT_CACHE_SECONDS = 30


def _path(uid: str, conversation_id: str) -> str:
    return f'sync:record_wait:v1:{uid}:{conversation_id}'


def remember_record_wait(uid: str, conversation_id: str, reason: str) -> None:
    set_generic_cache(_path(uid, conversation_id), {'reason': reason}, RECORD_WAIT_CACHE_SECONDS)


def cached_record_wait(uid: str, conversation_id: str) -> Optional[str]:
    cached = get_generic_cache(_path(uid, conversation_id))
    reason = cached.get('reason') if isinstance(cached, dict) else None
    return reason if isinstance(reason, str) else None


def forget_record_wait(uid: str, conversation_id: str) -> None:
    delete_generic_cache(_path(uid, conversation_id))


_MARKER_TIMEOUT_SECONDS = 0.5
_marker_redis = None


def _marker_client():
    """A bounded client: a stalled Redis cannot hold the upload past its 503."""
    global _marker_redis
    if _marker_redis is None:
        _marker_redis = create_bounded_redis_client(_MARKER_TIMEOUT_SECONDS)
    return _marker_redis


def claim_gap_fill_marker(record_key: str, wal_key: str, ttl: int) -> bool:
    """First claim of a (record, WAL) gap fill inside ``ttl``; False on a repeat.

    Keys are one-way hashes, never a uid or conversation id. A Redis error
    counts as no marker: the gap-fill write is create-only, so a repeat that
    gets through is a no-op.
    """
    try:
        return bool(_marker_client().set(f'sync:record_gap_fill:v1:{record_key}:{wal_key}', '1', ex=ttl, nx=True))
    except Exception:
        record_fallback(
            component='sync_dispatch',
            from_mode='gap_fill_marker',
            to_mode='create_only_write',
            reason='unavailable',
            outcome='degraded',
        )
        return True


def cached_coverage_wait(key: str) -> bool:
    """A negative coverage result only; Redis expiry is the validity boundary."""
    try:
        return _marker_client().get(f'sync:record_coverage_wait:v1:{key}') in (b'1', '1')
    except Exception:
        record_fallback(
            component='sync_dispatch',
            from_mode='coverage_wait_memo',
            to_mode='coverage_check',
            reason='unavailable',
            outcome='degraded',
        )
        return False


def remember_coverage_wait(key: str) -> None:
    """Write at most once per TTL, including concurrent checks; never slide expiry."""
    try:
        _marker_client().set(f'sync:record_coverage_wait:v1:{key}', '1', ex=RECORD_WAIT_CACHE_SECONDS, nx=True)
    except Exception:
        record_fallback(
            component='sync_dispatch',
            from_mode='coverage_wait_memo',
            to_mode='coverage_check',
            reason='unavailable',
            outcome='degraded',
        )
