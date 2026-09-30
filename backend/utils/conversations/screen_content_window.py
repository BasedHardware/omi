"""The trusted content window of a conversation and its selection fingerprint.

One definition shared by the adjudication route (which stamps the fingerprint of
the window a pass covered) and the notes finalizer (which waits for a pass over
the conversation's current window). Pure: no I/O.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

CONTENT_WINDOW_POLICY = 'meeting-content-v1'
LEGACY_CONTENT_WINDOW_TOLERANCE_SECONDS = 30
LEGACY_LIFECYCLE_FINGERPRINT = 'legacy-lifecycle-v1'


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def selection_fingerprint(lower: datetime, upper: datetime) -> str:
    lower_ms = round(lower.timestamp() * 1000)
    upper_ms = round(upper.timestamp() * 1000)
    return f'{CONTENT_WINDOW_POLICY}:{lower_ms}:{upper_ms}'


def trusted_content_window(conversation: Dict[str, Any]) -> tuple[datetime, datetime] | None:
    """Project transcript offsets only when their wall-clock origin is trustworthy.

    Legacy listen rows can preserve a socket-first-audio ``started_at`` across a rollover, while
    their transcript offsets restart at zero. In that shape, the projection disagrees with
    ``finished_at`` and must not be used to retrieve screen content.
    """
    started_at = conversation.get('started_at')
    if not isinstance(started_at, datetime):
        return None

    spans: list[tuple[float, float]] = []
    for segment in conversation.get('transcript_segments') or []:
        if not isinstance(segment, dict) or not str(segment.get('text') or '').strip():
            continue
        start = segment.get('start')
        end = segment.get('end')
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)):
            continue
        if not isinstance(end, (int, float)) or not math.isfinite(start) or not math.isfinite(end):
            continue
        if start < 0 or end <= start:
            continue
        spans.append((float(start), float(end)))
    if not spans:
        return None

    started_at = ensure_aware(started_at)
    lower = started_at + timedelta(seconds=min(start for start, _ in spans))
    upper = started_at + timedelta(seconds=max(end for _, end in spans))
    audio_timeline = conversation.get('audio_timeline')
    external_data = conversation.get('external_data') or {}
    has_trusted_origin = (isinstance(audio_timeline, dict) and audio_timeline.get('version') == 2) or (
        isinstance(external_data, dict) and bool(external_data.get('from_segments_client_session_id'))
    )
    if not has_trusted_origin:
        finished_at = conversation.get('finished_at')
        if not isinstance(finished_at, datetime):
            return None
        difference = abs((upper - ensure_aware(finished_at)).total_seconds())
        if difference > LEGACY_CONTENT_WINDOW_TOLERANCE_SECONDS:
            return None
    return lower, upper


def current_selection_fingerprint(conversation: Dict[str, Any]) -> str:
    """The fingerprint a pass over this conversation's current content would carry."""
    window = trusted_content_window(conversation)
    return selection_fingerprint(*window) if window else LEGACY_LIFECYCLE_FINGERPRINT
