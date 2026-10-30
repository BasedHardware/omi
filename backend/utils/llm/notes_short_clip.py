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

# The same floor measured on the clock, kept deliberately tiny: a capture whose
# entire speech fits a few seconds cannot hold a dozen real words, however many
# tokens the recognizer squeezed into it (a 2 s clip kept by Jev with a full
# model title, 2026-10-25). The word floor does the real work; this leg only
# catches token-inflated slivers. It must stay well below a short real command
# ("remind me to call mom at five", ~3-6 s): those keep their notes and tasks.
SHORT_CLIP_MAX_SPEECH_SECONDS = 4.0


def speech_seconds(segments: Any) -> float | None:
    """Summed transcript segment spans, the same measure the relevance tier receives.

    ``None`` when no segment carries a usable span (the floor then answers on
    words alone). Known span faults over-report (pre-roll, quantised chunks,
    one segment spanning minutes), which keeps real speech above the floor.
    """
    total = 0.0
    seen = False
    for row in segments or ():
        text = row.get('text') if isinstance(row, Mapping) else getattr(row, 'text', '')
        if not str(text or '').strip():
            continue
        start = row.get('start') if isinstance(row, Mapping) else getattr(row, 'start', None)
        end = row.get('end') if isinstance(row, Mapping) else getattr(row, 'end', None)
        if start is None or end is None:
            continue
        try:
            span = max(0.0, float(end) - float(start))
        except (TypeError, ValueError):
            continue
        seen = True
        total += span
    return total if seen else None


def below_short_clip_floor(*, words: int, speech_seconds: float | None) -> bool:
    """The short-clip floor on either measure: few words, or speech too brief to carry them."""
    if words < NOTES_MIN_WORDS:
        return True
    return speech_seconds is not None and 0 <= speech_seconds < SHORT_CLIP_MAX_SPEECH_SECONDS


def quiet_minimum(uid: str, conversation: Any, *, tz: str | None = None) -> Any:
    """A short nonempty speech capture is kept, without any paid notes.

    Short is the floor on either measure (``below_short_clip_floor``): few
    words, or a span of speech too brief to carry a conversation even when the
    recognizer packed a dozen words into it. Either way the clip never reaches
    the relevance tiers or the notes model, so no tier can keep it as a
    standalone conversation with a generated title.

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
    eligible = has_text and below_short_clip_floor(words=words, speech_seconds=speech_seconds(selected))
    shadow('short_clip', 'disagree' if eligible else 'agree', words=words)
    if not eligible or not serving_for('NOTES_PACKET_V2_MODE', uid):
        return None
    minimum = build_deterministic_minimum_structured(view, uid=uid, tz_name_provider=lambda: tz)
    minimum.title_provenance = 'server_minimum'
    result('short_clip', 'minimum')
    return minimum
