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


SPAN_FIELDS = ('recorded_start', 'recorded_end', 'arrival_at', 'clock')


def _timing_row(value: Any) -> Mapping[str, Any]:
    """Read recording evidence without serializing unrelated display content."""
    if isinstance(value, Mapping):
        return value
    fields = (
        *SPAN_FIELDS,
        'processing_admitted_at',
        'created_at',
        'started_at',
        'finished_at',
        'transcript_segments',
        'sync_live_target',
        'audio_timeline',
        'capture_evidence',
        'status',
        'sync_recorded_end_at',
        'sync_content_revision',
        'last_speech_at',
    )
    return {field: getattr(value, field, None) for field in fields}


def conversation_span(row: Any):
    """Typed read, with lazy legacy derivation and no write/backfill side effect.

    A live processing end never proves speech. Pure sync receipts include VAD
    tails; otherwise placed transcript/frame offsets prove the recording. Empty
    live stubs are points until audio arrives. Imported non-audio rows retain
    their supplied extent. Arrival is metadata only.
    """
    from models.recorded_span import RecordedClock, RecordedSpan
    from utils.conversations.lifecycle_clocks import utc

    row = _timing_row(row)
    start, end = utc(row.get('recorded_start')), utc(row.get('recorded_end'))
    arrival = utc(row.get('arrival_at')) or utc(row.get('processing_admitted_at')) or utc(row.get('created_at'))
    if start is not None and end is not None and end >= start:
        return RecordedSpan(
            recorded_start=start, recorded_end=end, arrival_at=arrival, clock=row.get('clock') or RecordedClock.legacy
        )
    if row.get('recorded_start') is not None or row.get('recorded_end') is not None:
        return None
    origin = utc(row.get('started_at'))
    segments = row.get('transcript_segments')
    segments = (
        [
            s if isinstance(s, Mapping) else {key: getattr(s, key, None) for key in ('start', 'end', 'audio_alignment')}
            for s in segments
        ]
        if isinstance(segments, list)
        else []
    )
    placed = recorded_span(origin, segments)
    if origin is None:
        return None
    live = bool(
        row.get('sync_live_target')
        or row.get('audio_timeline')
        or (row.get('capture_evidence') or {}).get('origin') == 'live'
        or getattr(row.get('status'), 'value', row.get('status')) == 'in_progress'
    )
    proven_ends = [
        value for value in (sync_recorded_end(dict(row), placed), utc(row.get('last_speech_at'))) if value is not None
    ]
    end = max(proven_ends) if proven_ends else None
    if end is None and not live and not segments:
        end = utc(row.get('finished_at'))
    start = placed[0] if placed else origin
    end = max(start, end or start)
    return RecordedSpan(recorded_start=start, recorded_end=end, arrival_at=arrival, clock=RecordedClock.legacy)


def span_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    span = conversation_span(row)
    return span.model_dump() if span is not None else {}


def write_span(row: Mapping[str, Any], *, arrival_at: datetime | None = None) -> dict[str, Any]:
    """Recompute only from recording evidence, before transcript compression.

    Full creates stamp server arrival once; partial writes carry the old arrival
    through their transaction snapshot. Never use arrival to manufacture a span.
    """
    from models.recorded_span import RecordedClock

    if (
        not isinstance(row.get('transcript_segments'), list)
        and row.get('recorded_start') is not None
        and row.get('recorded_end') is not None
    ):
        return span_fields(row)
    evidence = dict(row)
    for key in ('recorded_start', 'recorded_end'):
        evidence.pop(key, None)
    fields: dict[str, Any] = span_fields(evidence)
    if not fields:
        # Unknown origins stay unknown, but every create still has arrival and provenance.
        fields.update(recorded_start=None, recorded_end=None)
    if row.get('audio_timeline'):
        clock = RecordedClock.frame
    elif row.get('sync_content_revision') or row.get('sync_recorded_end_at'):
        clock = RecordedClock.device if not row.get('sync_clock_run') else RecordedClock.estimated_device
    elif (row.get('capture_evidence') or {}).get('origin') == 'live' or getattr(
        row.get('status'), 'value', row.get('status')
    ) == 'in_progress':
        clock = RecordedClock.live_capture
    else:
        clock = row.get('clock') or RecordedClock.imported
    fields['clock'] = clock
    fields['arrival_at'] = row.get('arrival_at') or arrival_at
    return fields


def recorded_end(row: Mapping[str, Any]) -> datetime | None:
    """Recorded end for metadata admission; old end-only projections stay legacy.

    Full rows use the typed span. Metadata-only legacy projections cannot
    reconstruct an origin and retain their old end until the writer fixes them
    forward; a creation/arrival timestamp never fabricates a recorded origin.
    """
    span = conversation_span(row)
    if span is not None:
        return span.recorded_end
    from utils.conversations.lifecycle_clocks import utc

    return utc(row.get('last_speech_at')) or utc(row.get('finished_at'))


def at_offset(base: datetime | None, offset: float) -> datetime | None:
    """Project an offset from a supplied recording origin, never from arrival."""
    return base + timedelta(seconds=max(0.0, offset)) if base else None
