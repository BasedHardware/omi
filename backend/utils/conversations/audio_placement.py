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

import bisect
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, Tuple

from database.audio_timeline import COVERAGE_TOLERANCE_SECONDS, chunk_span_bounds
from utils.audio_timeline import is_audio_timeline_v2
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


CAPTURE_CLOCK_TOLERANCE_SECONDS = 1.0


def capture_window(
    conversation: Mapping[str, Any],
    start: float,
    end: float,
    *,
    segments: Optional[Sequence[Mapping[str, Any]]] = None,
    tolerance: float = CAPTURE_CLOCK_TOLERANCE_SECONDS,
) -> Optional[Tuple[float, float]]:
    """Where the live receiver heard ``[start, end)``, when every contributor recorded it.

    Legacy live text is timed from the provider stream and stored audio from chunk
    arrival; reconnects and failover pull those clocks apart, so ``started_at + start``
    often misses the audio. ``audio_capture_start``/``audio_capture_end`` hold the
    receiver's capture-clock window for the segment. All contributors must agree on
    one offset between transcript time and capture time, and keep their duration.
    The result is a second candidate, not proof: the capture clock and the chunk
    clock can still disagree, so callers keep their transcript verification.
    """
    start_f = _numeric(start)
    end_f = _numeric(end)
    if start_f is None or end_f is None or start_f < 0 or end_f <= start_f:
        return None
    contributors = list(segments) if segments is not None else _overlapping_segments(conversation, start_f, end_f)
    if not contributors:
        return None
    offsets = []
    for segment in contributors:
        if not _placed_contributor(segment):
            return None
        seg_start = _numeric(segment.get('start'))
        seg_end = _numeric(segment.get('end'))
        cap_start = _numeric(segment.get('audio_capture_start'))
        cap_end = _numeric(segment.get('audio_capture_end'))
        if seg_start is None or seg_end is None or cap_start is None or cap_end is None or cap_end <= cap_start:
            return None
        if abs((cap_end - cap_start) - (seg_end - seg_start)) > tolerance:
            return None
        offsets.append(cap_start - seg_start)
    if max(offsets) - min(offsets) > tolerance:
        return None
    offset = sorted(offsets)[len(offsets) // 2]
    return (start_f + offset, end_f + offset)


CAPTURE_RETRY_MIN_SHIFT_SECONDS = 0.25


def capture_shift(
    conversation: Mapping[str, Any],
    start: float,
    end: float,
    *,
    segments: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Optional[float]:
    """Seconds between the capture window and the legacy position, or None when either is unknown.

    Verified readers cut at the legacy position first, because the capture clock and the
    stored-chunk clock differ by ordinary arrival jitter. Only when that cut fails and the
    capture window sits somewhere materially different is it worth one more attempt.
    """
    capture = capture_window(conversation, start, end, segments=segments)
    legacy = provisional_window(conversation, start, end)
    if capture is None or legacy is None:
        return None
    return capture[0] - legacy[0]


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


@dataclass(frozen=True)
class PreparedAudioCoverage:
    """One-pass validated span index: merged union ``coverage`` plus merged
    ``ambiguity`` intervals (regions two or more distinct ``chunk_spans``
    entries cover). Immutable sorted ``(start, end)`` tuples for ``bisect``."""

    validated: bool
    coverage: Tuple[Tuple[float, float], ...] = ()
    ambiguity: Tuple[Tuple[float, float], ...] = ()

    def covers(self, start: float, end: float) -> bool:
        if not self.validated or end <= start:
            return False
        index = bisect.bisect_right(self.coverage, (start, math.inf)) - 1
        if index < 0:
            return False
        span_start, span_end = self.coverage[index]
        return span_start <= start and span_end >= end - COVERAGE_TOLERANCE_SECONDS

    def ambiguous(self, start: float, end: float) -> bool:
        index = bisect.bisect_right(self.ambiguity, (start, math.inf)) - 1
        if index >= 0 and self.ambiguity[index][1] > start:
            return True
        index += 1
        return index < len(self.ambiguity) and self.ambiguity[index][0] < end


def prepare_audio_coverage(
    audio_files: Any,
    *,
    deadline: Optional[float] = None,
    max_spans: Optional[int] = None,
) -> PreparedAudioCoverage:
    """Validate the manifest once and index coverage plus cross-span overlap.

    Every file needs equally sized non-empty ``chunk_timestamps``/
    ``chunk_spans`` arrays of finite values and well-formed spans; each
    timestamp/span pair is checked in one pass. A ``monotonic`` ``deadline``
    or a ``max_spans`` bound stops preparation anywhere — per file, per pair,
    and around the sort and sweep — and yields ``validated=False`` rather
    than a partial index. The clock is only consulted when a deadline is
    supplied.
    """
    if not isinstance(audio_files, Sequence) or isinstance(audio_files, (str, bytes)) or not audio_files:
        return PreparedAudioCoverage(validated=False)
    spans = []
    for audio_file in audio_files:
        if deadline is not None and time.monotonic() >= deadline:
            return PreparedAudioCoverage(validated=False)
        if not isinstance(audio_file, Mapping):
            return PreparedAudioCoverage(validated=False)
        file_spans: Any = audio_file.get('chunk_spans')
        timestamps: Any = audio_file.get('chunk_timestamps')
        for value in (file_spans, timestamps):
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
                return PreparedAudioCoverage(validated=False)
        if len(file_spans) != len(timestamps):
            return PreparedAudioCoverage(validated=False)
        if max_spans is not None and len(spans) + len(file_spans) > max_spans:
            return PreparedAudioCoverage(validated=False)
        for timestamp, span in zip(timestamps, file_spans):
            if deadline is not None and time.monotonic() >= deadline:
                return PreparedAudioCoverage(validated=False)
            if _numeric(timestamp) is None:
                return PreparedAudioCoverage(validated=False)
            bounds = chunk_span_bounds(span)
            if bounds is None:
                return PreparedAudioCoverage(validated=False)
            spans.append(bounds)
    if deadline is not None and time.monotonic() >= deadline:
        return PreparedAudioCoverage(validated=False)
    spans.sort()
    if deadline is not None and time.monotonic() >= deadline:
        return PreparedAudioCoverage(validated=False)
    coverage = []
    ambiguity = []
    max_prior_end: Optional[float] = None
    for start, end in spans:
        if deadline is not None and time.monotonic() >= deadline:
            return PreparedAudioCoverage(validated=False)
        if coverage and start <= coverage[-1][1] + COVERAGE_TOLERANCE_SECONDS:
            coverage[-1] = (coverage[-1][0], max(coverage[-1][1], end))
        else:
            coverage.append((start, end))
        if max_prior_end is not None and max_prior_end > start:
            overlap = (start, min(end, max_prior_end))
            if ambiguity and overlap[0] <= ambiguity[-1][1]:
                ambiguity[-1] = (ambiguity[-1][0], max(ambiguity[-1][1], overlap[1]))
            else:
                ambiguity.append(overlap)
        if max_prior_end is None or end > max_prior_end:
            max_prior_end = end
    if deadline is not None and time.monotonic() >= deadline:
        return PreparedAudioCoverage(validated=False)
    return PreparedAudioCoverage(
        validated=True,
        coverage=tuple(coverage),
        ambiguity=tuple(ambiguity),
    )


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


def saved_sync_window(segment: Mapping[str, Any], origin: float) -> bool:
    """A stored ``audio_source`` marker that still matches this segment's position.

    Proof only while it describes exactly where the segment sits now: finite
    ordered endpoints equal to ``origin + segment.start/end``. A rebased donor
    keeps its absolute endpoints; a retimed, malformed or non-sync marker is
    no evidence at all.
    """
    source = segment.get('audio_source')
    if not isinstance(source, Mapping) or source.get('type') != 'sync':
        return False
    src_start = _numeric(source.get('start'))
    src_end = _numeric(source.get('end'))
    seg_start = _numeric(segment.get('start'))
    seg_end = _numeric(segment.get('end'))
    if src_start is None or src_end is None or seg_start is None or seg_end is None or src_end <= src_start:
        return False
    return (
        abs(src_start - (origin + seg_start)) <= COVERAGE_TOLERANCE_SECONDS
        and abs(src_end - (origin + seg_end)) <= COVERAGE_TOLERANCE_SECONDS
    )


def text_window_refusal(start: float, end: float) -> Optional[str]:
    """A bounded reason for malformed raw text endpoints, independent of audio clocks."""
    start_f, end_f = _numeric(start), _numeric(end)
    if start_f is None or end_f is None or start_f < 0 or end_f < start_f:
        return 'invalid_text_window'
    if end_f == start_f:
        return 'zero_text_window'
    return None


def locate(
    conversation: Mapping[str, Any],
    start: float,
    end: float,
    *,
    segments: Optional[Sequence[Mapping[str, Any]]] = None,
    capture_spans: bool = False,
    coverage: Optional[PreparedAudioCoverage] = None,
) -> AudioPlacement:
    """Map ``[start, end)`` (conversation-relative) onto stored audio, or refuse.

    ``reason`` is one of ``v2`` / ``sync`` / ``capture_span`` (a window is
    returned and may be trusted), ``untrusted_clock`` (no window; a
    provisional candidate is the caller's risk), ``uncovered_audio`` /
    ``unplaced`` / ``missing_origin`` / ``invalid_window`` (no window; the
    caller must not guess).

    ``capture_spans`` admits a live segment's receiver-recorded capture
    window as trusted only when the contributors cover the requested text
    window, every contributor carries complete finite ordered capture fields
    whose offset and duration agree within the strict 1 ms coverage
    tolerance, the whole ``audio_files`` manifest passes the v2 validator
    (every chunk has a finite span paired with a timestamp), and validated
    span coverage fully contains the capture window. Any gap — a spanless or
    malformed manifest, an uncovered hiatus, a missing or conflicting
    contributor — stays ``untrusted_clock``; a real manifest that mixes
    span-bearing and legacy chunks is refused rather than half-trusted.
    """
    start_f = _numeric(start)
    end_f = _numeric(end)
    if start_f is None or end_f is None or text_window_refusal(start, end) is not None:
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
        index = coverage if coverage is not None else prepare_audio_coverage(conversation.get('audio_files'))
        if not index.validated:
            return AudioPlacement(None, 'uncovered_audio')
        if index.ambiguous(abs_start, abs_end):
            return AudioPlacement(None, 'uncovered_audio')
        if index.covers(abs_start, abs_end):
            return AudioPlacement((abs_start, abs_end), 'v2')
        return AudioPlacement(None, 'uncovered_audio')

    if conversation.get('audio_timeline'):
        return AudioPlacement(None, 'untrusted_clock')

    if not contributors:
        return AudioPlacement(None, 'untrusted_clock')
    all_sync = True
    for segment in contributors:
        scope = segment.get('speaker_id_scope')
        is_sync_scope = isinstance(scope, str) and scope.startswith('sync:') and len(scope) > len('sync:')
        if not is_sync_scope and not saved_sync_window(segment, origin):
            all_sync = False
            break
    if all_sync:
        if not _union_covers(contributors, start_f, end_f):
            return AudioPlacement(None, 'untrusted_clock')
        index = coverage if coverage is not None else prepare_audio_coverage(conversation.get('audio_files'))
        if index.validated and index.ambiguous(abs_start, abs_end):
            return AudioPlacement(None, 'untrusted_clock')
        return AudioPlacement((abs_start, abs_end), 'sync')
    if capture_spans:
        if not _union_covers(contributors, start_f, end_f):
            return AudioPlacement(None, 'untrusted_clock')
        window = capture_window(
            conversation,
            start_f,
            end_f,
            segments=contributors,
            tolerance=COVERAGE_TOLERANCE_SECONDS,
        )
        if window is None:
            return AudioPlacement(None, 'untrusted_clock')
        index = coverage if coverage is not None else prepare_audio_coverage(conversation.get('audio_files'))
        if not index.validated:
            return AudioPlacement(None, 'untrusted_clock')
        if index.ambiguous(window[0], window[1]):
            return AudioPlacement(None, 'untrusted_clock')
        if not index.covers(window[0], window[1]):
            return AudioPlacement(None, 'untrusted_clock')
        return AudioPlacement(window, 'capture_span')
    return AudioPlacement(None, 'untrusted_clock')


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
