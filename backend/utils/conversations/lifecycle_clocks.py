"""Named conversation clocks; dual-written within the existing storage transaction.

Segment storage remains replace-by-array. An append-only store can produce the
same clock patch later without changing lifecycle readers.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from config.occasion_conversations import LIFECYCLE_V2_MODE_ENV
from config.refactor_modes import serving_for, shadow_or_serve
from utils.conversations.lifecycle_metrics import observe

logger = logging.getLogger(__name__)


def utc(value: Any) -> datetime | None:
    try:
        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return datetime.fromtimestamp(value, timezone.utc)
        if isinstance(value, str):
            return utc(datetime.fromisoformat(value.replace('Z', '+00:00')))
    except (ValueError, OverflowError, OSError):
        pass
    return None


def speech_clock(uid: str, row: Mapping[str, Any]) -> datetime | None:
    from utils.conversations.recorded_time import conversation_span

    if row.get('recorded_end') is not None:
        span = conversation_span(row)
        return span.recorded_end if span else None
    legacy = utc(row.get('finished_at'))
    speech = utc(row.get('last_speech_at')) or legacy
    if shadow_or_serve(LIFECYCLE_V2_MODE_ENV):
        observe('speech_clock', speech == legacy)
    return speech if serving_for(LIFECYCLE_V2_MODE_ENV, uid) else legacy


def activity_updates(
    uid: str,
    current: Mapping[str, Any],
    arrival_at: datetime,
    *,
    segments: Sequence[Mapping[str, Any]] = (),
    started_at: Any = None,
) -> dict[str, Any]:
    """Monotonic activity and actual speech end, never empty-flush speech time."""
    if not shadow_or_serve(LIFECYCLE_V2_MODE_ENV):
        return {}
    updates: dict[str, Any] = {}
    activity = utc(current.get('recorded_end')) or utc(current.get('last_speech_at'))
    if activity is not None:
        updates['last_activity_at'] = activity
    origin = utc(started_at) or utc(current.get('started_at'))
    ends = [
        float(s['end'])
        for s in segments
        if s.get('audio_alignment') != 'unplaced'
        and str(s.get('text') or '').strip()
        and isinstance(s.get('end'), (int, float))
        and not isinstance(s.get('end'), bool)
        and math.isfinite(s['end'])
        and s['end'] >= 0
    ]
    if origin and ends:
        end = origin + timedelta(seconds=max(ends))
        updates['last_speech_at'] = max(end, utc(current.get('last_speech_at')) or end)
        updates['last_activity_at'] = max(end, activity or end)
    return updates


def segment_activity_updates(uid, current, at, live_segments, started_at):
    origin = current.get('started_at') if current.get('audio_timeline') else started_at
    return activity_updates(uid, current, at, segments=live_segments or (), started_at=origin)


def overlap_snapshot(uid, conversation, persisted):
    """Carry recording evidence across the Conversation DTO seam."""
    return {
        **persisted,
        **{
            key: getattr(conversation, key, persisted.get(key))
            for key in (
                'id',
                'source',
                'status',
                'discarded',
                'started_at',
                'finished_at',
                'created_at',
                'transcript_segments',
                'external_data',
                'client_device_id',
            )
        },
        **{
            key: persisted.get(key)
            for key in ('recorded_start', 'recorded_end', 'arrival_at', 'clock', 'last_speech_at')
        },
    }


def overlap_fields(uid, row):
    from utils.conversations.recorded_time import conversation_span

    span = conversation_span(row)
    return dict(row, started_at=span.recorded_start if span else None, finished_at=span.recorded_end if span else None)
