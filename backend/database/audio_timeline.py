"""Pure audio-timeline span helpers (stdlib only).

This module is deliberately import-free: ``database/`` modules (notably
``database.conversations``) need the v2 chunk-span vocabulary, but hermetic
tests exec database modules against a stubbed ``utils`` package, so the
helpers must live at this layer rather than in ``utils.audio_timeline``.
``utils.audio_timeline`` re-exports them; it owns the stateful capture-clock
primitives (CaptureTimeline, SendMap, ProviderEpochTranslator) that only the
utils/routers layers use.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# 1 ms: filename-rounding tolerance for coverage and continuity checks.
COVERAGE_TOLERANCE_SECONDS = 0.001


def chunk_span(chunk: Mapping[str, Any] | Any) -> Optional[Dict[str, Any]]:
    """Validated v2 span metadata ('start', 'samples', 'sample_rate') or None."""
    if not hasattr(chunk, 'get'):
        return None
    span = chunk.get('span')
    if not isinstance(span, Mapping) or isinstance(span, (str, bytes)):
        return None
    try:
        raw_start = span['start']
        raw_samples = span['samples']
        raw_rate = span['sample_rate']
    except (KeyError, TypeError):
        return None
    if isinstance(raw_start, bool) or isinstance(raw_samples, bool) or isinstance(raw_rate, bool):
        return None
    try:
        start = float(raw_start)
        samples = int(raw_samples)
        rate = int(raw_rate)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(start) or start < 0.0 or samples <= 0 or rate <= 0:
        return None
    return {'start': start, 'samples': samples, 'sample_rate': rate}


def span_blob_metadata(span: Mapping[str, Any] | Any) -> Dict[str, str]:
    """Blob metadata keys carrying one authoritative v2 span."""
    if not isinstance(span, Mapping) or isinstance(span, (str, bytes)):
        raise TypeError(f"span must be a Mapping, got {type(span).__name__}")
    try:
        raw_start = span['start']
        raw_samples = span['samples']
        raw_rate = span['sample_rate']
    except (KeyError, TypeError) as exc:
        raise ValueError(f"span missing required key: {exc}") from exc
    if isinstance(raw_start, bool) or isinstance(raw_samples, bool) or isinstance(raw_rate, bool):
        raise ValueError("span fields cannot be boolean")
    try:
        start = float(raw_start)
        samples = int(raw_samples)
        rate = int(raw_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"span fields must be numeric: {exc}") from exc
    if not math.isfinite(start) or start < 0.0 or samples <= 0 or rate <= 0:
        raise ValueError(f"invalid span values: start={start}, samples={samples}, rate={rate}")
    return {
        'v2_start': repr(start),
        'v2_samples': str(samples),
        'v2_sample_rate': str(rate),
    }


def parse_span_blob_metadata(metadata: Optional[Mapping[str, Any] | Any]) -> Optional[Dict[str, Any]]:
    """Rehydrate a v2 span from blob metadata, or None when absent/malformed.

    Only a real mapping is a metadata document: a GCS blob carries ``None`` or
    a dict, and anything else (an ORM/test double answering attribute probes)
    is not span evidence and must fail closed to the legacy listing behavior.
    """
    if not isinstance(metadata, Mapping) or isinstance(metadata, (str, bytes)):
        return None
    try:
        raw_start = metadata['v2_start']
        raw_samples = metadata['v2_samples']
        raw_rate = metadata['v2_sample_rate']
    except (KeyError, TypeError):
        return None
    if isinstance(raw_start, bool) or isinstance(raw_samples, bool) or isinstance(raw_rate, bool):
        return None
    try:
        start = float(raw_start)
        samples = int(raw_samples)
        rate = int(raw_rate)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(start) or start < 0.0 or samples <= 0 or rate <= 0:
        return None
    return {'start': start, 'samples': samples, 'sample_rate': rate}


def chunk_span_bounds(item: object) -> Optional[Tuple[float, float]]:
    """``(start, end)`` of one stored ``chunk_spans`` entry, or None if malformed.

    Entries are ``{start, end}`` objects (Firestore cannot store nested
    arrays); a ``[start, end]`` pair is accepted for in-memory callers.
    Attribute-style carriers (e.g. Pydantic v2 ``BaseModel``, which does not
    inherit from ``Mapping``) are read via ``.start`` / ``.end`` — this keeps
    the module import-free while accepting what the write path stores.
    """
    if isinstance(item, Mapping):
        raw_start, raw_end = item.get('start'), item.get('end')
    elif hasattr(item, 'start') and hasattr(item, 'end'):
        # Pydantic v2 BaseModel et al: not a Mapping, but carries .start/.end.
        # Downstream bool/float/span_valid checks still fail closed on bad values.
        raw_start, raw_end = getattr(item, 'start'), getattr(item, 'end')
    elif isinstance(item, (list, tuple)) and len(item) == 2:
        raw_start, raw_end = item[0], item[1]
    else:
        return None
    if isinstance(raw_start, bool) or isinstance(raw_end, bool):
        return None
    try:
        start, end = float(raw_start), float(raw_end)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not span_valid(start, end):
        return None
    return start, end


def span_valid(start: float, end: float) -> bool:
    return math.isfinite(start) and math.isfinite(end) and start >= 0.0 and end > start


def group_chunks_by_coverage(
    chunks: Sequence[Dict[str, Any]] | Sequence[Any],
    *,
    gap_threshold: float,
    tolerance: float = COVERAGE_TOLERANCE_SECONDS,
) -> List[List[Dict[str, Any]]]:
    """Group listed chunks into contiguous AudioFile parts.

    v2 listings (every chunk carrying span metadata) split at actual uncovered
    ends or overlaps — not just start-to-start differences; a single spanless
    chunk keeps the whole listing legacy so no false coverage is claimed.
    """
    if not chunks or not isinstance(chunks, (list, tuple)):
        return []

    spans: List[Optional[Tuple[float, float]]] = []
    for chunk in chunks:
        parsed_span = chunk_span(chunk)
        if parsed_span is None:
            spans.append(None)
            continue
        start = float(parsed_span['start'])
        end = start + float(parsed_span['samples']) / float(parsed_span['sample_rate'])
        spans.append((start, end) if span_valid(start, end) else None)
    v2_listing = bool(spans) and all(span is not None for span in spans)

    effective_tolerance = tolerance if math.isfinite(tolerance) and tolerance >= 0.0 else COVERAGE_TOLERANCE_SECONDS

    groups: List[List[Dict[str, Any]]] = []
    for index, chunk in enumerate(chunks):
        split = False
        if groups and v2_listing:
            prev_end = spans[index - 1]
            this_start = spans[index]
            split = (
                prev_end is not None
                and this_start is not None
                and abs(this_start[0] - prev_end[1]) > effective_tolerance
            )
        if not split and groups:
            prev_chunk = groups[-1][-1]
            try:
                curr_ts = float(chunk['timestamp'])
                prev_ts = float(prev_chunk['timestamp'])
                if (hasattr(chunk, 'get') and isinstance(chunk.get('timestamp'), bool)) or (
                    hasattr(prev_chunk, 'get') and isinstance(prev_chunk.get('timestamp'), bool)
                ):
                    split = True
                elif not (math.isfinite(curr_ts) and math.isfinite(prev_ts)):
                    split = True
                elif not math.isfinite(gap_threshold):
                    split = True
                else:
                    split = (curr_ts - prev_ts) > gap_threshold
            except (KeyError, TypeError, ValueError, AttributeError):
                split = True
        if split or not groups:
            groups.append([chunk])
        else:
            groups[-1].append(chunk)
    return groups
