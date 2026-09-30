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
from typing import Dict, List, Mapping, Optional, Tuple

# 1 ms: filename-rounding tolerance for coverage and continuity checks.
COVERAGE_TOLERANCE_SECONDS = 0.001


def chunk_span(chunk: Mapping) -> Optional[Dict]:
    """Validated v2 span metadata ('start', 'samples', 'sample_rate') or None."""
    if not isinstance(chunk, Mapping):
        return None
    span = chunk.get('span') if isinstance(chunk, dict) else None
    if not isinstance(span, dict):
        return None
    try:
        start = float(span['start'])
        samples = int(span['samples'])
        rate = int(span['sample_rate'])
    except (KeyError, TypeError, ValueError):
        return None
    if samples <= 0 or rate <= 0 or not math.isfinite(start):
        return None
    return {'start': start, 'samples': samples, 'sample_rate': rate}


def span_blob_metadata(span: Dict) -> Dict[str, str]:
    """Blob metadata keys carrying one authoritative v2 span."""
    if not isinstance(span, Mapping):
        raise ValueError('span must be a mapping')
    try:
        start = float(span['start'])
        samples = int(span['samples'])
        rate = int(span['sample_rate'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('span must contain numeric start, samples, and sample_rate') from exc
    if not math.isfinite(start) or samples <= 0 or rate <= 0:
        raise ValueError('span values must be finite and positive')
    return {
        'v2_start': repr(start),
        'v2_samples': str(samples),
        'v2_sample_rate': str(rate),
    }


def parse_span_blob_metadata(metadata: Optional[Dict]) -> Optional[Dict]:
    """Rehydrate a v2 span from blob metadata, or None when absent/malformed.

    Only a real mapping is a metadata document: a GCS blob carries ``None`` or
    a dict, and anything else (an ORM/test double answering attribute probes)
    is not span evidence and must fail closed to the legacy listing behavior.
    """
    if not isinstance(metadata, dict):
        return None
    try:
        start = float(metadata['v2_start'])
        samples = int(metadata['v2_samples'])
        rate = int(metadata['v2_sample_rate'])
    except (KeyError, TypeError, ValueError):
        return None
    if samples <= 0 or rate <= 0 or not math.isfinite(start):
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
    return math.isfinite(start) and math.isfinite(end) and end > start


def group_chunks_by_coverage(
    chunks: List[Dict], *, gap_threshold: float, tolerance: float = COVERAGE_TOLERANCE_SECONDS
) -> List[List[Dict]]:
    """Group listed chunks into contiguous AudioFile parts.

    v2 listings (every chunk carrying span metadata) split at actual uncovered
    ends or overlaps — not just start-to-start differences; a single spanless
    chunk keeps the whole listing legacy so no false coverage is claimed.
    """
    if not chunks or not isinstance(chunks, list):
        return []
    # Non-finite/negative gap_threshold fails safe to 0.0 (splitting conservatively on any gap),
    # while tolerance defaults back to the authoritative COVERAGE_TOLERANCE_SECONDS constant.
    if not math.isfinite(gap_threshold) or gap_threshold < 0:
        gap_threshold = 0.0
    if not math.isfinite(tolerance) or tolerance < 0:
        tolerance = COVERAGE_TOLERANCE_SECONDS

    spans: List[Optional[Tuple[float, float]]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            spans.append(None)
            continue
        span = chunk.get('span')
        if not isinstance(span, dict):
            spans.append(None)
            continue
        try:
            start = float(span['start'])
            end = start + float(span['samples']) / float(span['sample_rate'])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            spans.append(None)
            continue
        spans.append((start, end) if span_valid(start, end) else None)
    v2_listing = bool(spans) and all(span is not None for span in spans)

    groups: List[List[Dict]] = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        split = False
        if groups and v2_listing:
            prev_end = spans[index - 1]
            this_start = spans[index]
            split = prev_end is not None and this_start is not None and abs(this_start[0] - prev_end[1]) > tolerance
        if not split and groups:
            prev_chunk = groups[-1][-1]
            try:
                curr_ts = float(chunk['timestamp'])
                prev_ts = float(prev_chunk['timestamp'])
                split = (curr_ts - prev_ts) > gap_threshold
            except (KeyError, TypeError, ValueError):
                split = True
        if split or not groups:
            groups.append([chunk])
        else:
            groups[-1].append(chunk)
    return groups
