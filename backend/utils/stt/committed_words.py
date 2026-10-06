"""Bounded per-word provider timings for committed transcript coverage.

Committed proof may only cite audio the provider actually recognized as
speech: a whole-segment span also covers silence and untranscribed gaps, so
segment start/end are never evidence. Adapters record raw provider-time word
intervals with ``remember_provider_word``; the epoch translator projects them
onto capture samples with ``project_provider_words`` — zero gap fill, and any
segment that cannot supply valid disjoint word intervals abstains entirely.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple, cast

from config.capture_evidence import capture_evidence_dark_write_enabled, listen_committed_capture_coverage_enabled

PROVIDER_WORD_RANGES_KEY = '_provider_word_ranges'
PROVIDER_WORDS_ABSTAIN_KEY = '_provider_words_abstain'
CAPTURE_WORD_RANGES_KEY = '_capture_word_ranges'

MAX_WORD_RANGES = 256
MAX_WORD_SECONDS = 2.0


def _seconds_pair(value: Any) -> Tuple[float, float] | None:
    try:
        start, end = value
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(start, (int, float))
        or isinstance(start, bool)
        or not isinstance(end, (int, float))
        or isinstance(end, bool)
        or not math.isfinite(start)
        or not math.isfinite(end)
        or start < 0
        or end <= start
        or end - start > MAX_WORD_SECONDS
    ):
        return None
    return float(start), float(end)


def remember_provider_word(segment: Dict[str, Any], start: Any, end: Any, text: Any) -> None:
    """Record one recognized provider word interval on its segment dict.

    Inert unless both the dark-write admission and the committed-coverage flag
    are on: with either off the segment stays byte-identical. Empty text is not
    evidence and is ignored. An invalid interval or a bounds overflow abstains
    the whole segment: its collected ranges are dropped and a private marker
    blocks any later additions.
    """
    if not (capture_evidence_dark_write_enabled() and listen_committed_capture_coverage_enabled()):
        return
    if segment.get(PROVIDER_WORDS_ABSTAIN_KEY):
        return
    if not isinstance(text, str) or not text.strip():
        return
    pair = _seconds_pair((start, end))
    ranges = segment.setdefault(PROVIDER_WORD_RANGES_KEY, [])
    if pair is None or len(ranges) >= MAX_WORD_RANGES:
        ranges.clear()
        segment[PROVIDER_WORDS_ABSTAIN_KEY] = True
        return
    ranges.append(pair)


def project_provider_words(segment: Dict[str, Any], send_map: Any, rate: int) -> Tuple[Tuple[int, int], ...]:
    """Map raw provider word intervals onto capture samples, gap-preserving.

    Pops the private raw fields from `segment` (a translator-owned copy) and
    returns the disjoint capture-sample intervals the words provably occupy.
    Every interval must lie inside the segment's own provider start/end and is
    mapped independently through `send_map.map_interval` only — no point or
    tail recovery and no interpolation across accepted-send discontinuities.
    Only overlapping or touching mapped intervals coalesce; every positive
    gap stays unproven. Anything unusable returns ().
    """
    raw = segment.pop(PROVIDER_WORD_RANGES_KEY, None)
    abstain = segment.pop(PROVIDER_WORDS_ABSTAIN_KEY, False)
    if abstain or not raw or not isinstance(raw, (list, tuple)) or len(raw) > MAX_WORD_RANGES:
        return ()
    try:
        segment_start = float(cast(Any, segment.get('start')))
        segment_end = float(cast(Any, segment.get('end')))
    except (TypeError, ValueError):
        return ()
    if not (math.isfinite(segment_start) and math.isfinite(segment_end)):
        return ()
    mapped = []
    for item in raw:
        pair = _seconds_pair(item)
        if pair is None:
            continue
        start, end = pair
        if start < segment_start or end > segment_end:
            continue
        first = math.ceil(start * rate)
        last = math.floor(end * rate)
        if last <= first:
            continue
        interval = send_map.map_interval(first, last)
        if interval is not None:
            mapped.append(interval)
    merged = []
    for first, last in sorted(mapped):
        if merged and first <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], last))
        else:
            merged.append((first, last))
    return tuple(merged)
