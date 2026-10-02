"""Shared provenance-aware placement of transcript windows onto stored audio.

Transcript segment times are conversation-relative seconds; whether they
address the stored chunks depends on how the conversation was captured. This
module is the single pure gate every audio reader shares:

- audio-timeline v2 manifests prove coverage through validated chunk spans;
- ``sync:``-scoped segments are timed by the same uploaded files that became
  the stored chunks, so their union over a window is trusted;
- every other clock — live provider scopes, ``legacy-conversation:`` donor
  scopes, this stage's own ``conversation:`` scopes, or no scope at all — is
  provisional: a caller may still cut a candidate at the provisional position,
  but only behind the mandatory transcript verification;
- an explicitly unplaced contributor or a missing/invalid origin refuses
  outright, because a wrong window is worse than none.

A returned window proves coordinates, not decoded bytes. Everything here is
pure: no environment, storage or provider access.
"""

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, Tuple

from database.audio_timeline import COVERAGE_TOLERANCE_SECONDS, chunk_span_bounds
from utils.audio_timeline import covered_window, is_audio_timeline_v2
from utils.text_utils import compute_text_containment

TEXT_SEARCH_PAD_SECONDS = 10.0
TEXT_SEARCH_MAX_SECONDS = 32.0
TEXT_ANCHOR_MIN_TOKENS = 5
TEXT_ANCHOR_MAX_WORDS = 512

MAX_PLACEMENT_REQUEST_SECONDS = 12.0
_CANDIDATE_DEDUP_SECONDS = 0.001


@dataclass(frozen=True)
class AudioPlacement:
    window: Optional[Tuple[float, float]]
    reason: str


def _seconds(value: Any) -> Optional[float]:
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        if isinstance(value, datetime):
            value = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        return float(value)
    except (OverflowError, ValueError):
        return None


def _numeric(value: Any) -> Optional[float]:
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        return float(value)
    except (OverflowError, ValueError):
        return None


def _origin(conversation: Mapping[str, Any], *, allow_created_at: bool) -> Optional[float]:
    started_at = conversation.get('started_at')
    if started_at is None or (isinstance(started_at, str) and not started_at.strip()):
        return _seconds(conversation.get('created_at')) if allow_created_at else None
    return _seconds(started_at)


def provisional_window(conversation: Mapping[str, Any], start: float, end: float) -> Optional[Tuple[float, float]]:
    start_f = _numeric(start)
    end_f = _numeric(end)
    if start_f is None or end_f is None or start_f < 0 or end_f <= start_f:
        return None
    origin = _origin(conversation, allow_created_at=True)
    if origin is None:
        return None
    abs_start = origin + start_f
    abs_end = origin + end_f
    if not (math.isfinite(abs_start) and math.isfinite(abs_end)) or abs_end <= abs_start:
        return None
    return (abs_start, abs_end)


def _placed_contributor(segment: Any) -> bool:
    if not isinstance(segment, Mapping) or segment.get('audio_alignment') == 'unplaced':
        return False
    seg_start = _numeric(segment.get('start'))
    seg_end = _numeric(segment.get('end'))
    return seg_start is not None and seg_end is not None and seg_start >= 0 and seg_end > seg_start


def _overlapping_segments(conversation: Mapping[str, Any], start: float, end: float) -> list:
    overlapping = []
    for segment in conversation.get('transcript_segments') or []:
        if not isinstance(segment, Mapping):
            continue
        seg_start = _numeric(segment.get('start'))
        seg_end = _numeric(segment.get('end'))
        if seg_start is not None and seg_end is not None and seg_start < end and seg_end > start:
            overlapping.append(segment)
    return overlapping


def _v2_manifest_valid(audio_files: Any) -> bool:
    if not isinstance(audio_files, Sequence) or isinstance(audio_files, (str, bytes)) or not audio_files:
        return False
    for audio_file in audio_files:
        if not isinstance(audio_file, Mapping):
            return False
        spans: Any = audio_file.get('chunk_spans')
        timestamps: Any = audio_file.get('chunk_timestamps')
        for value in (spans, timestamps):
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
                return False
        if len(spans) != len(timestamps):
            return False
        if any(_numeric(ts) is None for ts in timestamps):
            return False
        if any(chunk_span_bounds(span) is None for span in spans):
            return False
    return True


def _union_covers(contributors: Sequence[Mapping[str, Any]], start: float, end: float) -> bool:
    bounds = [(_numeric(s.get('start')), _numeric(s.get('end'))) for s in contributors]
    intervals = sorted((a, b) for a, b in bounds if a is not None and b is not None)
    remaining = start
    for seg_start, seg_end in intervals:
        if seg_start > remaining + COVERAGE_TOLERANCE_SECONDS:
            return False
        if seg_end > remaining:
            remaining = seg_end
            if remaining >= end - COVERAGE_TOLERANCE_SECONDS:
                return True
    return False


def locate(
    conversation: Mapping[str, Any],
    start: float,
    end: float,
    *,
    segments: Optional[Sequence[Mapping[str, Any]]] = None,
) -> AudioPlacement:
    """Map ``[start, end)`` (conversation-relative) onto stored audio, or refuse.

    ``reason`` is one of ``v2`` / ``sync`` (a window is returned and may be
    trusted), ``untrusted_clock`` (no window; a provisional candidate is the
    caller's risk), ``uncovered_audio`` / ``unplaced`` / ``missing_origin`` /
    ``invalid_window`` (no window; the caller must not guess).
    """
    start_f = _numeric(start)
    end_f = _numeric(end)
    if start_f is None or end_f is None or start_f < 0 or end_f <= start_f:
        return AudioPlacement(None, 'invalid_window')

    contributors = list(segments) if segments is not None else _overlapping_segments(conversation, start_f, end_f)
    if any(not _placed_contributor(s) for s in contributors):
        return AudioPlacement(None, 'unplaced')

    origin = _origin(conversation, allow_created_at=False)
    if origin is None:
        return AudioPlacement(None, 'missing_origin')
    abs_start, abs_end = origin + start_f, origin + end_f
    if not (math.isfinite(abs_start) and math.isfinite(abs_end)) or abs_end <= abs_start:
        return AudioPlacement(None, 'invalid_window')

    if is_audio_timeline_v2(conversation):
        normalized = dict(conversation)
        normalized['started_at'] = origin
        if not _v2_manifest_valid(normalized.get('audio_files')):
            return AudioPlacement(None, 'uncovered_audio')
        if covered_window(normalized.get('audio_files'), abs_start, abs_end):
            return AudioPlacement((abs_start, abs_end), 'v2')
        return AudioPlacement(None, 'uncovered_audio')

    if conversation.get('audio_timeline'):
        return AudioPlacement(None, 'untrusted_clock')

    if not contributors:
        return AudioPlacement(None, 'untrusted_clock')
    for segment in contributors:
        scope = segment.get('speaker_id_scope')
        if not isinstance(scope, str) or not scope.startswith('sync:') or len(scope) == len('sync:'):
            return AudioPlacement(None, 'untrusted_clock')
    if not _union_covers(contributors, start_f, end_f):
        return AudioPlacement(None, 'untrusted_clock')
    return AudioPlacement((abs_start, abs_end), 'sync')


def _tokens(text: str) -> list:
    return re.findall(r"\w+(?:['’]\w+)*", unicodedata.normalize('NFC', text).casefold())


def locate_in_verified_words(
    expected_text: str,
    words: Sequence[Mapping[str, Any]],
    duration: float,
    *,
    audio_duration: float,
    anchor_offset: float = 0.0,
) -> AudioPlacement:
    """Anchor ``expected_text`` inside word-timed audio, or refuse.

    ``words`` must be word-granular: each entry carries a ``timestamp`` pair of
    seconds inside ``[0, audio_duration]`` and text holding exactly one token.
    A returned window is relative to the start of the submitted audio; add the
    search window's absolute start to recover wall seconds.
    """
    duration_f = _numeric(duration)
    audio_f = _numeric(audio_duration)
    offset_f = _numeric(anchor_offset)
    if (
        duration_f is None
        or audio_f is None
        or offset_f is None
        or duration_f <= 0
        or duration_f > MAX_PLACEMENT_REQUEST_SECONDS
        or audio_f <= 0
        or audio_f > TEXT_SEARCH_MAX_SECONDS
        or offset_f < 0
    ):
        return AudioPlacement(None, 'invalid_window')
    words_any: Any = words
    if not isinstance(words_any, Sequence) or isinstance(words_any, (str, bytes)):
        return AudioPlacement(None, 'unsupported_word_times')
    if len(words) > TEXT_ANCHOR_MAX_WORDS:
        return AudioPlacement(None, 'unsupported_word_times')
    if len(words) < TEXT_ANCHOR_MIN_TOKENS:
        return AudioPlacement(None, 'insufficient_anchor')

    prefix = _tokens(expected_text)[:TEXT_ANCHOR_MIN_TOKENS]
    if len(prefix) < TEXT_ANCHOR_MIN_TOKENS:
        return AudioPlacement(None, 'insufficient_anchor')

    starts = []
    ends = []
    tokens = []
    texts = []
    previous_start = 0.0
    for word in words:
        word_any: Any = word
        if not isinstance(word_any, Mapping):
            return AudioPlacement(None, 'unsupported_word_times')
        timestamp = word.get('timestamp')
        if isinstance(timestamp, (str, bytes)) or not isinstance(timestamp, Sequence) or len(timestamp) != 2:
            return AudioPlacement(None, 'unsupported_word_times')
        word_start = _numeric(timestamp[0])
        word_end = _numeric(timestamp[1])
        if (
            word_start is None
            or word_end is None
            or word_start < 0
            or word_end <= word_start
            or word_end > audio_f
            or word_start < previous_start
        ):
            return AudioPlacement(None, 'unsupported_word_times')
        text = word.get('text')
        if not isinstance(text, str):
            return AudioPlacement(None, 'unsupported_word_times')
        word_tokens = _tokens(text)
        if len(word_tokens) != 1:
            return AudioPlacement(None, 'unsupported_word_times')
        previous_start = word_start
        starts.append(word_start)
        ends.append(word_end)
        tokens.append(word_tokens[0])
        texts.append(text)

    accepted = []
    for index in range(0, len(tokens) - TEXT_ANCHOR_MIN_TOKENS + 1):
        if tokens[index : index + TEXT_ANCHOR_MIN_TOKENS] != prefix:
            continue
        first = starts[index] + offset_f
        last = first + duration_f
        if not (0 <= first < last <= audio_f):
            continue
        selected = [texts[j] for j in range(len(words)) if starts[j] < last and ends[j] > first]
        if len(selected) < TEXT_ANCHOR_MIN_TOKENS:
            continue
        if compute_text_containment(' '.join(selected), expected_text) < 0.9:
            continue
        if not any(abs(first - prior) <= _CANDIDATE_DEDUP_SECONDS for prior in accepted):
            accepted.append(first)

    if len(accepted) == 1:
        first = accepted[0]
        return AudioPlacement((first, first + duration_f), 'text_anchor')
    if not accepted:
        return AudioPlacement(None, 'text_anchor_missing')
    return AudioPlacement(None, 'ambiguous_text_anchor')
