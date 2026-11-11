"""Committed-proof frame ownership tiebreak for ambiguous lineage matches.

Pure functions only: no I/O, no imports beyond stdlib and the sibling
committed-coverage validator. When several generations strictly contain a
segment and neither uniqueness nor the phone's stamp decides, a validated
committed live run can still name the owner: it must cover the segment's exact
source-frame coordinates, or exactly adjoin them (the run ends at the
segment's first frame or starts at its last frame), and its receipt-wall
anchors must independently reproduce both segment wall endpoints. Ownership
selection never authorizes suppression — a segment merely adjoining proven
audio is still transcribed and saved. Anything missing, malformed or
multi-supported returns None; this module never raises into the fail-open
binding path.
"""

from __future__ import annotations

import math
import uuid
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from typing import Any, Optional, TypeGuard

from utils.sync.committed_coverage import (
    MAX_CAPTURE_LIFETIME_SKEW_SECONDS,
    MAX_DECODED_FRAMES,
    MAX_ENVELOPES,
    validated_committed_runs,
)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_capture_root(root: object) -> bool:
    if not isinstance(root, str):
        return False
    try:
        uuid.UUID(root)
    except (ValueError, AttributeError):
        return False
    return True


def _is_finite_seconds(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _claim_valid(claim: object) -> TypeGuard[Mapping]:
    raw: Any = claim
    if not isinstance(raw, Mapping):
        return False
    if not _valid_capture_root(raw.get('capture_root')):
        return False
    epoch: Any = raw.get('clock_epoch')
    start: Any = raw.get('source_frame_start')
    count: Any = raw.get('frame_count')
    rate: Any = raw.get('rate_hz')
    if not all(_is_int(v) for v in (epoch, start, count, rate)):
        return False
    if epoch < 0 or start < 0 or count <= 0 or rate <= 0:
        return False
    return raw.get('codec') in ('pcm16', 'opus') and raw.get('channel') == 'mono'


def _offsets_valid(offsets: object, frame_count: int) -> TypeGuard[Sequence[int]]:
    raw: Any = offsets
    if not isinstance(raw, (list, tuple)) or len(raw) < 2 or len(raw) - 1 > MAX_DECODED_FRAMES:
        return False
    if len(raw) - 1 > frame_count:
        return False
    if not (_is_int(raw[0]) and raw[0] == 0):
        return False
    previous = 0
    for value in raw[1:]:
        if not _is_int(value) or value <= previous:
            return False
        previous = value
    return True


def _coordinate(offsets: Sequence[int], domain_start: int, sample: int) -> tuple[int, int]:
    """(absolute source frame, sample offset inside it) for a decoded sample."""
    if sample == offsets[-1]:
        return domain_start + len(offsets) - 1, 0
    index = bisect_right(offsets, sample) - 1
    return domain_start + index, sample - offsets[index]


def _uniform_segment_frames(
    offsets: Sequence[int], domain_start: int, first_frame: int, last_frame: int, spf: int
) -> bool:
    """Every decoded frame the segment touches has exactly ``spf`` samples."""
    for frame in range(first_frame, last_frame + 1):
        index = frame - domain_start
        if index < 0 or index + 1 >= len(offsets):
            return False
        if offsets[index + 1] - offsets[index] != spf:
            return False
    return True


def _clock_agrees(
    run: Mapping,
    frame: int,
    offset: int,
    wall_seconds: float,
    rate: int,
) -> bool:
    """Extrapolate the run's receipt clock to one segment coordinate."""
    expected = (
        run['receipt_wall_start'] + ((frame - run['source_frame_start']) * run['samples_per_frame'] + offset) / rate
    )
    return abs(expected - wall_seconds) <= MAX_CAPTURE_LIFETIME_SKEW_SECONDS


def _run_decides(
    run: Mapping,
    start_coord: tuple[int, int],
    end_coord: tuple[int, int],
    segment_start: float,
    segment_end: float,
    rate: int,
) -> bool:
    """The run covers or exactly adjoins the segment's source coordinates."""
    spf = run['samples_per_frame']
    span_samples = (run['source_frame_end'] - run['source_frame_start']) * spf
    start_pos = (start_coord[0] - run['source_frame_start']) * spf + start_coord[1]
    end_pos = (end_coord[0] - run['source_frame_start']) * spf + end_coord[1]
    covered = start_pos >= 0 and end_pos <= span_samples
    adjoins = (run['source_frame_end'] == start_coord[0] and start_coord[1] == 0) or (
        run['source_frame_start'] == end_coord[0] and end_coord[1] == 0
    )
    if not covered and not adjoins:
        return False
    return _clock_agrees(run, start_coord[0], start_coord[1], segment_start, rate) and _clock_agrees(
        run, end_coord[0], end_coord[1], segment_end, rate
    )


def unique_committed_canonical(
    matches: Sequence,
    start: object,
    end: object,
    source_position_map: object,
) -> Optional[str]:
    """The single match canonical proven to own the segment's source frames, else None.

    ``matches`` are the caller's already-filtered generations; each carries a
    ``canonical`` id and an optional ``evidence`` (the row's stored live
    ``capture_evidence`` envelope). ``source_position_map`` is the pipeline's
    ``(frame_map, derivative_start_sample)`` pair for this segment. A
    canonical qualifies when its attributed envelopes yield at least one
    validated committed run that covers or exactly adjoins the segment's
    source coordinates with independent clock agreement at both endpoints;
    combined evidence is validated first so competing lifetimes abstain the
    decision entirely. Two qualifying canonicals, malformed evidence or an
    absent/invalid map all return None — never an ordering guess.
    """
    try:
        if not (_is_finite_seconds(start) and _is_finite_seconds(end)):
            return None
        if end <= start:
            return None
        pair: Any = source_position_map
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return None
        frame_map, derivative_start = pair
        if not isinstance(frame_map, Mapping):
            return None
        claim = frame_map.get('claim')
        if not _claim_valid(claim):
            return None
        offsets = frame_map.get('offsets')
        if not _offsets_valid(offsets, claim['frame_count']):
            return None
        if not _is_int(derivative_start) or derivative_start < 0 or derivative_start > offsets[-1]:
            return None
        rate = claim['rate_hz']
        segment_samples = int(round((end - start) * rate))
        if segment_samples < 1:
            return None
        end_sample = derivative_start + segment_samples
        if end_sample > offsets[-1]:
            if end_sample - offsets[-1] > 1:
                return None
            end_sample = offsets[-1]
        domain_start = claim['source_frame_start']
        start_coord = _coordinate(offsets, domain_start, derivative_start)
        end_coord = _coordinate(offsets, domain_start, end_sample)
        if end_coord <= start_coord:
            return None

        envelopes_by_canonical: dict[str, list[Mapping]] = {}
        all_envelopes: list[Mapping] = []
        for match in matches:
            canonical = getattr(match, 'canonical', None)
            evidence = getattr(match, 'evidence', None)
            if not isinstance(canonical, str) or not canonical:
                return None
            if not isinstance(evidence, Mapping) or not evidence:
                continue
            envelopes_by_canonical.setdefault(canonical, []).append(evidence)
            all_envelopes.append(evidence)
        if not all_envelopes or len(all_envelopes) > MAX_ENVELOPES:
            return None
        if validated_committed_runs(claim, all_envelopes) is None:
            return None

        supported: set[str] = set()
        for canonical, envelopes in envelopes_by_canonical.items():
            runs = validated_committed_runs(claim, envelopes)
            if not runs:
                continue
            for run in runs:
                if run['rate_hz'] != rate:
                    continue
                if not _uniform_segment_frames(
                    offsets,
                    domain_start,
                    start_coord[0],
                    end_coord[0] - (1 if end_coord[1] == 0 else 0),
                    run['samples_per_frame'],
                ):
                    continue
                if _run_decides(run, start_coord, end_coord, float(start), float(end), rate):
                    supported.add(canonical)
                    break
        if len(supported) != 1:
            return None
        return supported.pop()
    except Exception:
        return None
