"""Wall-clock / speech / segment shape of a conversation at first completed persist.

Fail-open: a metric or log error must never fail a conversation. Labels are a
closed vocabulary — never uid, conversation id, device id, or free text.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime

from utils.metrics import (
    CONVERSATION_DURATION_BUCKETS,
    CONVERSATION_SEGMENT_BUCKETS,
    CONVERSATION_SHAPE_SOURCES,
    OMI_CONVERSATION_DURATION_SECONDS,
    OMI_CONVERSATION_SEGMENTS,
    OMI_CONVERSATION_SPEECH_SECONDS,
)
from utils.product_metrics import SOURCES, record_product_event

logger = logging.getLogger(__name__)

SHAPE_SOURCES = frozenset(CONVERSATION_SHAPE_SOURCES)
_INTEGRATION_SOURCES = frozenset({'workflow', 'external_integration'})
_DURATION_LE = tuple(str(edge) for edge in CONVERSATION_DURATION_BUCKETS) + ('+Inf',)
_SEGMENT_LE = tuple(str(edge) for edge in CONVERSATION_SEGMENT_BUCKETS) + ('+Inf',)


def _field(payload: object, name: str) -> object:
    if isinstance(payload, Mapping):
        return payload.get(name)
    return getattr(payload, name, None)


def _source_token(raw: object) -> str:
    value = getattr(raw, 'value', raw)
    return value if isinstance(value, str) else ''


def classify_conversation_source(payload: object) -> str:
    """Closed shape source. Bound: 6 values in SHAPE_SOURCES."""
    try:
        if _field(payload, 'imported') is True:
            return 'import'
        source = _source_token(_field(payload, 'source'))
        if source in _INTEGRATION_SOURCES:
            return 'integration'
        if source == 'desktop':
            return 'desktop'
        if _field(payload, 'sync_content_revision') is not None or _field(payload, 'sync_relevance') is not None:
            return 'sync'
        if source:
            return 'live'
        return 'unknown'
    except Exception:
        return 'unknown'


def _as_datetime(raw: object) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


def wall_clock_seconds(payload: object) -> float | None:
    started = _as_datetime(_field(payload, 'started_at'))
    finished = _as_datetime(_field(payload, 'finished_at'))
    if started is None or finished is None:
        return None
    return max(0.0, (finished - started).total_seconds())


def _segment_span(segment: object) -> float:
    if isinstance(segment, Mapping):
        start = segment.get('start')
        end = segment.get('end')
    else:
        start = getattr(segment, 'start', None)
        end = getattr(segment, 'end', None)
    try:
        start_s = float(start) if start is not None else 0.0
        end_s = float(end) if end is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    return end_s - start_s if end_s > start_s else 0.0


def speech_seconds(payload: object) -> float:
    segments = _field(payload, 'transcript_segments')
    if not isinstance(segments, list):
        return 0.0
    return sum(_segment_span(segment) for segment in segments)


def segment_count(payload: object) -> int:
    segments = _field(payload, 'transcript_segments')
    return len(segments) if isinstance(segments, list) else 0


def bucket_le(value: float, edges: tuple[int, ...]) -> str:
    for edge in edges:
        if value <= edge:
            return str(edge)
    return '+Inf'


def observe_completed_conversation_shape(uid: str, payload: object) -> None:
    """Record shape + product events for one first completed persist. Never raises."""
    try:
        source = classify_conversation_source(payload)
        if source not in SHAPE_SOURCES:
            source = 'unknown'
        duration = wall_clock_seconds(payload)
        speech = speech_seconds(payload)
        segments = float(segment_count(payload))
        if duration is not None:
            OMI_CONVERSATION_DURATION_SECONDS.labels(source=source).observe(duration)
        OMI_CONVERSATION_SPEECH_SECONDS.labels(source=source).observe(max(0.0, speech))
        OMI_CONVERSATION_SEGMENTS.labels(source=source).observe(max(0.0, segments))
        event_source = source if source in SOURCES else 'none'
        # conversation_created is the dead event this seam revives and the one
        # that feeds per-user-daily. Do not also emit conversation_finalized:
        # request_finalization already records that on job admission
        # (lifecycle.request_finalization, intent.created). A second increment
        # here would give one counter two meanings.
        record_product_event('conversation_created', uid=uid, source=event_source, outcome='ok')
        if source == 'sync':
            duration_le = bucket_le(duration if duration is not None else 0.0, CONVERSATION_DURATION_BUCKETS)
            speech_le = bucket_le(max(0.0, speech), CONVERSATION_DURATION_BUCKETS)
            segments_le = bucket_le(max(0.0, segments), CONVERSATION_SEGMENT_BUCKETS)
            if duration_le not in _DURATION_LE:
                duration_le = '+Inf'
            if speech_le not in _DURATION_LE:
                speech_le = '+Inf'
            if segments_le not in _SEGMENT_LE:
                segments_le = '+Inf'
            logger.info(
                'omi_conversation_shape source=%s duration_le=%s speech_le=%s segments_le=%s',
                source,
                duration_le,
                speech_le,
                segments_le,
            )
    except Exception:
        return
