"""Pure audio bounds. A processing clock is never evidence of recorded duration."""

import math
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from models.conversation_continuity import DEFAULT_GAP_SECONDS


def recorded_span(
    started_at: datetime | None, segments: Sequence[Mapping[str, Any]]
) -> tuple[datetime, datetime] | None:
    if started_at is None:
        return None
    intervals = [
        (float(s['start']), float(s['end']))
        for s in segments
        if s.get('audio_alignment') != 'unplaced'
        and all(
            isinstance(s.get(k), (int, float)) and not isinstance(s[k], bool) and math.isfinite(s[k])
            for k in ('start', 'end')
        )
        and s['end'] > s['start']
    ]
    if not intervals:
        return None
    try:
        return started_at + timedelta(seconds=min(a for a, _ in intervals)), started_at + timedelta(
            seconds=max(b for _, b in intervals)
        )
    except (OverflowError, ValueError):
        return None


def is_late(span: tuple[datetime, datetime] | None, now: datetime) -> bool:
    return span is not None and (now - span[1]).total_seconds() >= DEFAULT_GAP_SECONDS
