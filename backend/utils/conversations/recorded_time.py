"""Pure audio bounds. A processing clock is never evidence of recorded duration."""

import math
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from config.recorded_time_tolerances import CONTINUE_GAP_SECONDS as DEFAULT_GAP_SECONDS


def _placed_interval(segment: Mapping[str, Any]) -> tuple[float, float] | None:
    """The interval a segment proves, or ``None`` when it proves no position."""
    if segment.get('audio_alignment') == 'unplaced':
        return None
    if not all(
        isinstance(segment.get(k), (int, float)) and not isinstance(segment[k], bool) and math.isfinite(segment[k])
        for k in ('start', 'end')
    ):
        return None
    if not segment['end'] > segment['start']:
        return None
    return float(segment['start']), float(segment['end'])


def recorded_span(
    started_at: datetime | None, segments: Sequence[Mapping[str, Any]]
) -> tuple[datetime, datetime] | None:
    if started_at is None:
        return None
    intervals = [interval for interval in (_placed_interval(s) for s in segments) if interval is not None]
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


def _normalized_segments(row: Any) -> list[Mapping[str, Any]]:
    """Segments as mappings, never the typed ``recorded_start``/``recorded_end``.

    Both extent readers share this normalisation so they cannot drift. The
    typed span fields are deliberately ignored here: a caller asking for
    segment extent must not be answered by a stored envelope.
    """
    segments = row.get('transcript_segments')
    if not isinstance(segments, list):
        return []
    return [
        s if isinstance(s, Mapping) else {key: getattr(s, key, None) for key in ('start', 'end', 'audio_alignment')}
        for s in segments
    ]


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
    segments = _normalized_segments(row)
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


def segment_span(row: Any) -> tuple[datetime, datetime] | None:
    """Extent proven by placed transcript segments; a wall-clock envelope is not.

    ``conversation_span`` may derive a legacy row's end from ``finished_at``
    when no placed segment proves the recording. That envelope is a coarse
    hint, so a caller that needs captured-audio proof reads this instead and
    refuses when either side has no placed segment. The typed
    ``recorded_start``/``recorded_end`` fields are deliberately ignored: they
    are a stored envelope, not segment evidence.
    """
    from utils.conversations.lifecycle_clocks import utc

    row = _timing_row(row)
    return recorded_span(utc(row.get('started_at')), _normalized_segments(row))


def segment_span_is_exact(row: Any) -> bool:
    """Whether every segment proves a position, so the extent is the whole row.

    ``recorded_span`` drops segments it cannot place: ``audio_alignment ==
    'unplaced'``, non-finite offsets, and empty intervals. A caller that must
    account for all of a row's speech reads this to refuse a row whose extent
    covers only part of what it carries.
    """
    segments = _normalized_segments(_timing_row(row))
    return bool(segments) and all(_placed_interval(segment) is not None for segment in segments)


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
