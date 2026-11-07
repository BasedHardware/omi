"""Short per-conversation memo of a registered-record custody wait.

Owns one bounded Redis key per (uid, conversation) whose record is still
waiting on conversation-level state (no record jobs yet, owner reservation
pending). A repeat upload for that conversation inside the window is answered
with the same retryable wait before any file save, archive or decode, so a hot
client loop costs almost nothing. It never pauses the account and never
releases audio: a hit only repeats a 503 that keeps local audio. Redis errors
fail open to the full check (a pure cache miss, no mode change).
"""

from typing import Optional

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
