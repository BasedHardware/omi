"""Lightweight original provider partition; no clustering or storage imports."""

from typing import Any

from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL


def provider_key(segment: Any) -> tuple[str, int] | None:
    original = segment.provider_speaker
    if original is not None:
        if original.get('id', -1) < 0 or not original.get('scope'):
            return None
        return (f"{original.get('provider') or 'unknown'}\0{original['scope']}", original['id'])
    scope = segment.speaker_id_scope
    if (
        not scope
        or scope.startswith(('conversation:', 'legacy-conversation:'))
        or segment.speaker_id == OMI_SPEAKER_ID_SENTINEL
        or segment.speaker_id is None
        or segment._speaker_id_synthesized
    ):
        return None
    return (f'{segment.stt_provider or "unknown"}\0{scope}', segment.speaker_id)
