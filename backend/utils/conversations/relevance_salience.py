"""Home salience is a presentation decision, never a relevance discard.

Model background votes require current evidence of owner absence. Missing identity
is not silence. Minimum rows additionally need positive noise/media evidence.
"""

from __future__ import annotations

import math
import unicodedata
from importlib import import_module
from typing import Any, Sequence

from models.speaker_evidence import SpeakerEvidence
from utils.conversations.relevance_content import owner_speech_seconds, value
from utils.conversations.relevance_rules import EXPLICIT_REMINDER_RE

MAX_NOISE_CLIP_SECONDS = 20
MAX_REPETITION_CHARS = 400


def repetitive_clip(segments: Sequence[Any]) -> bool:
    """A repeated phrase covering the entire clip, including a truncated final repeat.

    Ignore punctuation/spacing across scripts, never infer language or classify
    ordinary short speech. Bound the work and require at least two full repeats.
    """
    text = ''.join(str(value(s, 'text', '') or '') for s in segments)
    text = ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())
    if not 16 <= len(text) <= MAX_REPETITION_CHARS or any(c.isdigit() for c in text):
        return False
    return any(text == (text[:size] * (len(text) // size + 1))[: len(text)] for size in range(8, len(text) // 2 + 1))


def minimum_is_background(conversation: Any, structured: Any, evidence: SpeakerEvidence | None) -> bool:
    """Do not turn a compute floor, an unknown identity or a short moment into noise."""
    segments = value(conversation, 'transcript_segments', ()) or ()
    if (
        value(structured, 'title_provenance') != 'server_minimum'
        or any(value(structured, field) for field in ('overview', 'sections', 'action_items', 'events'))
        or value(conversation, 'photos')
        or value(conversation, 'user_title')
        or any(value(s, 'is_user', False) for s in segments)
        or any(EXPLICIT_REMINDER_RE.search(str(value(s, 'text', '') or '')) for s in segments)
        or owner_speech_seconds(evidence, segments) != 0
    ):
        return False
    # A served content-kind stamp already has the media/noise authority's evidence.
    if value(conversation, 'content_kind') in ('media', 'noise'):
        return True
    spans = [(value(s, 'start'), value(s, 'end')) for s in segments]
    if (
        not spans
        or any(
            not isinstance(t, (int, float)) or isinstance(t, bool) or not math.isfinite(t)
            for span in spans
            for t in span
        )
        or any(end <= start for start, end in spans)
    ):
        return False
    duration = max(end for _, end in spans) - min(start for start, _ in spans)
    return 0 < duration <= MAX_NOISE_CLIP_SECONDS and repetitive_clip(segments)


def finalize_salience(structured: Any, conversation: Any, evidence: SpeakerEvidence | None) -> Any:
    """All notes arms and minimum paths share this last presentation gate.

    Even a likely acoustic owner candidate or legacy positive owner label protects
    speech. This includes every multi-turn owner dialogue, regardless of topic.
    Negative legacy labels cannot establish owner absence.
    """
    segments = value(conversation, 'transcript_segments', ()) or ()
    owner_seconds = owner_speech_seconds(evidence, segments)
    if value(structured, 'salience') == 'background' and (
        owner_seconds != 0
        or any(value(s, 'is_user', False) for s in segments)
        or value(conversation, 'photos')
        or value(conversation, 'user_title')
    ):
        structured.salience = 'highlight'
    elif value(structured, 'salience') is None and minimum_is_background(conversation, structured, evidence):
        structured.salience = 'background'
    return structured


def get_evidence(uid: str | None, conversation_id: str | None) -> SpeakerEvidence | None:
    """The L2 evidence read, fail-open: an unavailable read leaves the model's vote to the guards."""
    if not uid or not conversation_id:
        return None
    try:
        return import_module('utils.speakers.evidence').get_evidence(uid, conversation_id)
    except Exception:
        return None


def finish_home_salience(uid: str, structured: Any, conversation: Any, *, user_kept: bool = False) -> Any:
    """Finalize after notes reuse and minimum paths, before completed persistence.

    Only candidate background rows need the evidence read; normal highlights incur no I/O.
    """
    if value(structured, 'salience') != 'background' and value(structured, 'title_provenance') != 'server_minimum':
        return structured
    if user_kept:
        structured.salience = 'highlight'
        return structured
    evidence = get_evidence(uid, value(conversation, 'id') or value(conversation, 'processing_conversation_id'))
    return finalize_salience(structured, conversation, evidence)
