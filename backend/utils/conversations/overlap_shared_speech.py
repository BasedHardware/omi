"""Bounded, deterministic evidence of sentences heard in the same overlap.

No speaker identity, provider, LLM, persistence or configurable scoring cutoffs.
Unknown timing cannot add evidence; work overflow abstains. See docs/operational/capture-shared-speech.md.
"""

from __future__ import annotations

import bisect
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from config.capture_shared_speech import (
    MAX_CAPTURE_SEGMENTS as MAX_SEGMENTS,
    MAX_CAPTURE_CHARS as MAX_CHARS,
    MAX_CAPTURE_SEGMENT_CHARS as MAX_SEGMENT_CHARS,
)
from utils.conversations.fragment_visibility import is_completed_rule_discard

VERSION = 'overlap_shared_speech_v1'
SKEW_SECONDS = 15.0
MIN_WORDS = 30
MIN_WINDOW_JACCARD = 0.25
MIN_LINE_JACCARD = 0.5
MIN_SHARED_WORDS = 20
MIN_SHARED_BIGRAMS = 8
MIN_SUPPORT_SECONDS = 10.0
MIN_MATCHED_SPEECH_SECONDS = 15.0
MIN_LINE_SECONDS = 1.0
# Datetimes have microsecond resolution; epoch subtraction can add <1us noise.
ROUNDING_SECONDS = 0.000001
MAX_WORDS = 64000
MAX_SEGMENT_SECONDS = 90.0
MAX_COMPARISONS = 16384
MAX_TOKEN_WORK = 524288
MAX_LCS_CELLS = 262144
_WORD = re.compile(r'[^\W_]+', re.UNICODE)


def field(row: Any, name: str) -> Any:
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)


def pair_category(first: Any, second: Any) -> str:
    if field(first, 'source') != field(second, 'source'):
        return 'cross_source'
    external_a, external_b = field(first, 'external_data'), field(second, 'external_data')
    a = field(first, 'client_device_id') or (external_a.get('device_id') if isinstance(external_a, Mapping) else None)
    b = field(second, 'client_device_id') or (external_b.get('device_id') if isinstance(external_b, Mapping) else None)
    if not a or not b:
        return 'same_source_unknown_device'
    return 'same_source_same_device' if a == b else 'same_source_different_device'


@dataclass(frozen=True)
class OverlapSharedSpeech:
    would_join: bool = False
    reason: str = 'ineligible'
    window_jaccard: float = 0.0
    matched_sentences: int = 0
    shared_words: int = 0
    shared_bigrams: int = 0
    support_seconds: float = 0.0
    min_words: int = 0
    matched_speech_seconds: float = 0.0
    dropped_segments: int = 0
    unknown_words: int = 0

    def evidence(self) -> dict:
        return {
            'method': VERSION,
            'window_jaccard': round(self.window_jaccard, 4),
            'matched_sentences': self.matched_sentences,
            'shared_words': self.shared_words,
            'shared_bigrams': self.shared_bigrams,
            'support_seconds': round(self.support_seconds, 3),
            'min_words': self.min_words,
            'matched_speech_seconds': round(self.matched_speech_seconds, 3),
            'dropped_segments': self.dropped_segments,
            'unknown_words': self.unknown_words,
        }


class _Rejected(Exception):
    pass


def _epoch(value: Any) -> float:
    if not isinstance(value, datetime):
        raise _Rejected('timing')
    try:
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    except (OverflowError, OSError, ValueError):
        raise _Rejected('timing') from None


def _number(value: Any) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _window(row: Any) -> tuple[float, float]:
    if any(field(row, k) for k in ('deleted', 'discarded', 'capture_group_closed')):
        raise _Rejected('ineligible')
    if field(row, 'status') != 'completed' or not field(row, 'source'):
        raise _Rejected('ineligible')
    if isinstance(row, Mapping) and is_completed_rule_discard(row):
        raise _Rejected('ineligible')
    if field(row, 'has_transcript_corrections') or field(row, 'transcript_correction_overlay') is not None:
        raise _Rejected('transcript_corrections')
    unavailable = field(row, '_shared_speech_rejection')
    if unavailable in ('decode_bounds', 'decode_invalid'):
        raise _Rejected(unavailable)
    start, end = _epoch(field(row, 'started_at')), _epoch(field(row, 'finished_at'))
    if end <= start:
        raise _Rejected('timing')
    return start, end


def shared_speech_group_guard(rows: Mapping[str, Any], _transaction: Any, _client: Any) -> bool:
    """Recheck every member's current eligibility without decrypting in the transaction."""
    try:
        for row in rows.values():
            _window(row)
        return bool(rows) and len({bool(field(row, 'is_locked')) for row in rows.values()}) == 1
    except _Rejected:
        return False


def _lines(row: Any, window: tuple[float, float], lo: float, hi: float) -> tuple[list, int, int]:
    segments = field(row, 'transcript_segments') or []
    if not isinstance(segments, (list, tuple)):
        raise _Rejected('shape')
    if len(segments) > MAX_SEGMENTS:
        raise _Rejected('bounds')
    result = []
    chars = word_count = unknown_words = dropped_segments = 0
    for segment in segments:
        text = field(segment, 'text')
        if not isinstance(text, str):
            raise _Rejected('shape')
        chars += len(text)
        if len(text) > MAX_SEGMENT_CHARS or chars > MAX_CHARS:
            raise _Rejected('bounds')
        if not text.strip():
            continue
        start, end = field(segment, 'start'), field(segment, 'end')
        duration = window[1] - window[0]
        unusable = not _number(start) or not _number(end)
        if not unusable:
            unusable = (
                end <= start
                or start < -ROUNDING_SECONDS
                or end > duration + ROUNDING_SECONDS
                or field(segment, 'audio_alignment') == 'unplaced'
            )
        wall_start = wall_end = 0.0
        if not unusable:
            start, end = max(0.0, start), min(duration, end)
            wall_start, wall_end = window[0] + start, window[0] + end
            if wall_end <= lo or wall_start >= hi:
                continue  # trusted timestamps place all these words outside the intersection
            unusable = (
                end <= start
                or end - start > MAX_SEGMENT_SECONDS
                or wall_start < lo - ROUNDING_SECONDS
                or wall_end > hi + ROUNDING_SECONDS
            )
            wall_start, wall_end = max(lo, wall_start), min(hi, wall_end)
        normalized = unicodedata.normalize('NFKC', text).casefold().replace('’', "'").replace("'", '')
        words = tuple(_WORD.findall(normalized))
        word_count += len(words)
        if word_count > MAX_WORDS:
            raise _Rejected('bounds')
        if unusable:
            # Unknown placement cannot add evidence or inflate similarity by
            # disappearing: charge every word as distinct, unshared vocabulary.
            unknown_words += len(words)
            dropped_segments += 1
            continue
        if words:
            result.append((wall_start, words, frozenset(words), frozenset(zip(words, words[1:])), wall_end))
    return sorted(result), unknown_words, dropped_segments


def _ordered_words(a: tuple[str, ...], b: tuple[str, ...]) -> list[str]:
    """LCS alignment; the caller budgets its exact cell work before calling."""
    rows = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, word in enumerate(a, 1):
        for j, target in enumerate(b, 1):
            rows[i][j] = rows[i - 1][j - 1] + 1 if word == target else max(rows[i - 1][j], rows[i][j - 1])
    matched = []
    i, j = len(a), len(b)
    while i and j:
        if a[i - 1] == b[j - 1]:
            matched.append(a[i - 1])
            i, j = i - 1, j - 1
        elif rows[i - 1][j] >= rows[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return matched[::-1]


def _speech_seconds(lines: list, indices: set[int]) -> float:
    covered_until = float('-inf')
    seconds = 0.0
    for i in sorted(indices):
        start, end = lines[i][0], lines[i][4]
        seconds += max(0.0, end - max(start, covered_until))
        covered_until = max(covered_until, end)
    return seconds


def measure_overlap_shared_speech(first: Any, second: Any) -> OverlapSharedSpeech:
    """Require both overlap speech and two independent, time-aligned sentences.

    One-to-one line assignment prevents one line/duplicate diarization from
    supplying multiple confirmations. Repetition cannot inflate distinct support.
    """
    try:
        aw, bw = _window(first), _window(second)
        if bool(field(first, 'is_locked')) != bool(field(second, 'is_locked')):
            raise _Rejected('lock_partition')
        lo, hi = max(aw[0], bw[0]), min(aw[1], bw[1])
        if hi <= lo:
            raise _Rejected('no_overlap')
        a, unknown_a, dropped_a = _lines(first, aw, lo, hi)
        b, unknown_b, dropped_b = _lines(second, bw, lo, hi)
        unknown_words, dropped_segments = unknown_a + unknown_b, dropped_a + dropped_b
        minimum = min(sum(len(line[1]) for line in a), sum(len(line[1]) for line in b))
        if minimum < MIN_WORDS:
            return OverlapSharedSpeech(
                reason='insufficient_speech',
                min_words=minimum,
                unknown_words=unknown_words,
                dropped_segments=dropped_segments,
            )
        tokens_a = set().union(*(line[2] for line in a))
        tokens_b = set().union(*(line[2] for line in b))
        # A lower bound: adding every unknown token to the union overcharges
        # its possible size; no unknown token enters the proven intersection.
        jaccard = len(tokens_a & tokens_b) / (len(tokens_a | tokens_b) + unknown_a + unknown_b)
        if jaccard < MIN_WINDOW_JACCARD:
            return OverlapSharedSpeech(
                reason='window_text',
                window_jaccard=jaccard,
                min_words=minimum,
                unknown_words=unknown_words,
                dropped_segments=dropped_segments,
            )
        # Canonical orientation makes greedy assignment symmetric under pair reversal.
        if [(x[0], x[1]) for x in b] < [(x[0], x[1]) for x in a]:
            a, b = b, a
        starts = [line[0] for line in b]
        proposals = []
        comparisons = token_work = cells = 0
        for i, line in enumerate(a):
            if len(line[2]) < 8 or line[4] - line[0] < MIN_LINE_SECONDS:
                continue
            left = bisect.bisect_left(starts, line[0] - SKEW_SECONDS)
            right = bisect.bisect_right(starts, line[0] + SKEW_SECONDS)
            comparisons += right - left
            if comparisons > MAX_COMPARISONS:
                raise _Rejected('bounds')
            for j in range(left, right):
                target = b[j]
                if target[4] - target[0] < MIN_LINE_SECONDS:
                    continue
                token_work += len(line[2]) + len(target[2])
                if token_work > MAX_TOKEN_WORK:
                    raise _Rejected('bounds')
                common = line[2] & target[2]
                grams = line[3] & target[3]
                score = len(common) / len(line[2] | target[2])
                if len(target[2]) >= 8 and len(common) >= 6 and len(grams) >= 2 and score >= MIN_LINE_JACCARD:
                    cells += len(line[1]) * len(target[1])
                    if cells > MAX_LCS_CELLS:
                        raise _Rejected('bounds')
                    ordered = _ordered_words(line[1], target[1])
                    if len(ordered) / max(len(line[1]), len(target[1])) >= 0.6:
                        proposals.append((-score, abs(line[0] - target[0]), i, j, set(ordered), grams))
        used_a, used_b, texts_a, texts_b = set(), set(), set(), set()
        common_words, common_grams, times_a, times_b = set(), set(), [], []
        selected = []
        for _, _, i, j, common, grams in sorted(proposals):
            if i in used_a or j in used_b or a[i][1] in texts_a or b[j][1] in texts_b:
                continue
            used_a.add(i)
            used_b.add(j)
            texts_a.add(a[i][1])
            texts_b.add(b[j][1])
            selected.append((i, j, common, grams))
        # Both word order within a line and line order across the capture matter.
        used_a, used_b = set(), set()
        last_j = -1
        for i, j, common, grams in sorted(selected):
            if j <= last_j:
                continue
            last_j = j
            used_a.add(i)
            used_b.add(j)
            common_words.update(common)
            common_grams.update(grams)
            times_a.append(a[i][0])
            times_b.append(b[j][0])
        support = min(max(times_a) - min(times_a), max(times_b) - min(times_b)) if times_a else 0.0
        speech_seconds = min(_speech_seconds(a, used_a), _speech_seconds(b, used_b))
        confirms = (
            len(used_a) >= 2
            and len(common_words) >= MIN_SHARED_WORDS
            and len(common_grams) >= MIN_SHARED_BIGRAMS
            and support >= MIN_SUPPORT_SECONDS
            and speech_seconds >= MIN_MATCHED_SPEECH_SECONDS
        )
        return OverlapSharedSpeech(
            confirms,
            'shared_sentences' if confirms else 'sentence_support',
            jaccard,
            len(used_a),
            len(common_words),
            len(common_grams),
            support,
            minimum,
            speech_seconds,
            unknown_words=unknown_words,
            dropped_segments=dropped_segments,
        )
    except _Rejected as error:
        return OverlapSharedSpeech(reason=str(error))
