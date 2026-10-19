"""Decide how much of a unit diarization must see. Pure; no models, no IO.

ASR already sees only padded VAD windows; diarization used to see the whole
unit, silence included. This module keeps the decision of *whether* (and on
which samples) diarization runs separate from how the GPU stage is batched:

- ``speech_regions``: the evidence diarization must cover, i.e. the union of
  unpadded VAD speech and every emitted word clock. Words always count, so a
  word ASR found in padding outside VAD still receives speaker evidence.
- ``short_single_region``: one contiguous evidence region short enough that a
  speaker change inside it is not resolvable by the diarizer anyway. The caller
  then writes the existing ``skipped_single`` result instead of running it.
- ``plan_compaction``/``compact``/``map_back``: diarize only padded speech
  regions joined by short zero gaps, then map turns back onto the original
  capture clock. Any region marked speech is retained whole.
"""

from dataclasses import dataclass
import math

SAMPLE_RATE = 16000

# Context kept on each side of evidence, so segmentation sees onsets/offsets.
PAD_SECONDS = 1.0
# Padded regions closer than this keep their original in-between audio.
JOIN_GAP_SECONDS = 4.0
# Zeros inserted between retained pieces; keeps pieces from abutting.
SEAM_SECONDS = 0.5
# Compaction is only worth a second code path when it removes real audio.
MAX_KEPT_FRACTION = 0.8
# One contiguous evidence region at or under this length skips diarization.
SHORT_SINGLE_SECONDS = 2.0
# Evidence pauses of at most this (inclusive) are one region for the single test.
SHORT_SINGLE_JOIN_SECONDS = 0.5


@dataclass(frozen=True)
class Compaction:
    # (compact_start_sample, original_start_sample, sample_count), ascending.
    pieces: tuple[tuple[int, int, int], ...]
    original_samples: int
    compact_samples: int

    @property
    def kept_seconds(self) -> float:
        return sum(count for _, _, count in self.pieces) / SAMPLE_RATE


def _finite_pair(start, end):
    start, end = float(start), float(end)
    if not (math.isfinite(start) and math.isfinite(end)) or end < start:
        raise ValueError('invalid evidence clock')
    return start, end


def speech_regions(speech_spans, words, duration):
    """Sorted, merged (start, end) seconds of VAD speech plus word clocks."""
    regions = []
    for span in speech_spans:
        regions.append(_finite_pair(span['start'], span['end']))
    for word in words:
        regions.append(_finite_pair(*word['timestamp']))
    merged = []
    for start, end in sorted(regions):
        start, end = max(0.0, start), min(duration, end)
        if end < start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def short_single_region(regions, *, limit=SHORT_SINGLE_SECONDS, join=SHORT_SINGLE_JOIN_SECONDS):
    """True when all evidence is one region no longer than ``limit``.

    Pauses of at most ``join`` seconds (inclusive) do not split the region; a
    pause strictly longer than ``join`` does.
    """
    if not regions:
        return False
    for (_, end), (start, _) in zip(regions, regions[1:]):
        if start - end > join:
            return False
    return regions[-1][1] - regions[0][0] <= limit


def plan_compaction(
    regions,
    total_samples,
    *,
    pad=PAD_SECONDS,
    join_gap=JOIN_GAP_SECONDS,
    seam=SEAM_SECONDS,
    max_kept_fraction=MAX_KEPT_FRACTION,
):
    """Return a Compaction, or None when diarizing the full unit is required.

    None means: no evidence (never compact speech away to nothing) or too
    little audio removed to justify a second timeline.
    """
    if total_samples <= 0 or not regions:
        return None
    padded = []
    for start, end in regions:
        left = max(0, math.floor((start - pad) * SAMPLE_RATE))
        right = min(total_samples, math.ceil((end + pad) * SAMPLE_RATE))
        if right <= left:
            continue
        if padded and left - padded[-1][1] < join_gap * SAMPLE_RATE:
            padded[-1] = (padded[-1][0], max(right, padded[-1][1]))
        else:
            padded.append((left, right))
    if not padded:
        return None
    kept = sum(right - left for left, right in padded)
    if kept > max_kept_fraction * total_samples:
        return None
    seam_samples = int(round(seam * SAMPLE_RATE))
    pieces, position = [], 0
    for left, right in padded:
        if pieces:
            position += seam_samples
        pieces.append((position, left, right - left))
        position += right - left
    return Compaction(tuple(pieces), total_samples, position)


def compact(samples, plan, *, concatenate, zeros):
    """Build the compacted waveform. Array ops are injected for testability."""
    parts = []
    previous_end = None
    for compact_start, original, count in plan.pieces:
        if previous_end is not None and compact_start > previous_end:
            parts.append(zeros(compact_start - previous_end))
        parts.append(samples[original : original + count])
        previous_end = compact_start + count
    result = concatenate(parts)
    if len(result) != plan.compact_samples:
        raise ValueError('compacted length mismatch')
    return result


def map_back(regions, plan):
    """Map compact-clock regions to original clocks; seam audio is dropped.

    A region crossing a seam is split, one fragment per retained piece.
    Exclusive input stays exclusive because pieces are monotonic.
    """
    mapped = []
    for region in regions:
        left, right = float(region['start']), float(region['end'])
        if not (math.isfinite(left) and math.isfinite(right)) or not 0 <= left < right:
            raise ValueError('invalid compacted turn clock')
        # Frame-centred model output may end past EOF (see crop_model_vad_spans);
        # pieces bound every fragment, so the overhang maps to nothing.
        a, b = left * SAMPLE_RATE, right * SAMPLE_RATE
        for compact_start, original, count in plan.pieces:
            lo, hi = max(a, compact_start), min(b, compact_start + count)
            if hi > lo:
                mapped.append(
                    {
                        **region,
                        'start': (original + lo - compact_start) / SAMPLE_RATE,
                        'end': (original + hi - compact_start) / SAMPLE_RATE,
                    }
                )
    return mapped


def unassigned_word_count(words, turns):
    """Words overlapping no turn (a diarizer gap inside a retained piece)."""
    ordered = sorted((float(t['start']), float(t['end'])) for t in turns)
    missing = 0
    for word in words:
        left, right = map(float, word['timestamp'])
        if not any(start <= left < end or (min(right, end) - max(left, start)) > 0 for start, end in ordered):
            missing += 1
    return missing
