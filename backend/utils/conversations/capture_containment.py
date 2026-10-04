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

import difflib
import itertools
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

MODE_ENV = 'CAPTURE_GROUP_CONTAINMENT_MODE'
_MODES = ('off', 'shadow', 'on')
_PHASES = ('rule', 'jev')
_REASONS = (
    'contained',
    'no_user_speech',
    'too_small',
    'insufficient_coverage',
    'timing',
    'bounds',
    'ineligible',
)

MAX_SEGMENTS = 1024
MAX_SEGMENT_CHARS = 2048
MAX_CAPTURE_CHARS = 131072
MAX_CAPTURE_WORDS = 16000
MAX_SEGMENT_WORDS = 128
MAX_SEGMENT_SECONDS = 90.0
MAX_TARGET_CANDIDATES = 16
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
    score = 'unavailable'
    if isinstance(jev_p, (int, float)) and not isinstance(jev_p, bool):
        if math.isfinite(jev_p) and 0 <= jev_p <= 1:
            score = f'{round(float(jev_p), 6):f}'
    logger.info(
        'event=capture_group_containment mode=%s phase=%s would_join=%s reason=%s jev_p=%s',
        safe_mode,
        safe_phase,
        'true' if decision.would_join else 'false',
        reason,
        score,
    )


def _field(row: Any, name: str) -> Any:
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)


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
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _in_window_segments(
    started_at: datetime,
    duration_seconds: float,
    ix_start: datetime,
    ix_end: datetime,
    segments: Any,
) -> tuple[list[tuple[datetime, datetime, bool, tuple[str, ...], int]], int] | None:
    """Wholly-in-window text segments, or None on any budget/shape violation."""
    if segments is None:
        return [], 0
    if isinstance(segments, (str, bytes)) or not isinstance(segments, Iterable):
        return None
    collected = list(itertools.islice(segments, MAX_SEGMENTS + 1))
    if len(collected) > MAX_SEGMENTS:
        return None
    total_chars = 0
    total_words = 0
    placed: list[tuple[datetime, datetime, bool, tuple[str, ...], int]] = []
    for index, segment in enumerate(collected):
        text = _field(segment, 'text')
        if not isinstance(text, str) or not text.strip():
            continue
        total_chars += len(text)
        if len(text) > MAX_SEGMENT_CHARS or total_chars > MAX_CAPTURE_CHARS:
            return None
        if _field(segment, 'audio_alignment') == 'unplaced':
            return None
        start, end = _field(segment, 'start'), _field(segment, 'end')
        if not _valid_time(start) or not _valid_time(end):
            return None
        if not (0 <= start < end <= duration_seconds):
            return None
        words = tuple(_WORD.findall(text.lower()))
        total_words += len(words)
        if total_words > MAX_CAPTURE_WORDS:
            return None
        wall_start = started_at + timedelta(seconds=start)
        wall_end = started_at + timedelta(seconds=end)
        if wall_start < ix_start or wall_end > ix_end:
            continue
        if end - start > MAX_SEGMENT_SECONDS or len(words) > MAX_SEGMENT_WORDS:
            return None
        placed.append((wall_start, wall_end, _field(segment, 'is_user') is True, words, index))
    placed.sort(key=lambda item: (item[0], item[1], item[4]))
    return placed, total_words


def _bigrams(words: tuple[str, ...]) -> set[tuple[str, str]]:
    return {(words[i], words[i + 1]) for i in range(len(words) - 1)}


def _match_utterances(
    small_user: list[tuple[datetime, datetime, tuple[str, ...]]],
    target_user: list[tuple[datetime, datetime, tuple[str, ...]]],
) -> tuple[int, set[str], set[tuple[str, ...]], float] | None:
    """Greedily pair smaller user utterances with monotonic target bundles."""
    matched_words = 0
    matched_tokens: set[str] = set()
    matched_utterances: set[tuple[str, ...]] = set()
    support_start: datetime | None = None
    support_end: datetime | None = None
    last_consumed = -1
    for u_start, u_end, u_words in small_user:
        candidates = []
        skew = timedelta(seconds=MAX_TIME_SKEW_SECONDS)
        for i in range(last_consumed + 1, len(target_user)):
            if target_user[i][0] - u_start > skew:
                break
            if u_start - target_user[i][0] > skew:
                continue
            for span in range(1, MAX_BUNDLE_SPAN + 1):
                if i + span > len(target_user):
                    break
                bundle = target_user[i : i + span]
                if abs((bundle[-1][1] - u_end).total_seconds()) > MAX_TIME_SKEW_SECONDS:
                    continue
                bundle_words = tuple(word for _, _, words in bundle for word in words)
                if (bundle[-1][1] - bundle[0][0]).total_seconds() > MAX_BUNDLE_SECONDS:
                    continue
                if len(bundle_words) > MAX_BUNDLE_WORDS:
                    continue
                candidates.append((i, i + span - 1, bundle, bundle_words))
                if len(candidates) > MAX_TARGET_CANDIDATES:
                    return None
        best = None
        for i, j, bundle, bundle_words in candidates:
            blocks = difflib.SequenceMatcher(None, u_words, bundle_words, autojunk=False).get_matching_blocks()
            common = sum(block.size for block in blocks)
            if common / len(u_words) < MIN_PAIR_COVERAGE:
                continue
            if len(_bigrams(u_words) & _bigrams(bundle_words)) < MIN_SHARED_BIGRAMS:
                continue
            key = (common, -abs((bundle[0][0] - u_start).total_seconds()), -j)
            if best is None or key > best[0]:
                best = (key, j, blocks)
        if best is None:
            continue
        _, j, blocks = best
        last_consumed = j
        matched_words += sum(block.size for block in blocks)
        for block in blocks:
            matched_tokens.update(u_words[block.a : block.a + block.size])
        matched_utterances.add(u_words)
        support_start = u_start if support_start is None else min(support_start, u_start)
        support_end = u_end if support_end is None else max(support_end, u_end)
    support_seconds = (
        (support_end - support_start).total_seconds() if support_start is not None and support_end is not None else 0.0
    )
    return matched_words, matched_tokens, matched_utterances, support_seconds


def measure_capture_containment(first: Any, second: Any) -> CaptureContainment:
    """Decide whether the smaller capture's user speech is contained in the other."""
    row_a, row_b = _window(first), _window(second)
    if row_a is None or row_b is None or row_a[2] == row_b[2]:
        return CaptureContainment(would_join=False, reason='ineligible')
    ix_start, ix_end = max(row_a[0], row_b[0]), min(row_a[1], row_b[1])
    if ix_end <= ix_start:
        return CaptureContainment(would_join=False, reason='ineligible')
    sides = []
    for start, finish, _source, segments in (row_a, row_b):
        duration = (finish - start).total_seconds()
        loaded = _in_window_segments(start, duration, ix_start, ix_end, segments)
        if loaded is None:
            return CaptureContainment(would_join=False, reason='bounds')
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
    matched = _match_utterances([(s, e, w) for s, e, w in small_user if len(w) >= MIN_UTTERANCE_WORDS], large_user)
    if matched is None:
        return CaptureContainment(would_join=False, reason='bounds', smaller_words=smaller_words)
    matched_words, matched_tokens, matched_utterances, support_seconds = matched
    coverage = matched_words / smaller_words if smaller_words else 0.0
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
    )
