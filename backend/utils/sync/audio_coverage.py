"""Source-frame audio coverage planner for the WAL sync consumer.

Pure functions only: no I/O, no imports beyond stdlib. Every output is either
validated absolute source-frame intervals or an abstention; missing, malformed,
conflicting, or out-of-bounds evidence never removes audio.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from utils.sync.committed_coverage import validated_committed_ranges

MAX_DECODED_FRAMES = 360000
MAX_RECEIVED_INTERVALS = 32
MAX_OUTPUT_INTERVALS = 32
MAX_RUNS_PER_ENVELOPE = 32
MAX_ENVELOPES = 13
MAX_CONTEXT_SECONDS = 0.25

_CLAIM_CODECS = ('pcm16', 'opus')
_LIVE_COVERAGE = ('mapped', 'incomplete')


def _is_int(value: object) -> bool:
    return type(value) is int


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
    if raw.get('codec') not in _CLAIM_CODECS or raw.get('channel') != 'mono':
        return False
    return True


def _run_matches_claim(run: Mapping, root: str, epoch: int) -> bool:
    return run.get('capture_root') == root and _is_int(run.get('clock_epoch')) and run['clock_epoch'] == epoch


def _validated_received_ranges(claim: Mapping, envelopes: Sequence[Mapping]) -> tuple[tuple[int, int], ...] | None:
    """Positive live-received source-frame intervals for one WAL file claim.

    Returns () when no envelope proves any received frame (caller keeps all
    audio), None when matching evidence exists but is malformed or conflicting
    (caller abstains from the coverage consumer entirely). Envelopes for other
    roots/epochs, unknown capabilities, or non-live origins contribute nothing.
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
    proof: list[tuple[int, int]] = []
    for env in raw_envelopes:
        if not isinstance(env, Mapping):
            continue
        if env.get('origin') is not None and env['origin'] != 'live':
            continue
        runs = env.get('runs')
        if not isinstance(runs, list):
            continue
        if len(runs) > MAX_RUNS_PER_ENVELOPE:
            return None
        if not any(isinstance(run, Mapping) and _run_matches_claim(run, root, epoch) for run in runs):
            continue
        if not (_is_int(env.get('version')) and env['version'] == 1):
            return None
        if env.get('capability') != 'source_position':
            return None
        if env.get('origin') != 'live':
            return None
        if env.get('coverage') not in _LIVE_COVERAGE:
            return None
        if not _is_int(env.get('conflicts')) or env['conflicts'] != 0:
            return None
        for run in runs:
            raw_run: Any = run
            if not isinstance(raw_run, Mapping):
                return None
            if not _run_matches_claim(raw_run, root, epoch):
                continue
            run_rate: Any = raw_run.get('rate_hz')
            if not _is_int(run_rate):
                return None
            if raw_run.get('channel') != channel or run_rate != rate:
                continue
            frame_start: Any = raw_run.get('source_frame_start')
            frame_end: Any = raw_run.get('source_frame_end')
            sample_start: Any = raw_run.get('decoded_sample_start')
            sample_end: Any = raw_run.get('decoded_sample_end')
            samples_per_frame: Any = raw_run.get('samples_per_frame')
            if not all(_is_int(v) for v in (frame_start, frame_end, sample_start, sample_end, samples_per_frame)):
                return None
            if frame_start < 0 or frame_end <= frame_start:
                return None
            if sample_start < 0 or sample_end <= sample_start or samples_per_frame <= 0:
                return None
            if (sample_end - sample_start) != (frame_end - frame_start) * samples_per_frame:
                return None
            proof.append((frame_start, frame_end))
    if not proof:
        return ()
    proof.sort()
    merged = [proof[0]]
    for start, end in proof[1:]:
        if start <= merged[-1][1]:
            last = merged[-1]
            merged[-1] = (last[0], max(last[1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def validated_live_ranges(
    claim: Mapping,
    envelopes: Sequence[Mapping],
    *,
    wal_start_seconds: object = None,
    frame_samples: Sequence[int] | None = None,
) -> tuple[tuple[int, int], ...] | None:
    received = _validated_received_ranges(claim, envelopes)
    if received is None:
        return None
    return validated_committed_ranges(
        claim, envelopes, wal_start_seconds=wal_start_seconds, frame_samples=frame_samples
    )


def plan_unreceived_frames(
    frame_samples: Sequence[int],
    live_received_ranges: Sequence[tuple[int, int]],
    *,
    frame_start: int = 0,
    sample_rate: int = 16000,
    context_seconds: float = 0.25,
) -> tuple[tuple[int, int], ...] | None:
    """Absolute source-frame intervals to KEEP after subtracting live receipts.

    Returns () when every decoded frame is positively proven live-received, None
    to abstain (caller keeps the original file untouched). Kept intervals never
    concatenate covered gaps: each may expand only into adjacent covered frames,
    whole frames only, capped per side by context_seconds of sample budget.
    """
    if not _is_int(frame_start) or frame_start < 0:
        return None
    if not _is_int(sample_rate) or sample_rate <= 0:
        return None
    if (
        type(context_seconds) not in (int, float)
        or not math.isfinite(context_seconds)
        or context_seconds < 0
        or context_seconds > MAX_CONTEXT_SECONDS
    ):
        return None
    try:
        frame_count = len(frame_samples)
        received_count = len(live_received_ranges)
    except TypeError:
        return None
    if not frame_count or frame_count > MAX_DECODED_FRAMES:
        return None
    if received_count > MAX_RECEIVED_INTERVALS:
        return None
    samples = list(frame_samples)
    if any(not _is_int(n) or n <= 0 for n in samples):
        return None
    domain_end = frame_start + frame_count
    received: list[tuple[int, int]] = []
    for rng in live_received_ranges:
        try:
            start, end = rng
        except (TypeError, ValueError):
            return None
        if not _is_int(start) or not _is_int(end):
            return None
        if start < 0 or end <= start:
            return None
        start = max(start, frame_start)
        end = min(end, domain_end)
        if end <= start:
            continue
        received.append((start, end))

    received.sort()
    merged_received: list[tuple[int, int]] = []
    for start, end in received:
        if merged_received and start <= merged_received[-1][1]:
            last = merged_received[-1]
            merged_received[-1] = (last[0], max(last[1], end))
        else:
            merged_received.append((start, end))

    covered = bytearray(frame_count)
    for start, end in merged_received:
        covered[start - frame_start : end - frame_start] = b'\x01' * (end - start)

    keep: list[list[int]] = []
    index = 0
    while index < frame_count:
        if covered[index]:
            index += 1
            continue
        end = index
        while end < frame_count and not covered[end]:
            end += 1
        keep.append([index, end])
        index = end
    if not keep:
        return ()

    context_budget = int(sample_rate * context_seconds)
    if context_budget > 0:
        for interval in keep:
            total = 0
            index = interval[0] - 1
            while index >= 0 and covered[index]:
                cost = samples[index]
                if total + cost > context_budget:
                    break
                total += cost
                index -= 1
            interval[0] = index + 1
            total = 0
            index = interval[1]
            while index < frame_count and covered[index]:
                cost = samples[index]
                if total + cost > context_budget:
                    break
                total += cost
                index += 1
            interval[1] = index

    output: list[tuple[int, int]] = []
    for start, end in keep:
        if output and start <= output[-1][1]:
            last = output[-1]
            output[-1] = (last[0], max(last[1], end))
        else:
            output.append((start, end))
    if len(output) > MAX_OUTPUT_INTERVALS:
        return None
    return tuple((frame_start + start, frame_start + end) for start, end in output)
