"""Single source of truth for a conversation's duration.

`started_at` is the live-socket streaming-session origin, not the moment this
conversation's speech began: it is derived from the STT stream offset plus the
socket's first-audio-byte wall time, so it drifts tens of minutes behind wall
clock across a long socket. Any consumer that computes
`finished_at - started_at` therefore over-counts — an 8-second dictation scrap
recorded 42 minutes into a socket measures as a 42-minute conversation (#4056).

The duration this module returns is the **transcript span**: the largest
validated segment `end`, i.e. how far into the capture the last transcribed
speech landed. It is deliberately NOT summed speech time (see
`meeting_treatment.deduplicated_transcribed_speech_seconds` for that) and it is
not guaranteed elapsed capture time — silence after the last segment is not
counted.

The Flutter app (`ServerConversation.getDurationInSeconds`) and macOS
(`ServerConversation.durationInSeconds`) implement the same rule so the three
platforms report one number; the shared vectors live in
`contracts/parity/conversation_duration.json`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Optional

from utils.observability.fallback import record_fallback


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def transcript_span_seconds(segments: Any) -> Optional[float]:
    """Return the largest valid segment ``end``, or ``None`` when none is valid.

    A segment is ignored when its text is empty, when ``start``/``end`` are
    non-numeric or non-finite, or when ``end < start``. ``None`` means "this
    transcript cannot answer the question", which is different from ``0.0``
    ("the transcript says zero seconds").
    """

    span: Optional[float] = None
    for segment in segments or []:
        text = _value(segment, 'text', '')
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            start = float(_value(segment, 'start'))
            end = float(_value(segment, 'end'))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(end):
            continue
        if end < start:
            continue
        end = max(0.0, end)
        if span is None or end > span:
            span = end
    return span


def _wall_duration_seconds(conversation: Any) -> Optional[float]:
    started_at = _value(conversation, 'started_at')
    finished_at = _value(conversation, 'finished_at')
    if not isinstance(started_at, datetime) or not isinstance(finished_at, datetime):
        return None
    try:
        return max(0.0, (finished_at - started_at).total_seconds())
    except TypeError:
        return None


def conversation_duration_seconds(conversation: Any) -> Optional[float]:
    """Return the conversation's duration in seconds, or ``None`` if unknowable.

    Transcript span when the conversation has usable transcript segments;
    otherwise the wall window ``finished_at - started_at`` (clamped at zero),
    which is the only signal a transcript-free record — a photo-only capture —
    carries. Accepts the Pydantic ``Conversation``/``CreateConversation`` models
    and plain dicts.
    """

    segments = _value(conversation, 'transcript_segments') or []
    span = transcript_span_seconds(segments)
    if span is not None:
        return span

    wall = _wall_duration_seconds(conversation)
    if segments:
        # Segments exist but none survived validation, so the wall window is a
        # degraded stand-in for a number we should have been able to measure.
        record_fallback(
            component='conversation_finalization',
            from_mode='transcript_span',
            to_mode='wall_clock',
            reason='malformed_doc',
            outcome='degraded' if wall is not None else 'exhausted',
        )
    return wall
