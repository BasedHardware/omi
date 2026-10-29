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


def sync_recorded_end(row: dict, span: tuple[datetime, datetime] | None) -> datetime | None:
    """A sync intake receipt proves audio extent, including silent tails.

    Older pure-WAL rows already used recorded ends. Live stubs/targets did not,
    so without an intake receipt they can only contribute placed speech.
    """
    end = row.get('sync_recorded_end_at')
    if not isinstance(end, datetime) and row.get('sync_content_revision') and not row.get('sync_live_target'):
        end = row.get('finished_at')
    return end if isinstance(end, datetime) else span[1] if span else None
