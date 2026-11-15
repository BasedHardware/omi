"""Pure conversation shape calculations shared by metrics and size diagnostics."""

from collections.abc import Mapping


def payload_field(payload: object, name: str) -> object:
    if isinstance(payload, Mapping):
        return payload.get(name)
    return getattr(payload, name, None)


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
    segments = payload_field(payload, 'transcript_segments')
    if not isinstance(segments, list):
        return 0.0
    return sum(_segment_span(segment) for segment in segments)


def segment_count(payload: object) -> int:
    segments = payload_field(payload, 'transcript_segments')
    return len(segments) if isinstance(segments, list) else 0


def bucket_le(value: float, edges: tuple[int, ...]) -> str:
    for edge in edges:
        if value <= edge:
            return str(edge)
    return '+Inf'
