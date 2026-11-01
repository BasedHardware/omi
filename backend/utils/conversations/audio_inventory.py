"""Compare a conversation's audio manifest with its listed objects, without reading audio."""

from __future__ import annotations

import math
from typing import Any, List, Mapping, Optional, Sequence, Tuple, cast

from database.audio_timeline import COVERAGE_TOLERANCE_SECONDS
from utils.other.audio_chunks import chunk_end_upper_bound

SAMPLE_RATE = 16000


def finite_number(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def chunk_actual_bounds(chunk: Mapping[str, Any]) -> Optional[Tuple[float, Optional[float]]]:
    """``(start, end)`` extent of one listed object; ``end=None`` is unbounded."""
    span = chunk.get('span')
    if isinstance(span, Mapping):
        rate = finite_number(span.get('sample_rate'))
        start = finite_number(span.get('start'))
        samples = finite_number(span.get('samples'))
        if rate is None or start is None or samples is None or rate <= 0 or samples <= 0:
            return None
        return start, start + samples / rate
    timestamp = finite_number(chunk.get('timestamp'))
    if timestamp is None:
        return None
    return timestamp, chunk_end_upper_bound(chunk, SAMPLE_RATE)


def window_covered(extents: List[Tuple[float, float]], start: float, end: float) -> bool:
    """Whether the union of actual extents covers ``[start, end)``."""
    position = start
    while position < end - COVERAGE_TOLERANCE_SECONDS:
        advanced = [e for s, e in extents if s <= position + COVERAGE_TOLERANCE_SECONDS and e > position]
        if not advanced:
            return False
        position = max(advanced)
    return True


def unreconciled_extents(
    expected: List[Tuple[float, Optional[Tuple[float, float]]]],
    chunks: Sequence[Mapping[str, Any]],
) -> List[Tuple[float, float]]:
    """Audio extents where the manifest and the listed objects disagree.

    An entry on one side only, or a pair with different bounds, says nothing
    about audio elsewhere in the recording, so it refuses only the windows it
    touches. Unknown ends stay unbounded, as in the window proof.
    """
    listed = []
    for chunk in chunks:
        bounds = chunk_actual_bounds(chunk)
        if bounds is not None:
            listed.append((cast(float, finite_number(chunk['timestamp'])), bounds, chunk.get('span') is not None))
    listed.sort(key=lambda item: item[0])
    manifest = sorted(expected, key=lambda item: item[0])
    disputed: List[Tuple[float, float]] = []

    def from_manifest(timestamp: float, bounds: Optional[Tuple[float, float]]) -> Tuple[float, float]:
        return bounds if bounds is not None else (timestamp, math.inf)

    def from_listing(bounds: Tuple[float, Optional[float]]) -> Tuple[float, float]:
        return bounds[0], bounds[1] if bounds[1] is not None else math.inf

    m = n = 0
    while m < len(manifest) or n < len(listed):
        if n == len(listed) or (m < len(manifest) and manifest[m][0] < listed[n][0] - COVERAGE_TOLERANCE_SECONDS):
            disputed.append(from_manifest(*manifest[m]))
            m += 1
        elif m == len(manifest) or listed[n][0] < manifest[m][0] - COVERAGE_TOLERANCE_SECONDS:
            disputed.append(from_listing(listed[n][1]))
            n += 1
        else:
            timestamp, bounds = manifest[m]
            _, actual, has_span = listed[n]
            if (bounds is not None) != has_span or (
                bounds is not None
                and (
                    abs(bounds[0] - actual[0]) > COVERAGE_TOLERANCE_SECONDS
                    or actual[1] is None
                    or abs(bounds[1] - actual[1]) > COVERAGE_TOLERANCE_SECONDS
                )
            ):
                disputed.extend((from_manifest(timestamp, bounds), from_listing(actual)))
            m += 1
            n += 1
    return disputed
