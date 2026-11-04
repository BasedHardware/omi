"""One immutable conversation artifact per manifest, including stamp-retry recovery."""

import logging
from typing import Any

from database import conversations as conversations_db
from utils.other.storage import get_conversation_playback_manifest, upload_conversation_playback_artifact
from utils.sync.playback import build_conversation_playback_artifact, conversation_merge_fingerprint
from utils.sync.repeat_work_metrics import PLAYBACK_LOCK_CONTENTION, PLAYBACK_WRITES

logger = logging.getLogger(__name__)


def superseded_while_locked(payload: dict) -> bool:
    fingerprint = payload.get('fingerprint')
    if not isinstance(fingerprint, str) or not fingerprint:
        PLAYBACK_LOCK_CONTENTION.labels('retry').inc()
        return False
    try:
        conversation = conversations_db.get_conversation_raw_snapshot(
            payload['uid'],
            payload['conversation_id'],
            field_paths=['audio_files', 'started_at', 'created_at', 'deleted'],
            timeout=1.0,
        )
        superseded = bool(
            conversation
            and not conversation.get('deleted')
            and conversation.get('audio_files')
            and fingerprint != conversation_merge_fingerprint(conversation, demand=payload.get('on_demand') is True)
        )
    except Exception as exc:
        # An inconclusive check retains the existing retry; never discard work.
        logger.warning('event=playback_lock_freshness outcome=unreadable exception_type=%s', type(exc).__name__)
        PLAYBACK_LOCK_CONTENTION.labels('unreadable').inc()
        return False
    PLAYBACK_LOCK_CONTENTION.labels('superseded' if superseded else 'retry').inc()
    if superseded:
        PLAYBACK_WRITES.labels('skipped').inc()
    return superseded


def ensure_conversation_artifact(
    uid: str,
    conversation_id: str,
    audio_files: list[dict[str, Any]],
    started_at: float,
    fingerprint: str,
    *,
    strict_sources: bool = False,
) -> tuple[int, list[dict[str, Any]]]:
    existing = get_conversation_playback_manifest(uid, conversation_id, fingerprint)
    if existing is not None:
        return existing
    data, spans = build_conversation_playback_artifact(
        uid,
        conversation_id,
        audio_files,
        started_at,
        strict_sources=strict_sources or any(af.get('source_fingerprint') for af in audio_files),
    )
    upload_conversation_playback_artifact(uid, conversation_id, data, fingerprint, spans=spans)
    return len(data), spans
