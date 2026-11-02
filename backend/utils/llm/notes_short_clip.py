"""Default-on paid-notes floor. Word count is a compute policy, never a discard rule."""

from __future__ import annotations

from types import SimpleNamespace
from collections.abc import Mapping
from typing import Any

from config.notes_short_clip import floor_serving
from config.refactor_modes import shadow_or_serve
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.conversations.recovery import recovery_transcript_word_count
from utils.conversations.relevance_rules import EXPLICIT_REMINDER_RE, normalize_relevance_text
from utils.llm.notes_language_inputs import in_profile_segments
from utils.llm.notes_refactor_metrics import shadow, result
from utils.llm.notes_short_clip_policy import english_word_floor, has_existing_notes

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


def below_short_clip_floor(*, words: int, speech_seconds: float | None, use_word_floor: bool = True) -> bool:
    """Few English words, or speech too brief to carry a conversation in any language."""
    if use_word_floor and words < NOTES_MIN_WORDS:
        return True
    return speech_seconds is not None and 0 <= speech_seconds < SHORT_CLIP_MAX_SPEECH_SECONDS


def has_explicit_reminder(segments: Any) -> bool:
    text = ' '.join(
        str((row.get('text') if isinstance(row, Mapping) else getattr(row, 'text', '')) or '').strip()
        for row in segments or ()
    )
    return bool(EXPLICIT_REMINDER_RE.search(normalize_relevance_text(text)))


def quiet_minimum(
    uid: str,
    conversation: Any,
    *,
    tz: str | None = None,
    user_kept: bool = False,
    summary_app_selected: bool = False,
) -> Any:
    """A short nonempty speech capture is kept, without any paid notes.

    Known English captures use words or speech duration; other/unknown languages
    use duration alone because reminder patterns only cover English. Existing
    notes and user-selected apps always bypass the floor. Eligible clips skip
    the relevance tiers and notes model.

    The emoji is the minimum's deterministic category emoji (💬): a blank value
    does not render blank in the app, it renders the client's random fallback.
    """
    serving = floor_serving(uid)
    if (
        (not serving and not shadow_or_serve('NOTES_PACKET_V2_MODE'))
        or user_kept
        or getattr(conversation, 'sync_relevance_user_kept', False)
        or getattr(conversation, 'user_title', None)
        or getattr(conversation, 'photos', None)
        or getattr(conversation, 'has_photos', False)
        or has_existing_notes(conversation)
        or summary_app_selected
        or getattr(conversation, 'app_id', None)
    ):
        return None
    segments = list(getattr(conversation, 'transcript_segments', None) or ())
    if not segments and getattr(conversation, 'text', None):
        source = getattr(conversation, 'text_source', None)
        if getattr(source, 'value', source) != 'audio':
            return None
        segments = [SimpleNamespace(text=conversation.text)]
    text = ' '.join(
        str((row.get('text') if isinstance(row, Mapping) else getattr(row, 'text', '')) or '').strip()
        for row in segments
    )
    if has_explicit_reminder(segments):
        return None
    selected = [
        SimpleNamespace(**dict(row)) if isinstance(row, Mapping) else row for row in in_profile_segments(segments)
    ]
    view = SimpleNamespace(transcript_segments=selected, started_at=getattr(conversation, 'started_at', None))
    words = recovery_transcript_word_count(view)
    eligible = bool(text.strip()) and below_short_clip_floor(
        words=words,
        speech_seconds=speech_seconds(selected),
        use_word_floor=english_word_floor(conversation, normalize_relevance_text(text)),
    )
    shadow('short_clip', 'disagree' if eligible else 'agree', words=words)
    if not eligible or not serving:
        return None
    minimum = build_deterministic_minimum_structured(view, uid=uid, tz_name_provider=lambda: tz)
    minimum.title_provenance = 'server_minimum'
    result('short_clip', 'minimum')
    return minimum
