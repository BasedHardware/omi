"""Time-aligned user-utterance containment for complementary capture pairs (#3244).

The symmetric shared-speech rule requires exact flattened trigrams, so a
complementary pair whose transcripts diverge by sparse ASR substitutions can
fail to group. This detector instead aligns the smaller capture's own-voice
utterances to wall-clock-matched utterances on the other side, tolerating
scattered transcription differences while still requiring the user actually
said the same words at the same time.

Grouping is metadata only. All thresholds are deliberately conservative; this
is a heuristic, not calibrated production precision. The mode helper and the
fixed-format log line carry no transcript text, identifiers, or exception
detail.
"""

from __future__ import annotations

import bisect
import itertools
import logging
import math
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

MODE_ENV = 'CAPTURE_GROUP_CONTAINMENT_MODE'
_MODES = ('off', 'shadow', 'on')
_PHASES = ('rule', 'jev')
_BASES = ('full', 'sampled')
_REASONS = (
    'contained',
    'no_user_speech',
    'too_small',
    'insufficient_coverage',
    'timing',
    'bounds_segments',
    'bounds_segment_chars',
    'bounds_chars',
    'bounds_words',
    'bounds_segment_words',
    'bounds_segment_seconds',
    'bounds_candidates',
    'bounds_bundle_checks',
    'bounds_matcher_calls',
    'bounds_tokens',
    'bounds_cells',
    'layout_shape',
    'layout_timing',
    'layout_non_finite',
    'layout_out_of_window',
    'layout_window_slop',
    'layout_unplaced',
    'layout_overlap_ratio',
    'ineligible',
)

MAX_SEGMENTS = 4096
MAX_SEGMENT_CHARS = 2048
MAX_CAPTURE_CHARS = 524288
MAX_CAPTURE_WORDS = 64000
MAX_SEGMENT_WORDS = 128
MAX_SEGMENT_SECONDS = 90.0
MAX_TARGET_CANDIDATES = 16
MAX_SMALLER_UTTERANCES = 32
MIN_SMALLER_WORDS = 40
MIN_UTTERANCE_WORDS = 8
MIN_MATCHED_WORDS = 40
MIN_DISTINCT_WORDS = 20
MIN_MATCHED_UTTERANCES = 3
MIN_SUPPORT_SECONDS = 45.0
MIN_COVERAGE = 0.8
MIN_PAIR_COVERAGE = 0.8
MIN_SHARED_BIGRAMS = 2
MAX_BUNDLE_SECONDS = 90.0
MAX_BUNDLE_WORDS = 384
MAX_BUNDLE_SPAN = 3
MAX_TIME_SKEW_SECONDS = 12.0
MAX_MATCHER_CALLS = 128
MAX_COMPARED_TOKENS = 16384
MAX_TOKEN_COMPARISONS = 262144
MAX_BUNDLE_CHECKS = 4096
MAX_LAYOUT_SLOP_SECONDS = 2.0
MAX_LAYOUT_OVERLAP_FRACTION = 0.5

_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)


@dataclass(frozen=True)
class CaptureContainment:
    would_join: bool
    reason: str
    matched_words: int = 0
    smaller_words: int = 0
    matched_utterances: int = 0
    distinct_words: int = 0
    support_seconds: float = 0.0
    coverage: float = 0.0
    basis: str = 'full'
    dropped_segments: int = 0

    def evidence(self) -> dict:
        """Numeric-only record; never carries transcript text or identifiers."""
        return {
            'method': 'user_speech_containment',
            'matched_words': self.matched_words,
            'smaller_words': self.smaller_words,
            'matched_utterances': self.matched_utterances,
            'distinct_words': self.distinct_words,
            'support_seconds': round(self.support_seconds, 3),
            'coverage': round(self.coverage, 4),
        }


def capture_group_containment_mode() -> str:
    value = os.getenv(MODE_ENV, 'shadow').strip().lower()
    return value if value in _MODES else 'off'


def record_capture_containment(
    decision: CaptureContainment, *, mode: str, phase: str = 'rule', jev_p: Any = None
) -> None:
    """Emit the single fixed-format, content-free containment log line."""
    safe_mode = mode if mode in _MODES else 'off'
    safe_phase = phase if phase in _PHASES else 'rule'
    reason = decision.reason if decision.reason in _REASONS else 'ineligible'
    basis = getattr(decision, 'basis', 'full')
    basis = basis if basis in _BASES else 'full'
    score = 'unavailable'
    if isinstance(jev_p, (int, float)) and not isinstance(jev_p, bool):
        if math.isfinite(jev_p) and 0 <= jev_p <= 1:
            score = f'{round(float(jev_p), 6):f}'
    dropped = getattr(decision, 'dropped_segments', 0)
    if not isinstance(dropped, int) or isinstance(dropped, bool):
        dropped = 0
    dropped = max(0, min(dropped, 2 * MAX_SEGMENTS))
    logger.info(
        'event=capture_group_containment mode=%s phase=%s would_join=%s reason=%s jev_p=%s basis=%s dropped_segments=%d',
        safe_mode,
        safe_phase,
        'true' if decision.would_join else 'false',
        reason,
        score,
        basis,
        dropped,
    )


@dataclass
class _LayoutStats:
    dropped_segments: int = 0


class _ContainmentRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _field(row: Any, name: str) -> Any:
    return row.get(name) if isinstance(row, dict) or isinstance(row, Mapping) else getattr(row, name, None)


def _window(row: Any) -> tuple[datetime, datetime, str, Any] | None:
    if _field(row, 'discarded') or _field(row, 'deleted'):
        return None
    status = getattr(_field(row, 'status'), 'value', _field(row, 'status'))
    if status != 'completed':
        return None
    start, finish = _field(row, 'started_at'), _field(row, 'finished_at')
    if not isinstance(start, datetime) or not isinstance(finish, datetime):
        return None
    start = start.astimezone(timezone.utc) if start.tzinfo else start.replace(tzinfo=timezone.utc)
    finish = finish.astimezone(timezone.utc) if finish.tzinfo else finish.replace(tzinfo=timezone.utc)
    source = getattr(_field(row, 'source'), 'value', _field(row, 'source'))
    if finish <= start or not source:
        return None
    return start, finish, str(source), _field(row, 'transcript_segments')


def _valid_time(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _segment_track(segment: Any) -> tuple[bool, int | str | None]:
    if _field(segment, 'is_user') is True:
        return (True, None)
    speaker_id = _field(segment, 'speaker_id')
    if isinstance(speaker_id, int) and not isinstance(speaker_id, bool):
        return (False, speaker_id)
    speaker = _field(segment, 'speaker')
    return (False, speaker if isinstance(speaker, str) and len(speaker) <= 128 else None)


def _in_window_segments(
    started_at: datetime,
    duration_seconds: float,
    ix_start: datetime,
    ix_end: datetime,
    segments: Any,
    *,
    stats: _LayoutStats,
) -> tuple[list[tuple[datetime, datetime, bool, tuple[str, ...], int]], int]:
    """Wholly-in-window text segments; raises _ContainmentRejected on the first violation."""
    if segments is None:
        return [], 0
    if isinstance(segments, (str, bytes)) or not isinstance(segments, Iterable):
        raise _ContainmentRejected('layout_shape')
    collected = list(itertools.islice(segments, MAX_SEGMENTS + 1))
    if len(collected) > MAX_SEGMENTS:
        raise _ContainmentRejected('bounds_segments')
    total_chars = 0
    total_words = 0
    tracks: dict[int, tuple[bool, int | str | None]] = {}
    placed: list[tuple[datetime, datetime, bool, tuple[str, ...], int]] = []
    for index, segment in enumerate(collected):
        text = _field(segment, 'text')
        if not isinstance(text, str) or not text:
            continue
        start, end = _field(segment, 'start'), _field(segment, 'end')
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in (start, end)):
            raise _ContainmentRejected('layout_timing')
        if not _valid_time(start) or not _valid_time(end):
            raise _ContainmentRejected('layout_non_finite')
        if _field(segment, 'audio_alignment') == 'unplaced':
            raise _ContainmentRejected('layout_unplaced')
        if end <= start:
            stats.dropped_segments += 1
            continue
        raw_duration = end - start
        if end <= 0 or start >= duration_seconds:
            raise _ContainmentRejected('layout_out_of_window')
        if start < -MAX_LAYOUT_SLOP_SECONDS or end > duration_seconds + MAX_LAYOUT_SLOP_SECONDS:
            raise _ContainmentRejected('layout_window_slop')
        start, end = max(0.0, start), min(duration_seconds, end)
        wall_start = started_at + timedelta(seconds=start)
        wall_end = started_at + timedelta(seconds=end)
        if wall_start < ix_start or wall_end > ix_end:
            continue
        if len(text) > MAX_SEGMENT_CHARS:
            raise _ContainmentRejected('bounds_segment_chars')
        total_chars += len(text)
        if total_chars > MAX_CAPTURE_CHARS:
            raise _ContainmentRejected('bounds_chars')
        words = tuple(_WORD.findall(text.lower()))
        if len(words) > MAX_SEGMENT_WORDS:
            raise _ContainmentRejected('bounds_segment_words')
        total_words += len(words)
        if total_words > MAX_CAPTURE_WORDS:
            raise _ContainmentRejected('bounds_words')
        if raw_duration > MAX_SEGMENT_SECONDS:
            raise _ContainmentRejected('bounds_segment_seconds')
        if not words:
            continue
        placed.append((wall_start, wall_end, _field(segment, 'is_user') is True, words, index))
        tracks[index] = _segment_track(segment)
    placed.sort(key=lambda item: (item[0], item[1], item[4]))
    latest_end: dict[tuple[bool, int | str | None], datetime] = {}
    durations: dict[tuple[bool, int | str | None], float] = {}
    redundant: dict[tuple[bool, int | str | None], float] = {}
    seen: set[tuple[tuple[bool, int | str | None], datetime, datetime, tuple[str, ...]]] = set()
    normalized: list[tuple[datetime, datetime, bool, tuple[str, ...], int]] = []
    for item in placed:
        track = tracks[item[4]]
        previous = latest_end.get(track)
        seconds = (item[1] - item[0]).total_seconds()
        durations[track] = durations.get(track, 0.0) + seconds
        overlap = max(0.0, (min(previous, item[1]) - item[0]).total_seconds()) if previous is not None else 0.0
        redundant[track] = redundant.get(track, 0.0) + overlap
        latest_end[track] = item[1] if previous is None else max(previous, item[1])
        key = (track, item[0], item[1], item[3])
        if key not in seen:
            seen.add(key)
            normalized.append(item)
    if any(redundant[track] > durations[track] * MAX_LAYOUT_OVERLAP_FRACTION for track in durations):
        raise _ContainmentRejected('layout_overlap_ratio')
    return normalized, total_words


def _bigrams(words: tuple[str, ...]) -> set[tuple[str, str]]:
    return {(words[i], words[i + 1]) for i in range(len(words) - 1)}


def _ordered_match(u_words: tuple[str, ...], bundle_words: tuple[str, ...]) -> tuple[int, set[str]]:
    """Ordered LCS length plus the smaller-side tokens the alignment matched."""
    m, n = len(u_words), len(bundle_words)
    rows = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        above, current = rows[i - 1], rows[i]
        for j in range(1, n + 1):
            if u_words[i - 1] == bundle_words[j - 1]:
                current[j] = above[j - 1] + 1
            elif above[j] >= current[j - 1]:
                current[j] = above[j]
            else:
                current[j] = current[j - 1]
    matched: set[str] = set()
    i, j = m, n
    while i > 0 and j > 0:
        if u_words[i - 1] == bundle_words[j - 1] and rows[i][j] == rows[i - 1][j - 1] + 1:
            matched.add(u_words[i - 1])
            i -= 1
            j -= 1
        elif rows[i - 1][j] > rows[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return rows[m][n], matched


def _match_utterances(
    small_user: list[tuple[datetime, datetime, tuple[str, ...], int]],
    target_user: list[tuple[datetime, datetime, tuple[str, ...]]],
) -> tuple[int, set[str], set[tuple[str, ...]], float, float]:
    """Greedily pair smaller user utterances with monotonic target bundles."""
    matched_words = 0
    matched_weight = 0.0
    matched_tokens: set[str] = set()
    matched_utterances: set[tuple[str, ...]] = set()
    covered_until: datetime | None = None
    support_seconds = 0.0
    last_consumed = -1
    matcher_calls = 0
    compared_tokens = 0
    token_comparisons = 0
    bundle_checks = 0
    skew = timedelta(seconds=MAX_TIME_SKEW_SECONDS)
    target_starts = [item[0] for item in target_user]
    for u_start, u_end, u_words, u_weight in small_user:
        u_bigrams = _bigrams(u_words)
        candidates = []
        first = max(last_consumed + 1, bisect.bisect_left(target_starts, u_start - skew))
        last = bisect.bisect_right(target_starts, u_start + skew)
        for i in range(first, last):
            for span in range(1, MAX_BUNDLE_SPAN + 1):
                if i + span > len(target_user):
                    break
                if bundle_checks + 1 > MAX_BUNDLE_CHECKS:
                    raise _ContainmentRejected('bounds_bundle_checks')
                bundle_checks += 1
                bundle = target_user[i : i + span]
                if any(left[1] > right[0] for left, right in zip(bundle, bundle[1:])):
                    continue
                if abs((bundle[-1][1] - u_end).total_seconds()) > MAX_TIME_SKEW_SECONDS:
                    continue
                bundle_words = tuple(word for _, _, words in bundle for word in words)
                if (bundle[-1][1] - bundle[0][0]).total_seconds() > MAX_BUNDLE_SECONDS:
                    continue
                if len(bundle_words) > MAX_BUNDLE_WORDS:
                    continue
                candidates.append((i, i + span - 1, bundle, bundle_words))
                if len(candidates) > MAX_TARGET_CANDIDATES:
                    raise _ContainmentRejected('bounds_candidates')
        best = None
        for i, j, bundle, bundle_words in candidates:
            if len(u_bigrams & _bigrams(bundle_words)) < MIN_SHARED_BIGRAMS:
                continue
            tokens = len(u_words) + len(bundle_words)
            cells = len(u_words) * len(bundle_words)
            if matcher_calls + 1 > MAX_MATCHER_CALLS:
                raise _ContainmentRejected('bounds_matcher_calls')
            if compared_tokens + tokens > MAX_COMPARED_TOKENS:
                raise _ContainmentRejected('bounds_tokens')
            if token_comparisons + cells > MAX_TOKEN_COMPARISONS:
                raise _ContainmentRejected('bounds_cells')
            matcher_calls += 1
            compared_tokens += tokens
            token_comparisons += cells
            common, matched = _ordered_match(u_words, bundle_words)
            if common / len(u_words) < MIN_PAIR_COVERAGE:
                continue
            key = (common, -abs((bundle[0][0] - u_start).total_seconds()), -j)
            if best is None or key > best[0]:
                best = (key, j, common, matched)
        if best is None:
            continue
        _, j, common, matched = best
        last_consumed = j
        matched_words += common
        matched_weight += (common / len(u_words)) * u_weight
        matched_tokens.update(matched)
        matched_utterances.add(u_words)
        if covered_until is None or u_start >= covered_until:
            support_seconds += (u_end - u_start).total_seconds()
        elif u_end > covered_until:
            support_seconds += (u_end - covered_until).total_seconds()
        covered_until = u_end if covered_until is None else max(covered_until, u_end)
    return matched_words, matched_tokens, matched_utterances, support_seconds, matched_weight


def _sample_utterances(
    eligible: list[tuple[datetime, datetime, tuple[str, ...]]],
) -> list[tuple[datetime, datetime, tuple[str, ...], int]]:
    if len(eligible) <= MAX_SMALLER_UTTERANCES:
        return [(start, end, words, len(words)) for start, end, words in eligible]
    cumulative_ends = []
    total_words = 0
    for _, _, words in eligible:
        total_words += len(words)
        cumulative_ends.append(total_words)
    hits: dict[int, int] = {}
    for i in range(MAX_SMALLER_UTTERANCES):
        position = i * (total_words - 1) // (MAX_SMALLER_UTTERANCES - 1)
        index = bisect.bisect_right(cumulative_ends, position)
        hits[index] = hits.get(index, 0) + 1
    return [(*eligible[index], hits[index]) for index in sorted(hits)]


def measure_capture_containment(first: Any, second: Any, *, mode: str = 'on') -> CaptureContainment:
    """Decide whether the smaller capture's user speech is contained in the other."""
    stats = _LayoutStats()
    try:
        decision = _measure_capture_containment(first, second, mode=mode, stats=stats)
    except _ContainmentRejected as exc:
        decision = CaptureContainment(would_join=False, reason=exc.reason)
    return replace(decision, dropped_segments=stats.dropped_segments)


def _measure_capture_containment(first: Any, second: Any, *, mode: str, stats: _LayoutStats) -> CaptureContainment:
    row_a, row_b = _window(first), _window(second)
    if row_a is None or row_b is None or row_a[2] == row_b[2]:
        return CaptureContainment(would_join=False, reason='ineligible')
    ix_start, ix_end = max(row_a[0], row_b[0]), min(row_a[1], row_b[1])
    if ix_end <= ix_start:
        return CaptureContainment(would_join=False, reason='ineligible')
    sides = []
    for start, finish, _source, segments in (row_a, row_b):
        duration = (finish - start).total_seconds()
        loaded = _in_window_segments(start, duration, ix_start, ix_end, segments, stats=stats)
        sides.append(loaded)
    words_a = sum(len(words) for _, _, _, words, _ in sides[0][0])
    words_b = sum(len(words) for _, _, _, words, _ in sides[1][0])
    small, large = (sides[0][0], sides[1][0]) if words_a <= words_b else (sides[1][0], sides[0][0])
    smaller_words = min(words_a, words_b)
    small_user = [(s, e, w) for s, e, is_user, w, _ in small if is_user]
    large_user = [(s, e, w) for s, e, is_user, w, _ in large if is_user]
    if not small_user or not large_user:
        return CaptureContainment(would_join=False, reason='no_user_speech', smaller_words=smaller_words)
    if smaller_words < MIN_SMALLER_WORDS:
        return CaptureContainment(would_join=False, reason='too_small', smaller_words=smaller_words)
    eligible = [(s, e, w) for s, e, w in small_user if len(w) >= MIN_UTTERANCE_WORDS]
    eligible_words = sum(len(words) for _, _, words in eligible)
    if mode == 'shadow' and len(eligible) > MAX_SMALLER_UTTERANCES:
        sample = _sample_utterances(eligible)
        basis = 'sampled'
    else:
        sample = [(s, e, w, len(w)) for s, e, w in eligible]
        basis = 'full'
    sample_weight = sum(weight for _, _, _, weight in sample)
    try:
        matched_words, matched_tokens, matched_utterances, support_seconds, matched_weight = _match_utterances(
            sample, large_user
        )
    except _ContainmentRejected as exc:
        return CaptureContainment(would_join=False, reason=exc.reason, basis=basis)
    if basis == 'full':
        coverage = matched_words / smaller_words
    else:
        coverage = (matched_weight / sample_weight) * (eligible_words / smaller_words) if sample_weight else 0.0
    decision = CaptureContainment(
        would_join=(
            matched_words >= MIN_MATCHED_WORDS
            and len(matched_tokens) >= MIN_DISTINCT_WORDS
            and len(matched_utterances) >= MIN_MATCHED_UTTERANCES
            and support_seconds >= MIN_SUPPORT_SECONDS
            and coverage >= MIN_COVERAGE
        ),
        reason='contained',
        matched_words=matched_words,
        smaller_words=smaller_words,
        matched_utterances=len(matched_utterances),
        distinct_words=len(matched_tokens),
        support_seconds=support_seconds,
        coverage=coverage,
        basis=basis,
    )
    if decision.would_join:
        return decision
    if matched_words == 0:
        reason = 'timing'
    elif coverage < MIN_COVERAGE:
        reason = 'insufficient_coverage'
    else:
        reason = 'too_small'
    return CaptureContainment(
        would_join=False,
        reason=reason,
        matched_words=matched_words,
        smaller_words=smaller_words,
        matched_utterances=len(matched_utterances),
        distinct_words=len(matched_tokens),
        support_seconds=support_seconds,
        coverage=coverage,
        basis=basis,
    )
