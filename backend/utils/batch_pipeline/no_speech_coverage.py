"""Prove retained PCM coverage before a no-speech classification can hide a row.

Coordinates use the retained-unit 16 kHz sample grid. Only byte-identical
intersection frames may be deduplicated; conflicting overlaps refuse proof.
"""

from datetime import datetime
import math

from utils.batch_pipeline.record_partial_audio import union
from utils.other.raw_audio import filename_provenance

RATE = 16000
# At most 20 ms missing across the entire capture, including both boundaries.
# This tolerates timestamp rounding, never a missing normal audio chunk.
TOLERANCE_FRAMES = 320


class CoverageIncomplete(ValueError):
    """Content-free refusal: no complete, unambiguous capture coverage."""


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise CoverageIncomplete('coverage_incomplete') from None
    if isinstance(value, bool) or not math.isfinite(result):
        raise CoverageIncomplete('coverage_incomplete')
    return result


def capture_bounds(row, max_seconds):
    times = [row.get(key) for key in ('started_at', 'finished_at')]
    if any(not isinstance(value, datetime) or value.utcoffset() is None for value in times):
        raise CoverageIncomplete('coverage_incomplete')
    start, end = (_number(value.timestamp()) for value in times)
    duration = end - start
    if not 0 < duration <= max_seconds:
        raise CoverageIncomplete('coverage_incomplete')
    frames = round(duration * RATE)
    if frames <= 0:
        raise CoverageIncomplete('coverage_incomplete')
    return start, frames


def source_start(ref, pcm):
    # read_reference refreshes this metadata for the pinned data generation.
    metadata = ref.get('metadata') or {}
    start = metadata.get('capture_start')
    if start in (None, 'unknown'):
        start = filename_provenance(ref['path']).get('capture_start')
    start = _number(start)
    # Raw live packs count internal discontinuities before flattening packets.
    # Unknown gaps cannot be repaired by merely concatenating decoded samples.
    if _number(metadata.get('gap_count')) != 0:
        raise CoverageIncomplete('coverage_incomplete')
    end = _number(metadata.get('capture_end'))
    if abs((end - start) * RATE - len(pcm) // 2) > TOLERANCE_FRAMES:
        raise CoverageIncomplete('coverage_incomplete')
    return start


def covered_pcm(row, sources, max_seconds):
    origin, frames = capture_bounds(row, max_seconds)
    spans = sorted((round((start - origin) * RATE), pcm) for start, pcm in sources)
    ranges = [(left, left + len(pcm) // 2) for left, pcm in spans]
    if not ranges or any(left < -TOLERANCE_FRAMES or right > frames + TOLERANCE_FRAMES for left, right in ranges):
        raise CoverageIncomplete('coverage_incomplete')
    # Reuse the partial-retained coverage union on actual decoded frames, never
    # a padded wall-clock unit duration. Count boundary and interior holes.
    coverage = union(ranges)
    missing, cursor = 0, 0
    for span in coverage:
        left, right = max(0, span['start']), min(frames, span['end'])
        missing += max(0, left - cursor)
        cursor = max(cursor, right)
    missing += max(0, frames - cursor)
    if missing > TOLERANCE_FRAMES:
        raise CoverageIncomplete('coverage_incomplete')

    pcm_union = bytearray()
    cursor = 0
    for left, pcm in spans:
        right = left + len(pcm) // 2
        # Ignore only the bounded overhang outside the capture interval.
        clipped_left, clipped_right = max(0, left), min(frames, right)
        if clipped_right <= clipped_left:
            continue
        pcm = pcm[(clipped_left - left) * 2 : (clipped_right - left) * 2]
        left, right = clipped_left, clipped_right
        if left > cursor:
            pcm_union.extend(b'\0\0' * (left - cursor))
        overlap = max(0, min(cursor, right) - left)
        if pcm[: overlap * 2] != pcm_union[left * 2 : (left + overlap) * 2]:
            raise CoverageIncomplete('coverage_incomplete')
        pcm_union.extend(pcm[overlap * 2 :])
        cursor = max(cursor, right)
    pcm_union.extend(b'\0\0' * (frames - cursor))
    return bytes(pcm_union)
