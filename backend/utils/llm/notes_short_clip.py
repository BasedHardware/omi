"""Serve-gated paid-notes floor. Word count is a compute policy, never a discard rule."""

from __future__ import annotations

from types import SimpleNamespace
from collections.abc import Mapping
from typing import Any

from config.refactor_modes import serving_for, shadow_or_serve
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.conversations.recovery import recovery_transcript_word_count
from utils.llm.notes_language_inputs import in_profile_segments
from utils.llm.notes_refactor_metrics import shadow, result

NOTES_MIN_WORDS = 12


def quiet_minimum(uid: str, conversation: Any, *, tz: str | None = None) -> Any:
    """A short nonempty speech capture is kept, without any paid notes.

    The emoji is the minimum's deterministic category emoji (💬): a blank value
    does not render blank in the app, it renders the client's random fallback.
    """
    if not shadow_or_serve('NOTES_PACKET_V2_MODE') or getattr(conversation, 'photos', None):
        return None
    segments = list(getattr(conversation, 'transcript_segments', None) or ())
    if not segments and getattr(conversation, 'text', None):
        source = getattr(conversation, 'text_source', None)
        if getattr(source, 'value', source) != 'audio':
            return None
        segments = [SimpleNamespace(text=conversation.text)]
    has_text = any(
        str((row.get('text') if isinstance(row, Mapping) else getattr(row, 'text', '')) or '').strip()
        for row in segments
    )
    selected = [
        SimpleNamespace(**dict(row)) if isinstance(row, Mapping) else row for row in in_profile_segments(segments)
    ]
    view = SimpleNamespace(transcript_segments=selected, started_at=getattr(conversation, 'started_at', None))
    words = recovery_transcript_word_count(view)
    eligible = has_text and words < NOTES_MIN_WORDS
    shadow('short_clip', 'disagree' if eligible else 'agree', words=words)
    if not eligible or not serving_for('NOTES_PACKET_V2_MODE', uid):
        return None
    minimum = build_deterministic_minimum_structured(view, uid=uid, tz_name_provider=lambda: tz)
    minimum.title_provenance = 'server_minimum'
    result('short_clip', 'minimum')
    return minimum
