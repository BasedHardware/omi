"""Committed-only lifetime validator for the WAL audio coverage consumer.

Pure functions only: no I/O, no imports beyond stdlib. A committed transcript
proof authorizes suppression only inside its validated capture lifetime, and
only where the actual decoded WAL geometry and basename wall clock independently
reproduce the proof's anchors. Anything missing, malformed or conflicting
abstains the whole batch — partial guesses never remove audio.
"""

from __future__ import annotations

import math
import uuid
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from typing import Any, TypeGuard

MAX_LIFETIME_HISTORY = 16
MAX_CAPTURE_LIFETIME_SKEW_SECONDS = 2.0
MAX_COMMITTED_RUN_SECONDS = 30.0
MAX_COMMITTED_RUNS = 32
MAX_ENVELOPES = 13
MAX_DECODED_FRAMES = 360000

_PROOF_KIND = 'committed_transcript_v1'
_LIVE_COVERAGE = ('mapped', 'incomplete')


def _is_int(value: object) -> bool:
    return type(value) is int


def _is_finite_seconds(value: object) -> TypeGuard[int | float]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return math.isfinite(value)


def _valid_capture_root(root: object) -> bool:
    if not isinstance(root, str):
        return False
    try:
        uuid.UUID(root)
    except (ValueError, AttributeError):
        return False
    return True


def _validate_claim(claim: Mapping) -> bool:
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
    if raw.get('codec') not in ('pcm16', 'opus') or raw.get('channel') != 'mono':
        return False
    return True


def _run_matches(run: object, root: str, epoch: int) -> bool:
    if not isinstance(run, Mapping):
        return False
    return run.get('capture_root') == root and _is_int(run.get('clock_epoch')) and run['clock_epoch'] == epoch


def _validated_history_entry(entry: object) -> Mapping | None:
    raw: Any = entry
    if not isinstance(raw, Mapping):
        return None
    if not _valid_capture_root(raw.get('capture_root')):
        return None
    epoch: Any = raw.get('clock_epoch')
    start: Any = raw.get('source_frame_start')
    end: Any = raw.get('source_frame_end')
    rate: Any = raw.get('rate_hz')
    if not all(_is_int(v) for v in (epoch, start, end, rate)):
        return None
    if epoch < 0 or start < 0 or end <= start or rate <= 0:
        return None
    wall_start: Any = raw.get('receipt_wall_start')
    wall_end: Any = raw.get('receipt_wall_end')
    if not (_is_finite_seconds(wall_start) and wall_start > 0):
        return None
    if not (_is_finite_seconds(wall_end) and wall_end > 0 and wall_end >= wall_start):
        return None
    return raw


def _validated_run(run: object, *, channel: object, rate: int) -> Mapping | None:
    """Return the validated matching run; None when malformed or rate/channel-mismatched."""
    raw: Any = run
    if not isinstance(raw, Mapping):
        return None
    run_rate: Any = raw.get('rate_hz')
    if not _is_int(run_rate):
        return None
    if raw.get('channel') != channel or run_rate != rate:
        return None
    frame_start: Any = raw.get('source_frame_start')
    frame_end: Any = raw.get('source_frame_end')
    sample_start: Any = raw.get('decoded_sample_start')
    sample_end: Any = raw.get('decoded_sample_end')
    samples_per_frame: Any = raw.get('samples_per_frame')
    if not all(_is_int(v) for v in (frame_start, frame_end, sample_start, sample_end, samples_per_frame)):
        return None
    if frame_start < 0 or frame_end <= frame_start:
        return None
    if sample_start < 0 or sample_end <= sample_start or samples_per_frame <= 0:
        return None
    if (sample_end - sample_start) != (frame_end - frame_start) * samples_per_frame:
        return None
    wall_start: Any = raw.get('receipt_wall_start')
    wall_end: Any = raw.get('receipt_wall_end')
    if not (_is_finite_seconds(wall_start) and wall_start > 0):
        return None
    if not (_is_finite_seconds(wall_end) and wall_end > 0 and wall_end >= wall_start):
        return None
    source_seconds = (frame_end - frame_start) * samples_per_frame / run_rate
    if source_seconds > MAX_COMMITTED_RUN_SECONDS:
        return None
    if abs((wall_end - wall_start) - source_seconds) > MAX_CAPTURE_LIFETIME_SKEW_SECONDS:
        return None
    return raw


def _uniform_spans(frame_samples: Sequence[int]) -> list[tuple[int, int]] | None:
    """(start_index, samples_per_frame) boundaries of uniform-size frame runs."""
    try:
        frame_count = len(frame_samples)
    except TypeError:
        return None
    if not frame_count or frame_count > MAX_DECODED_FRAMES:
        return None
    spans: list[tuple[int, int]] = []
    for index in range(frame_count):
        value: Any = frame_samples[index]
        if not _is_int(value) or value <= 0:
            return None
        if not spans or spans[-1][1] != value:
            spans.append((index, value))
    return spans


def _span_covers_uniform(
    spans: Sequence[tuple[int, int]], span_starts: Sequence[int], lo_index: int, hi_index: int, spf: int
) -> bool:
    """Every frame in [lo_index, hi_index) has size spf."""
    position = bisect_right(span_starts, lo_index) - 1
    if position < 0 or spans[position][1] != spf:
        return False
    next_boundary = spans[position + 1][0] if position + 1 < len(spans) else None
    return next_boundary is None or next_boundary >= hi_index


def validated_committed_runs(
    claim: Mapping,
    envelopes: Sequence[Mapping],
) -> tuple[Mapping, ...] | None:
    """Validated committed runs for one claim, independent of observed WAL context.

    Returns the runs whose proof, envelope and lifetime evidence hold under the
    committed-transcript contract: receipt-only envelopes and foreign
    roots/epochs contribute nothing, while malformed or conflicting matching
    evidence returns None (the caller abstains). The runs carry their source
    frame geometry and receipt-wall anchors; whether they cover the caller's
    coordinates is the consumer's own decision.
    """
    if not _validate_claim(claim):
        return None
    raw_envelopes: Any = envelopes
    if raw_envelopes is None:
        return None
    try:
        envelope_count = len(raw_envelopes)
    except TypeError:
        return None
    if envelope_count > MAX_ENVELOPES:
        return None
    root = claim['capture_root']
    epoch = claim['clock_epoch']
    rate = claim['rate_hz']
    channel = claim['channel']

    committed_runs: list[Mapping] = []
    lifetimes: list[Mapping] = []
    for env in raw_envelopes:
        if not isinstance(env, Mapping):
            continue
        runs = env.get('runs')
        if not isinstance(runs, list):
            continue
        if len(runs) > MAX_COMMITTED_RUNS:
            return None
        if not any(_run_matches(run, root, epoch) for run in runs):
            continue
        proof: Any = env.get('proof')
        if proof is None:
            continue
        if proof != _PROOF_KIND:
            return None
        if not (_is_int(env.get('version')) and env['version'] == 1):
            return None
        if env.get('capability') != 'source_position' or env.get('origin') != 'live':
            return None
        if env.get('coverage') not in _LIVE_COVERAGE:
            return None
        if not _is_int(env.get('conflicts')) or env['conflicts'] != 0:
            return None
        lifetime: Any = env.get('lifetime')
        if not isinstance(lifetime, Mapping):
            return None
        if not (_is_int(lifetime.get('version')) and lifetime['version'] == 1):
            return None
        if lifetime.get('complete') is not True:
            return None
        if not _is_int(lifetime.get('conflicts')) or lifetime['conflicts'] != 0:
            return None
        history: Any = lifetime.get('history')
        if not isinstance(history, list) or not history or len(history) > MAX_LIFETIME_HISTORY:
            return None
        validated_history: dict[tuple, Mapping] = {}
        for entry in history:
            checked = _validated_history_entry(entry)
            if checked is None:
                return None
            key = (checked['capture_root'], checked['clock_epoch'])
            if key in validated_history:
                return None
            validated_history[key] = checked
        lifetimes.extend(
            entry
            for (entry_root, entry_epoch), entry in validated_history.items()
            if entry_root == root and entry_epoch == epoch
        )
        for run in runs:
            if not _run_matches(run, root, epoch):
                continue
            checked = _validated_run(run, channel=channel, rate=rate)
            if checked is None:
                return None
            anchor = validated_history.get((root, epoch))
            if anchor is None or anchor['rate_hz'] != checked['rate_hz']:
                return None
            if not (
                anchor['source_frame_start'] <= checked['source_frame_start']
                and checked['source_frame_end'] <= anchor['source_frame_end']
            ):
                return None
            if not (
                anchor['receipt_wall_start'] <= checked['receipt_wall_start']
                and checked['receipt_wall_end'] <= anchor['receipt_wall_end']
            ):
                return None
            committed_runs.append(checked)

    for index, first in enumerate(lifetimes):
        for second in lifetimes[index + 1 :]:
            overlap = (
                first['source_frame_start'] < second['source_frame_end']
                and second['source_frame_start'] < first['source_frame_end']
            )
            if not overlap:
                continue
            if (
                first['receipt_wall_end'] < second['receipt_wall_start'] - MAX_CAPTURE_LIFETIME_SKEW_SECONDS
                or second['receipt_wall_end'] < first['receipt_wall_start'] - MAX_CAPTURE_LIFETIME_SKEW_SECONDS
            ):
                return None
    return tuple(committed_runs)


def validated_committed_ranges(
    claim: Mapping,
    envelopes: Sequence[Mapping],
    *,
    wal_start_seconds: object,
    frame_samples: Sequence[int] | None,
) -> tuple[tuple[int, int], ...] | None:
    """Committed-transcript source-frame intervals for one WAL file claim.

    Returns () when no committed proof applies (caller keeps all audio), None
    when relevant evidence or observed WAL context is malformed or conflicting
    (caller abstains the whole batch). Receipt-only envelopes and foreign
    roots/epochs contribute nothing; only validated committed runs clipped to
    the observed WAL domain yield ranges.
    """
    if not _validate_claim(claim):
        return None
    if wal_start_seconds is None or frame_samples is None:
        return ()
    if not _is_finite_seconds(wal_start_seconds) or wal_start_seconds <= 0:
        return None
    spans = _uniform_spans(frame_samples)
    if spans is None:
        return None
    span_starts = [start for start, _ in spans]
    frame_count = len(frame_samples)
    if frame_count > claim['frame_count']:
        return None
    offsets = [0]
    for index in range(frame_count):
        offsets.append(offsets[-1] + frame_samples[index])

    rate = claim['rate_hz']
    domain_start = claim['source_frame_start']
    domain_end = domain_start + frame_count

    committed_runs = validated_committed_runs(claim, envelopes)
    if committed_runs is None:
        return None

    proven: list[tuple[int, int]] = []
    for run in committed_runs:
        lo = max(run['source_frame_start'], domain_start)
        hi = min(run['source_frame_end'], domain_end)
        if hi <= lo:
            continue
        spf = run['samples_per_frame']
        if not _span_covers_uniform(spans, span_starts, lo - domain_start, hi - domain_start, spf):
            return None
        wall_lo = wal_start_seconds + offsets[lo - domain_start] / rate
        wall_hi = wal_start_seconds + offsets[hi - domain_start] / rate
        expected_lo = run['receipt_wall_start'] + (lo - run['source_frame_start']) * spf / rate
        expected_hi = run['receipt_wall_start'] + (hi - run['source_frame_start']) * spf / rate
        if (
            abs(wall_lo - expected_lo) > MAX_CAPTURE_LIFETIME_SKEW_SECONDS
            or abs(wall_hi - expected_hi) > MAX_CAPTURE_LIFETIME_SKEW_SECONDS
        ):
            return None
        proven.append((lo, hi))
    if not proven:
        return ()
    proven.sort()
    merged = [proven[0]]
    for start, end in proven[1:]:
        if start <= merged[-1][1]:
            last = merged[-1]
            merged[-1] = (last[0], max(last[1], end))
        else:
            merged.append((start, end))
    return tuple(merged)
