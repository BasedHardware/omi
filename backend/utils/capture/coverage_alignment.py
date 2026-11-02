"""Bounded cross-device speech alignment. Wall time proposes; text proves.

The existing shared-speech matcher supplies independent sentence support. A
stricter ordered alignment then proves each secondary line is retained in the
primary before the entire secondary can disappear from the event list. Labels
and speaker identities never participate. No text is returned or persisted.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping, TypeGuard

from utils.conversations.overlap_shared_speech import measure_overlap_shared_speech, SKEW_SECONDS

VERSION = 'cross_device_v1'
MAX_LINES = 512
MAX_CHARS = 131072
MAX_ALIGNMENT_WORK = 262144
_WORD = re.compile(r'[^\W_]+', re.UNICODE)


def _number(value: Any) -> TypeGuard[int | float]:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def device(row: Mapping[str, Any]) -> str | None:
    external = row.get('external_data') or {}
    evidence = row.get('capture_evidence') or {}
    return row.get('client_device_id') or external.get('device_id') or evidence.get('client_device_id')


def distinct_streams(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    if first.get('source') and second.get('source') and first['source'] != second['source']:
        return True
    a, b = device(first), device(second)
    if a and b:
        return a != b
    return False


def quality_rank(row: Mapping[str, Any]) -> tuple:
    """Pendant first, then SNR, word confidence, duration and stable identity.

    Missing quality stays below measured quality; no speaker confidence is used.
    Only server-retained acoustic metadata is read, never a user identity label.
    """
    quality: dict[str, Any] = row.get('audio_quality') or {}
    snr, confidence = quality.get('snr_db'), quality.get('word_confidence')
    snr = min(100.0, max(-100.0, snr)) if _number(snr) else -101.0
    confidence = confidence if _number(confidence) and 0 <= confidence <= 1 else -1.0
    duration = (row['finished_at'] - row['started_at']).total_seconds()
    return (0 if row.get('source') == 'omi' else 1, -snr, -confidence, -duration, str(row['id']))


def policy_metadata(row: Mapping[str, Any]) -> dict:
    """Metadata that must remain stable between alignment and commit."""
    return {
        key: row.get(key)
        for key in ('source', 'client_device_id', 'external_data', 'capture_evidence', 'audio_quality', 'is_locked')
    }


def _words(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize('NFKC', text).casefold().replace('’', "'").replace("'", '')
    return tuple(_WORD.findall(normalized))


def _lines(row: Mapping[str, Any]) -> list[tuple[float, float, tuple[str, ...]]] | None:
    segments = row.get('transcript_segments') or []
    if not isinstance(segments, list) or len(segments) > MAX_LINES:
        return None
    chars = 0
    duration = (row['finished_at'] - row['started_at']).total_seconds()
    result = []
    for segment in segments:
        text = segment.get('text')
        if not isinstance(text, str):
            return None
        chars += len(text)
        if chars > MAX_CHARS:
            return None
        if not text.strip():
            continue
        start, end = segment.get('start'), segment.get('end')
        if (
            not _number(start)
            or not _number(end)
            or start < 0
            or end <= start
            or end > duration
            or segment.get('audio_alignment') == 'unplaced'
        ):
            return None
        words = _words(text)
        if words:
            result.append((row['started_at'].timestamp() + start, row['started_at'].timestamp() + end, words))
    return sorted(result)


@dataclass(frozen=True)
class Alignment:
    primary_id: str | None = None
    secondary_id: str | None = None
    would_fold: bool = False
    reason: str = 'unconfirmed'
    duplicate_lines: int = 0
    secondary_lines: int = 0

    @property
    def duplicate_line_rate(self) -> float:
        return self.duplicate_lines / self.secondary_lines if self.secondary_lines else 0.0

    def evidence(self) -> dict:
        return {
            'method': VERSION,
            'duplicate_lines': self.duplicate_lines,
            'secondary_lines': self.secondary_lines,
            'duplicate_line_rate': round(self.duplicate_line_rate, 4),
        }


def align(first: Mapping[str, Any], second: Mapping[str, Any]) -> Alignment:
    if not distinct_streams(first, second):
        return Alignment(reason='same_or_unknown_device')
    confirmation = measure_overlap_shared_speech(first, second)
    if not confirmation.would_join:
        # Include hard negatives in the denominator, rather than reporting an
        # artificial 100% duplicate rate over confirmed pairs alone.
        examined = min(len(first.get('transcript_segments') or []), len(second.get('transcript_segments') or []))
        return Alignment(reason=confirmation.reason, secondary_lines=min(examined, MAX_LINES))
    primary, secondary = sorted((first, second), key=quality_rank)
    a, b = _lines(primary), _lines(secondary)
    if not a or not b:
        return Alignment(reason='alignment_bounds')
    matched = work = 0
    last = -1
    for start, end, words in b:
        choices = []
        for index, (target_start, target_end, target) in enumerate(a):
            if index <= last or abs(start - target_start) > SKEW_SECONDS or abs(end - target_end) > SKEW_SECONDS:
                continue
            work += len(words) * len(target)
            if work > MAX_ALIGNMENT_WORK:
                return Alignment(reason='alignment_bounds')
            # Require ordered near-complete speech on both sides. A sentence
            # sharing a few phrases cannot authorize custody or hide new words.
            score = SequenceMatcher(None, words, target, autojunk=False).ratio()
            if score >= 0.95:
                choices.append((-score, abs(start - target_start), index))
        if choices:
            last = min(choices)[2]
            matched += 1
    complete = matched == len(b)
    return Alignment(
        str(primary['id']),
        str(secondary['id']),
        complete,
        'shared_speech' if complete else 'secondary_has_unique_speech',
        matched,
        len(b),
    )
