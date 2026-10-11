"""Continuation admission through the existing live lifecycle and content fences."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from database import listen_continuations
from utils.conversations import lifecycle
from utils.observability.fallback import record_fallback


def resolve_live_continuation(
    uid: str,
    origin_id: str,
    *,
    source: str,
    device_id: str | None,
    now: datetime,
    timeout: int,
    proposed: dict[str, str] | None = None,
    firestore_client: Any = None,
) -> dict[str, str] | None:
    result, retired = listen_continuations.resolve_live_continuation(
        uid,
        origin_id,
        source=source,
        device_id=device_id,
        now=now,
        timeout=timeout,
        proposed=proposed,
        firestore_client=firestore_client,
    )
    if retired:
        # Only empty generations are removed; transcript/photo content and its
        # revision fences stay owned by normal finalization.
        lifecycle.delete_empty_recording_conversation(uid, retired['conversation_id'], retired['recording_session_id'])
    if proposed and result is None:
        record_fallback(
            component='other',
            from_mode='recording_continuation',
            to_mode='new_generation',
            reason='config_incomplete',
            outcome='degraded',
        )
    return result
