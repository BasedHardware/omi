"""Conservative lexical repeat detection for safety-WAL speech bound to a live row.

Live and sync transcribe the same audio with different wording, so the existing
exact-text/exact-range merge dedupe cannot drop a reworded repeat. There is no
reliable constant offset between WAL and live clocks, so this helper never
rewrites timestamps and never drops on time coverage alone: an incoming segment
is dropped only when its capture is independently proven (``verified_capture_indices``)
AND a contiguous window of canonical live segments in its time neighborhood
lexically covers every substantive incoming token.

Live windows come from at most three chronologically adjacent live segments.
Their time span is the segment's ``audio_capture_start``/``audio_capture_end``
when both are finite, otherwise the row origin plus the stored offsets — a
content window, which on a v2 pinned timeline is still a faithful capture
window. Matching is deliberately conservative: counter inclusion of every
non-filler incoming token, bounded ``difflib`` ordered-match ratios, shared
exact trigrams, and a duration ratio inside [0.5, 2.0]. Anything the bounds,
caps or thresholds cannot prove is kept.

Pure module: stdlib only.
"""

from __future__ import annotations

import math
import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter
from difflib import SequenceMatcher
from typing import Optional

MAX_MIDPOINT_DISTANCE_SECONDS = 1800.0
MAX_INCOMING_SEGMENTS = 64
MAX_LIVE_SEGMENTS = 4096
MAX_CANDIDATE_SEGMENTS = 128
MAX_WINDOWS_EVALUATED = 16
MIN_INCOMING_TOKENS = 8
MAX_TOKENS = 256
MAX_CHARS = 4096
MIN_SUBSTANTIVE_TOKENS = 4
WINDOW_MAX_SEGMENTS = 3
WINDOW_MAX_GAP_SECONDS = 15.0
COVERAGE_INCOMING_RATIO = 0.85
COVERAGE_CANDIDATE_RATIO = 0.75
MIN_COMMON_TRIGRAMS = 2
DURATION_RATIO_MIN = 0.5
DURATION_RATIO_MAX = 2.0

FILLER_TOKENS = frozenset(
    {'a', 'an', 'the', 'um', 'uh', 'er', 'hmm', 'well', 'basically', 'just', 'so', 'and', 'okay', 'ok'}
)

PROTECTED_CORRECTIONS = frozenset(
    {'actually', 'instead', 'rather', 'correction', 'corrected', 'sorry', 'mean', 'meant'}
)

PROTECTED_NEGATIONS = frozenset(
    {
        'no',
        'not',
        'never',
        'without',
        'neither',
        'nor',
        'cannot',
        'cant',
        "can't",
        "don't",
        "doesn't",
        "didn't",
        "won't",
        "wouldn't",
        "isn't",
        "aren't",
        "wasn't",
        "weren't",
        "shouldn't",
        "couldn't",
        "mustn't",
    }
)

EXCLUDED_SCOPES = ('sync:', 'legacy-conversation:')

MAX_TOTAL_SPAN_SECONDS = 86400.0

_TOKEN_PATTERN = re.compile(r"\w+(?:'\w+)*", re.UNICODE)


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize('NFKC', text or '').casefold()
    return _TOKEN_PATTERN.findall(normalized)


def _substantive(tokens: list[str]) -> list[str]:
    return [token for token in tokens if token not in FILLER_TOKENS]


def _protected(tokens: list[str]) -> Counter:
    return Counter(
        token
        for token in tokens
        if token in PROTECTED_NEGATIONS or token in PROTECTED_CORRECTIONS or any(char.isdigit() for char in token)
    )


def _trigrams(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + 3]) for i in range(len(tokens) - 2)}


def _finite(value: object) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _duration(seconds_pair: tuple[float, float]) -> float:
    start, end = seconds_pair
    return max(0.0, end - start)


def _incoming_span(segment: dict) -> Optional[tuple[float, float]]:
    start = _finite(segment.get('timestamp'))
    offset_start, offset_end = _finite(segment.get('start')), _finite(segment.get('end'))
    if start is None or offset_start is None or offset_end is None or offset_end <= offset_start:
        return None
    abs_end = start + (offset_end - offset_start)
    if not math.isfinite(abs_end) or not math.isfinite(start + abs_end):
        return None
    return start, abs_end


def _live_segment_bounds(segment: dict, origin: float, pinned: bool) -> Optional[tuple[float, float, str]]:
    capture_start = _finite(segment.get('audio_capture_start'))
    capture_end = _finite(segment.get('audio_capture_end'))
    if capture_start is not None and capture_end is not None and capture_end > capture_start:
        if math.isfinite(capture_start + capture_end):
            return capture_start, capture_end, 'capture_window'
        return None
    start, end = _finite(segment.get('start')), _finite(segment.get('end'))
    if start is None or end is None or end <= start:
        return None
    abs_start, abs_end = origin + start, origin + end
    if not (math.isfinite(abs_start) and math.isfinite(abs_end) and math.isfinite(abs_start + abs_end)):
        return None
    return abs_start, abs_end, 'capture_window' if pinned else 'content_window'


def pinned_audio_timeline(marker: object) -> bool:
    """The v2 first-audio pin marker (``audio_timeline.version == 2``)."""
    return isinstance(marker, dict) and marker.get('version') == 2


def _eligible_live(segment: dict) -> bool:
    scope = segment.get('speaker_id_scope') or ''
    return not any(scope.startswith(prefix) for prefix in EXCLUDED_SCOPES)


def _aggregate_method(methods: list[str]) -> str:
    if not methods:
        return 'none'
    distinct = set(methods)
    return distinct.pop() if len(distinct) == 1 else 'mixed'


def bounded_span_seconds(segments: list[dict]) -> float:
    """Sum of non-negative segment durations over finite endpoints, clamped.

    Pathological offsets cannot produce NaN, infinities or runaway totals: the
    result is always finite and inside [0, 86400].
    """
    total = 0.0
    for segment in segments:
        start, end = _finite(segment.get('start')), _finite(segment.get('end'))
        if start is not None and end is not None:
            total += min(max(0.0, end - start), MAX_TOTAL_SPAN_SECONDS)
    return min(max(total, 0.0), MAX_TOTAL_SPAN_SECONDS)


def append_alignment_method(report: dict, exact_retries: int) -> str:
    """Telemetry method once the safe exact-retry pass has also run.

    Lexical drops keep their aggregated method; when nothing lexically dropped
    but the exact-retry pass removed segments, the method is 'exact_retry'.
    """
    if report['dropped_segments'] > 0:
        return report['alignment_method']
    if exact_retries > 0:
        return 'exact_retry'
    return report['alignment_method']


def drop_exact_retries(incoming_segments: list[dict], existing_segments: list[dict]) -> tuple[list[dict], int, bool]:
    """Drop incoming segments that provably replay something already stored.

    A segment drops only when an existing segment shares its normalized text
    AND either the same rounded-2-decimal absolute range or the same non-empty
    segment id. Range-only or relative-only coincidence never drops: unrelated
    new speech at an occupied absolute range is retained. Non-finite or
    inverted ranges and oversized text never participate on either side, so
    an unreadable segment is always kept. The third return marks whether any
    drop matched sync-scoped speech: that replay completes an earlier partial
    sync and still owes downstream completion.
    """
    existing_keys: dict[tuple[str, tuple[float, float]], str] = {}
    existing_ids: dict[str, tuple[str, str]] = {}
    for segment in existing_segments:
        start, end = _finite(segment.get('timestamp')), _finite(segment.get('end'))
        offset_start = _finite(segment.get('start'))
        raw_text = segment.get('text') or ''
        if start is None or end is None or offset_start is None or end <= offset_start or len(raw_text) > MAX_CHARS:
            continue
        abs_key = (round(start, 2), round(start + (end - offset_start), 2))
        text = ' '.join(_tokens(raw_text))
        scope = str(segment.get('speaker_id_scope') or '')
        if text:
            existing_keys[(text, abs_key)] = scope
        segment_id = segment.get('id')
        if isinstance(segment_id, str) and segment_id and text:
            existing_ids[segment_id] = (text, scope)
    kept: list[dict] = []
    dropped = 0
    sync_retry = False
    for segment in incoming_segments:
        start, end = _finite(segment.get('timestamp')), _finite(segment.get('end'))
        offset_start = _finite(segment.get('start'))
        raw_text = segment.get('text') or ''
        text = ' '.join(_tokens(raw_text)) if len(raw_text) <= MAX_CHARS else ''
        segment_id = str(segment.get('id') or '')
        scope = ''
        abs_match = False
        if text and start is not None and end is not None and offset_start is not None and end > offset_start:
            abs_key = (round(start, 2), round(start + (end - offset_start), 2))
            hit = existing_keys.get((text, abs_key))
            if hit is not None:
                abs_match = True
                scope = hit
        id_match = bool(segment_id) and bool(text) and existing_ids.get(segment_id, ('', ''))[0] == text
        if id_match:
            scope = scope or existing_ids[segment_id][1]
        if abs_match or id_match:
            dropped += 1
            if scope.startswith(EXCLUDED_SCOPES):
                sync_retry = True
        else:
            kept.append(segment)
    return kept, dropped, sync_retry


def drop_proven_exact_retries(
    indexed_incoming: list[tuple[int, dict]],
    existing_segments: list[dict],
    *,
    verified_indices: frozenset[int] = frozenset(),
) -> tuple[list[dict], int, bool]:
    """Exact-retry pass restricted to capture-proven or same-scope evidence.

    ``indexed_incoming`` pairs each kept incoming segment with its original
    intake index. A capture-proven index may exact-retry against all canonical
    segments; an unproven one only ever compares against stored lines carrying
    the identical nonempty ``sync:`` scope (file or segment-hash granularity),
    so unproved live text, ranges and bare ids are never the drop authority.
    More than ``MAX_LIVE_SEGMENTS`` existing or ``MAX_INCOMING_SEGMENTS``
    incoming rows bounds the pools before any matching: unproven segments then
    keep untouched without tokenizing.
    """
    if len(existing_segments) > MAX_LIVE_SEGMENTS:
        return [segment for _, segment in indexed_incoming], 0, False
    oversized = len(indexed_incoming) > MAX_INCOMING_SEGMENTS
    bounded_existing = existing_segments
    scoped_existing: dict[str, list[dict]] = {}
    for existing in bounded_existing:
        scope = str(existing.get('speaker_id_scope') or '')
        if scope.startswith('sync:'):
            scoped_existing.setdefault(scope, []).append(existing)
    survivors: list[dict] = []
    retries = 0
    sync_retry = False
    for index, segment in indexed_incoming[:MAX_INCOMING_SEGMENTS]:
        if index in verified_indices:
            pool = bounded_existing
        elif oversized:
            survivors.append(segment)
            continue
        else:
            scope = str(segment.get('speaker_id_scope') or '')
            pool = scoped_existing.get(scope, []) if scope.startswith('sync:') else []
        kept, dropped, retry = drop_exact_retries([segment], pool)
        retries += dropped
        sync_retry = sync_retry or retry
        survivors.extend(kept)
    survivors.extend(segment for _, segment in indexed_incoming[MAX_INCOMING_SEGMENTS:])
    return survivors, retries, sync_retry


def _zero_report() -> dict:
    return {
        'dropped_seconds': 0.0,
        'dropped_segments': 0,
        'evaluated_segments': 0,
        'methods': [],
        'alignment_method': 'none',
        'repeat_only': False,
    }


def drop_covered_repeats(
    incoming_segments: list[dict],
    live_segments: list[dict],
    *,
    live_origin: float,
    live_pinned: bool,
    verified_capture_indices: frozenset[int] = frozenset(),
) -> tuple[list[dict], dict]:
    """Return (kept incoming segments, drop report) for one bound intake.

    Only ``verified_capture_indices`` — incoming segments whose full source
    frame coverage is independently proven by S1 capture evidence — may drop;
    every other incoming segment is kept before any candidate work. The report
    carries ``dropped_seconds``, the per-drop ``methods`` and ``repeat_only``
    (every evaluated incoming segment was covered). Callers own telemetry
    aggregation; nothing here mutates the inputs.
    """
    if not verified_capture_indices or len(live_segments) > MAX_LIVE_SEGMENTS:
        return list(incoming_segments), _zero_report()
    live_index = []
    for segment in live_segments:
        if not _eligible_live(segment):
            continue
        bounds = _live_segment_bounds(segment, live_origin, live_pinned)
        text = segment.get('text') or ''
        if bounds is None or len(text) > MAX_CHARS:
            continue
        midpoint = (bounds[0] + bounds[1]) / 2
        if not math.isfinite(midpoint):
            continue
        live_index.append((midpoint, bounds, segment))
    live_index.sort(key=lambda item: (item[0], item[1][0], item[1][1], item[2].get('text') or ''))
    midpoints = [item[0] for item in live_index]

    kept: list[dict] = []
    dropped_seconds = 0.0
    methods: list[str] = []
    dropped_count = 0
    evaluated = 0
    for index, segment in enumerate(incoming_segments):
        if index >= MAX_INCOMING_SEGMENTS:
            kept.append(segment)
            continue
        if index not in verified_capture_indices:
            kept.append(segment)
            continue
        evaluated += 1
        span = _incoming_span(segment)
        text = segment.get('text') or ''
        if span is None or len(text) > MAX_CHARS:
            kept.append(segment)
            continue
        tokens = _tokens(text)
        substantive = _substantive(tokens)
        if not MIN_INCOMING_TOKENS <= len(tokens) <= MAX_TOKENS or len(set(substantive)) < MIN_SUBSTANTIVE_TOKENS:
            kept.append(segment)
            continue
        midpoint = (span[0] + span[1]) / 2
        if not math.isfinite(midpoint):
            kept.append(segment)
            continue
        low = bisect_left(midpoints, midpoint - MAX_MIDPOINT_DISTANCE_SECONDS)
        high = bisect_right(midpoints, midpoint + MAX_MIDPOINT_DISTANCE_SECONDS)
        if high - low > MAX_CANDIDATE_SEGMENTS:
            kept.append(segment)
            continue
        nearby = sorted(
            (
                (abs(item[0] - midpoint), item[1], item[2], _tokens(item[2].get('text') or ''))
                for item in live_index[low:high]
            ),
            key=lambda item: (item[0], item[1][0], item[1][1], item[2].get('text') or ''),
        )
        windows = []
        chronological = sorted(nearby, key=lambda item: (item[1][0], item[1][1], item[2].get('text') or ''))
        for start_index in range(len(chronological)):
            window_chars = 0
            window_tokens: list[str] = []
            for size in range(1, WINDOW_MAX_SEGMENTS + 1):
                parts = chronological[start_index : start_index + size]
                if len(parts) < size:
                    break
                if size > 1 and parts[-1][1][0] - parts[-2][1][1] > WINDOW_MAX_GAP_SECONDS:
                    break
                window_chars += len(parts[-1][2].get('text') or '') + (1 if size > 1 else 0)
                window_tokens = window_tokens + parts[-1][3]
                if window_chars > MAX_CHARS or len(window_tokens) > MAX_TOKENS:
                    break
                windows.append((parts, window_tokens))
        incoming_duration = _duration(span)
        if not math.isfinite(incoming_duration) or incoming_duration <= 0:
            kept.append(segment)
            continue
        incoming_substantive = Counter(substantive)
        incoming_protected = _protected(tokens)
        incoming_trigrams = _trigrams(tokens)
        eligible = []
        for parts, window_tokens in windows:
            window_start, window_end = parts[0][1][0], parts[-1][1][1]
            window_duration = _duration((window_start, window_end))
            if not math.isfinite(window_duration) or window_duration <= 0:
                continue
            ratio = incoming_duration / window_duration
            if not math.isfinite(ratio) or not DURATION_RATIO_MIN <= ratio <= DURATION_RATIO_MAX:
                continue
            window_substantive = Counter(_substantive(window_tokens))
            if any(window_substantive[token] < count for token, count in incoming_substantive.items()):
                continue
            if _protected(window_tokens) != incoming_protected:
                continue
            if len(incoming_trigrams & _trigrams(window_tokens)) < MIN_COMMON_TRIGRAMS:
                continue
            distance = abs((window_start + window_end) / 2 - midpoint)
            window_text = ' '.join(part[2].get('text') or '' for part in parts)
            eligible.append((distance, window_start, window_end, window_text, window_tokens, parts))
        eligible.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        matched = None
        for distance, window_start, window_end, window_text, window_tokens, parts in eligible[:MAX_WINDOWS_EVALUATED]:
            matched_blocks = SequenceMatcher(None, window_tokens, tokens, autojunk=False).get_matching_blocks()
            covered = sum(block.size for block in matched_blocks)
            if (
                covered / len(tokens) < COVERAGE_INCOMING_RATIO
                or covered / len(window_tokens) < COVERAGE_CANDIDATE_RATIO
            ):
                continue
            matched = parts
            break
        if matched is None:
            kept.append(segment)
            continue
        dropped_count += 1
        dropped_seconds += incoming_duration
        methods.append('source_frame_lexical')
    report = {
        'dropped_seconds': dropped_seconds,
        'dropped_segments': dropped_count,
        'evaluated_segments': evaluated,
        'methods': methods,
        'alignment_method': _aggregate_method(methods),
        'repeat_only': bool(incoming_segments) and not kept,
    }
    return kept, report
