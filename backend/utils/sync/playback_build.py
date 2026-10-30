"""One immutable conversation artifact per manifest, including stamp-retry recovery."""

from typing import Any

from utils.other.storage import get_conversation_playback_manifest, upload_conversation_playback_artifact
from utils.sync.playback import build_conversation_playback_artifact


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
