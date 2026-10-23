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
    legacy = utc(row.get('finished_at'))
    speech = utc(row.get('last_speech_at')) or legacy
    if shadow_or_serve(LIFECYCLE_V2_MODE_ENV):
        observe('speech_clock', speech == legacy)
    return speech if serving_for(LIFECYCLE_V2_MODE_ENV, uid) else legacy


def activity_updates(
    uid: str,
    current: Mapping[str, Any],
    at: datetime,
    *,
    segments: Sequence[Mapping[str, Any]] = (),
    started_at: Any = None,
) -> dict[str, Any]:
    """Monotonic activity and actual speech end, never empty-flush speech time."""
    if not shadow_or_serve(LIFECYCLE_V2_MODE_ENV):
        return {}
    activity = max(filter(None, (utc(at), utc(current.get('last_activity_at')))))
    updates: dict[str, Any] = {'last_activity_at': activity}
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
    return updates


def segment_activity_updates(uid, current, at, live_segments, started_at):
    origin = current.get('started_at') if current.get('audio_timeline') else started_at
    return activity_updates(uid, current, at, segments=live_segments or (), started_at=origin)


def overlap_snapshot(uid, conversation, persisted):
    """Carry the internal speech clock across the existing Conversation DTO seam."""
    if not serving_for(LIFECYCLE_V2_MODE_ENV, uid):
        return conversation
    return {**conversation.model_dump(), 'last_speech_at': persisted.get('last_speech_at')}


def overlap_fields(uid, row):
    if not serving_for(LIFECYCLE_V2_MODE_ENV, uid):
        return row
    return dict(row, started_at=utc(row.get('started_at')), finished_at=speech_clock(uid, row))
