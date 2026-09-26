"""Pure audio-timeline v2 primitives.

One per-listen-socket integer capture sample cursor owns the order of decoded
PCM16 mono. Provider sends carry references to that PCM; pusher audio packets
and persisted segment offsets are projections of it. Provider timestamps are
translated through the *actual accepted provider-send spans*, never by
subtracting a wall-clock delta or extrapolating from the last callback.

Everything in this module is pure: no IO, no clocks, no env. Callers pass
arrival observations in. ``project(sample)`` is piecewise sample-linear with an
arrival-time anchor at the first accepted decoded frame and at each explicitly
observed inter-arrival hiatus; anchors are never stored as a second playback
index (stored segment and blob offsets are already projected).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, cast

# Pure span helpers live in the database-layer module (stdlib only) so
# database/ can share them without importing utils/.
from database.audio_timeline import COVERAGE_TOLERANCE_SECONDS, chunk_span_bounds

# Measured inter-arrival gap beyond which a new anchor is set. This is a jitter
# guard, not a semantic silence boundary: a client still sending PCM silence
# advances samples normally and never anchors.
ANCHOR_GAP_SECONDS = 2.0

# Bound on retained anchors: keep the first anchor (so early remaps survive)
# plus the most recent ones. Each anchor is 2 numbers; 64 covers a session with
# a hiatus every few minutes.
MAX_ANCHORS = 64

# Provider timestamps may overshoot the last accepted send sample by the
# provider's own tail buffering (a frame or two of flushed audio). Beyond this
# tolerance the timestamp belongs to audio we cannot prove was accepted, so it
# is rejected instead of silently mapped onto our epoch.
PROVIDER_EDGE_TOLERANCE_SECONDS = 0.25

# Send-span storage bound. Contiguous sends merge into one span, so this counts
# silence gaps / failovers, not chunks. When the front is evicted, mappings for
# evicted provider time fail closed (None) rather than guessing.
MAX_SEND_SPANS = 4096

AUDIO_TIMELINE_V2 = 2
# V2 audio spans start at offset zero or later. A negative offset cannot be
# resolved by released clients which only inspect segment.start when seeking.
UNPLACED_SEGMENT_OFFSET = -1.0

CoverageOutcome = str  # 'covered' | 'missing' | 'pending_upload' | 'no_audio' | 'unsupported'


def is_audio_timeline_v2(conversation: Mapping) -> bool:
    """True when the conversation row carries the v2 provenance marker."""
    marker = conversation.get('audio_timeline')
    return isinstance(marker, Mapping) and marker.get('version') == AUDIO_TIMELINE_V2


def _started_at_seconds(conversation: Mapping) -> Optional[float]:
    started_at = conversation.get('started_at')
    if started_at is None:
        return None
    if hasattr(started_at, 'timestamp'):
        return float(started_at.timestamp())
    try:
        return float(started_at)
    except (TypeError, ValueError):
        return None


def segment_wall_window(conversation: Mapping, start: float, end: float) -> Optional[Tuple[float, float]]:
    """The one coordinate conversion: conversation-relative offsets -> absolute wall seconds.

    For v2 the projection is simply ``started_at + start/end`` after finite and
    ordered-endpoint checks; for v1 the same formula is preserved (the legacy
    frame already used started_at + offset) without promising semantic
    correctness. Returns None when the conversation or the window is unusable.
    """
    started = _started_at_seconds(conversation)
    if started is None:
        return None
    try:
        start_f, end_f = float(start), float(end)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(start_f) and math.isfinite(end_f)):
        return None
    # Half-open [start, end): an empty window is not a window.
    if end_f < start_f:
        return None
    return (started + start_f, started + end_f)


def _validated_chunk_spans(audio_files: Optional[Sequence]) -> Optional[List[Tuple[float, float]]]:
    """Union-merge the validated ``chunk_spans`` of every audio file.

    Returns None when no file carries spans (legacy lists) or any span is
    malformed: a malformed span fails closed rather than guessing coverage.
    """
    spans: List[Tuple[float, float]] = []
    saw_any = False
    for audio_file in audio_files or []:
        if not isinstance(audio_file, Mapping):
            return None
        raw = audio_file.get('chunk_spans')
        if not raw:
            continue
        saw_any = True
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return None
        for item in raw:
            bounds = chunk_span_bounds(item)
            if bounds is None:
                return None
            spans.append(bounds)
    if not saw_any:
        return None
    spans.sort()
    merged: List[Tuple[float, float]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1] + COVERAGE_TOLERANCE_SECONDS:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def covered_window(
    audio_files: Optional[Sequence], abs_start: float, abs_end: float, *, tolerance: float = COVERAGE_TOLERANCE_SECONDS
) -> bool:
    """True only when validated ``chunk_spans`` cover ``[abs_start, abs_end)``.

    A timestamp list alone never proves coverage: legacy files without spans
    return False here (they are at best a candidate), and v2 files with
    malformed spans fail closed the same way.
    """
    if abs_end <= abs_start:
        return False
    spans = _validated_chunk_spans(audio_files)
    if spans is None:
        return False
    remaining_start, remaining_end = abs_start, abs_end
    for start, end in spans:
        if end + tolerance <= remaining_start:
            continue
        if start > remaining_start + tolerance:
            return False
        if start > remaining_start:
            return False
        if end >= remaining_end - tolerance:
            return True
        remaining_start = end
    return False


def coverage_outcome(conversation: Mapping, start: float, end: float) -> CoverageOutcome:
    """Richer check for audio-linked features: never guesses ``covered``.

    ``covered`` requires validated span coverage of the requested window;
    ``missing`` when v2 spans exist but do not cover it; ``pending_upload``
    when private-cloud sync is on but no audio_files have landed yet;
    ``no_audio`` when the conversation has no private-cloud storage at all;
    ``unsupported`` when the stored audio is legacy (no span metadata).
    """
    window = segment_wall_window(conversation, start, end)
    if window is None:
        return 'missing'
    audio_files = conversation.get('audio_files') or []
    if not conversation.get('private_cloud_sync_enabled') and not audio_files:
        return 'no_audio'
    if not audio_files:
        return 'pending_upload'
    spans = _validated_chunk_spans(audio_files)
    if spans is None:
        return 'unsupported'
    abs_start, abs_end = window
    return 'covered' if covered_window(audio_files, abs_start, abs_end) else 'missing'


@dataclass
class CaptureTimeline:
    """Integer capture sample cursor over decoded PCM16 mono output.

    ``accept`` is called once per successfully decoded frame with the arrival
    observations; it returns the sample range the frame occupies and whether a
    new anchor was recorded. ``wall`` projects a sample position onto the
    server-derived wall-time axis. The clock counts decoded output samples,
    not wire bytes, and never advances on invalid/empty frames.
    """

    sample_rate: int
    next_sample: int = 0
    anchors: List[Tuple[int, float]] = field(default_factory=list)
    last_monotonic: Optional[float] = None
    wall_backward_events: int = 0
    # Once compaction has dropped interior anchors, samples below the oldest
    # retained interior anchor can no longer be projected truthfully; see
    # ``wall_strict``.
    compacted_below_sample: Optional[int] = None

    def accept(self, pcm: bytes, arrival_wall: float, arrival_monotonic: float) -> Tuple[int, int, bool]:
        """Account one accepted decoded frame; returns (start, end, new_anchor)."""
        samples = len(pcm) // 2
        start = self.next_sample
        if samples <= 0:
            return (start, start, False)
        end = start + samples
        # End-of-frame convention: the frame's first sample is estimated at
        # arrival minus the whole frame duration.
        first_sample_wall = arrival_wall - samples / self.sample_rate
        new_anchor = False
        if not self.anchors:
            self.anchors.append((start, first_sample_wall))
            new_anchor = True
        else:
            projected_end = self.wall(start)
            wall_gap = first_sample_wall - projected_end
            monotonic_gap = arrival_monotonic - self.last_monotonic if self.last_monotonic is not None else 0.0
            if wall_gap < -COVERAGE_TOLERANCE_SECONDS:
                # A wall-clock adjustment is not an hour of recorded audio:
                # keep projecting from the previous interval and record the
                # uncertainty. The monotonic guard below independently blocks
                # a false hiatus.
                self.wall_backward_events += 1
            elif wall_gap > ANCHOR_GAP_SECONDS and monotonic_gap > ANCHOR_GAP_SECONDS:
                # A measured inter-arrival hiatus: anchor at the estimated
                # first-sample wall, never earlier than the previous
                # projected end.
                self.anchors.append((start, max(first_sample_wall, projected_end)))
                new_anchor = True
                self._compact_anchors()
        self.last_monotonic = arrival_monotonic
        self.next_sample = end
        return (start, end, new_anchor)

    def _compact_anchors(self) -> None:
        if len(self.anchors) <= MAX_ANCHORS:
            return
        # Keep the first anchor (early remaps) plus the most recent ones.
        self.anchors = [self.anchors[0]] + self.anchors[-(MAX_ANCHORS - 1) :]
        # Samples between the first anchor and the oldest retained interior
        # anchor have lost the anchors that described their wall projection;
        # strict readers must refuse them instead of extrapolating across the
        # dropped hiatuses.
        oldest_retained_interior = self.anchors[1][0]
        if self.compacted_below_sample is None or self.compacted_below_sample > oldest_retained_interior:
            self.compacted_below_sample = oldest_retained_interior

    def wall(self, sample: int) -> float:
        """Project a capture sample position onto the wall-time axis."""
        if not self.anchors:
            raise ValueError('wall() called before any accepted frame')
        anchor_sample, anchor_wall = self.anchors[-1]
        if sample >= anchor_sample:
            return anchor_wall + (sample - anchor_sample) / self.sample_rate
        # Before the newest anchor: walk back to the newest anchor at or
        # before the sample so each monotone interval keeps its own slope.
        anchor_sample, anchor_wall = self.anchors[0]
        for candidate_sample, candidate_wall in self.anchors:
            if candidate_sample <= sample:
                anchor_sample, anchor_wall = candidate_sample, candidate_wall
            else:
                break
        return anchor_wall + (sample - anchor_sample) / self.sample_rate

    def wall_strict(self, sample: int) -> Optional[float]:
        """``wall`` that refuses samples whose anchors compaction evicted.

        Compaction keeps the first anchor plus the most recent ones; a sample
        inside a dropped interval would project from the first anchor's slope
        as if the evicted hiatuses never happened. Callers that must not
        guess (persistence, speaker-ID windows) use this and treat None as
        "position unknowable".
        """
        if self.compacted_below_sample is not None and sample < self.compacted_below_sample:
            return None
        return self.wall(sample)


class SendMap:
    """Accepted provider-audio spans for one provider connection (epoch).

    Tracks ``(provider_first_sample, capture_first_sample, length_samples)``
    at the provider sample rate. Provider timestamps are translated only
    through spans that were actually accepted by a ``raw.send`` that returned
    success; a failed send does not consume provider time, and a resend on a
    new connection starts a new epoch (a new SendMap).
    """

    def __init__(self, provider_sample_rate: int, max_spans: int = MAX_SEND_SPANS):
        self.provider_sample_rate = provider_sample_rate
        self._max_spans = max_spans
        self._spans: List[List[int]] = []  # [provider_first, capture_first, length]
        self.evicted_spans = 0

    @property
    def span_count(self) -> int:
        return len(self._spans)

    @property
    def last_capture_sample(self) -> Optional[int]:
        """Last accepted capture boundary, for text-only fallback placement."""
        if not self._spans:
            return None
        return self._spans[-1][1] + self._spans[-1][2]

    @property
    def last_provider_sample(self) -> Optional[int]:
        if not self._spans:
            return None
        return self._spans[-1][0] + self._spans[-1][2]

    def point_interval(self, provider_sample: int) -> Optional[Tuple[int, int]]:
        """A one-sample interval for an in-span zero-duration provider point.

        Some adapters emit a final word with equal endpoints. The provider
        point still identifies an accepted sample; keep its text and a real
        capture window without extending it into unaccepted audio.
        """
        span = self._locate(provider_sample)
        if span is None:
            return None
        provider_first, capture_first, length = span
        if provider_sample < provider_first or provider_sample > provider_first + length:
            return None
        capture = capture_first + provider_sample - provider_first
        if capture == capture_first + length:
            return (capture - 1, capture)
        return (capture, capture + 1)

    def add_accepted(self, provider_first_sample: int, capture_first_sample: int, length_samples: int) -> None:
        if length_samples <= 0:
            return
        if self._spans:
            last = self._spans[-1]
            if last[0] + last[2] == provider_first_sample and last[1] + last[2] == capture_first_sample:
                last[2] += length_samples
                return
        self._spans.append([provider_first_sample, capture_first_sample, length_samples])
        while len(self._spans) > self._max_spans:
            self._spans.pop(0)
            self.evicted_spans += 1

    def add_accepted_spans(self, spans: Sequence[Tuple[int, int]]) -> None:
        """Record consecutive pieces that the provider receives back-to-back."""
        for capture_first_sample, length_samples in spans:
            if not self._spans:
                provider_first = 0
            else:
                last = self._spans[-1]
                provider_first = last[0] + last[2]
            self.add_accepted(provider_first, capture_first_sample, length_samples)

    def _locate(self, provider_sample: int) -> Optional[Tuple[int, int, int]]:
        """The span containing (or within edge tolerance of) a provider sample."""
        tolerance = int(PROVIDER_EDGE_TOLERANCE_SECONDS * self.provider_sample_rate)
        low, high = 0, len(self._spans)
        while low < high:
            mid = (low + high) // 2
            if self._spans[mid][0] <= provider_sample:
                low = mid + 1
            else:
                high = mid
        index = low - 1
        if 0 <= index < len(self._spans):
            provider_first, capture_first, length = self._spans[index]
            if provider_sample <= provider_first + length + tolerance:
                return (provider_first, capture_first, length)
        # Slightly before the first span (provider timing jitter): clamp.
        if index < 0 and self._spans:
            provider_first, capture_first, length = self._spans[0]
            if provider_first - provider_sample <= tolerance:
                return (provider_first, capture_first, length)
        return None

    def map_sample(self, provider_sample: int) -> Optional[int]:
        """Translate one provider sample onto the capture timeline.

        An endpoint inside a span maps linearly into it; one within the edge
        tolerance past a span end clamps onto that end (the provider's own
        tail buffering). ``None`` when the sample is outside every accepted
        span: it belongs to audio we cannot prove was accepted.
        """
        span = self._locate(provider_sample)
        if span is None:
            return None
        provider_from, capture_from, length = span
        return capture_from + min(max(provider_sample - provider_from, 0), length)

    def capture_run_start(self, provider_sample: int) -> Optional[int]:
        """Stable start of the accepted capture run containing this point."""
        span = self._locate(provider_sample)
        return span[1] if span is not None else None

    def map_interval(self, provider_first_sample: int, provider_last_sample: int) -> Optional[Tuple[int, int]]:
        """Translate a provider interval to capture samples.

        Each endpoint maps independently through its containing span, so a
        segment is never mapped *through* an unrepresented gap as if it were
        audio. Endpoints outside every accepted span (beyond edge tolerance)
        reject with None rather than landing on another epoch — and so does an
        interval whose two different provider times would clamp onto one
        capture sample: that collapse fabricates a zero-length segment at a
        span edge instead of mapping the speech, so it fails closed too.
        """
        if provider_last_sample < provider_first_sample:
            provider_first_sample, provider_last_sample = provider_last_sample, provider_first_sample
        start_capture = self.map_sample(provider_first_sample)
        if start_capture is None:
            return None
        end_capture = self.map_sample(provider_last_sample)
        if end_capture is None:
            return None
        # Provider time is continuous across VAD-skipped capture audio. The
        # endpoints alone can therefore enclose a capture gap which was never
        # sent. Keep the whole text unplaced instead of inventing that window.
        previous: Optional[List[int]] = None
        for span in self._spans:
            provider_from, _, length = span
            if provider_from >= provider_last_sample:
                break
            if provider_from + length < provider_first_sample:
                continue
            if previous is not None and previous[1] + previous[2] != span[1]:
                return None
            previous = span
        if provider_last_sample > provider_first_sample and end_capture <= start_capture:
            return None
        return (start_capture, end_capture)

    def minimal_tail_interval(self, provider_first_sample: int, provider_last_sample: int) -> Optional[Tuple[int, int]]:
        """A minimal (one-sample) window for an intentional provider tail.

        A final that begins exactly at a span's end sample and ends inside the
        edge tolerance is the provider's own tail accounting for audio it
        buffered past our count (Modulate's ``done`` flush shape), not drift:
        under clamping both of its endpoints land on the span end, so
        ``map_interval`` fails closed — but the interval is real speech whose
        text may have no other copy. Keep it as a one-sample window on the
        span's last accepted sample. An interval whose start is strictly past
        the span end (arbitrary drift, the many-texts-one-float poison shape)
        still maps to None.
        """
        span = self._locate(provider_first_sample)
        if span is None:
            return None
        provider_from, capture_from, length = span
        if provider_first_sample != provider_from + length:
            return None
        if self.map_sample(provider_last_sample) != capture_from + length:
            return None
        tolerance = int(PROVIDER_EDGE_TOLERANCE_SECONDS * self.provider_sample_rate)
        if provider_last_sample > provider_from + length + tolerance:
            return None
        span_end = capture_from + length
        if span_end <= capture_from:
            return None
        return (span_end - 1, span_end)


class ProviderEpochTranslator:
    """One provider connection's mapping onto the capture timeline.

    Created fresh for every selected socket (initial, fallback and send-path
    failover). Legacy and managed callbacks wrap their segment emission with
    the same translator; timestamps are converted here, before persistence,
    so stored and emitted times are identical.

    ``project_times=False`` is the clock-only mode used for sessions whose
    persistence stays legacy (AUDIO_TIMELINE_V2 off, resumed-v1, custom/multi
    channel excluded earlier): provider-native segment times pass through
    untouched and only the private capture interval is attached, so live
    speaker ID can locate the audio on the capture clock without changing any
    persisted or wire-visible field.
    """

    def __init__(
        self,
        timeline: CaptureTimeline,
        provider_sample_rate: int,
        *,
        on_reject: Optional[Callable[[str], None]] = None,
        on_mapped: Optional[Callable[[], None]] = None,
        on_recover: Optional[Callable[[str], None]] = None,
        on_past_send: Optional[Callable[[Optional[float]], None]] = None,
        owner_at_send: Optional[Callable[[int, int], Optional[str]]] = None,
        project_times: bool = True,
    ):
        self.timeline = timeline
        self.provider_sample_rate = provider_sample_rate
        self.send_map = SendMap(provider_sample_rate)
        self.rejected_segments = 0
        self._on_reject = on_reject
        self._on_mapped = on_mapped
        self._on_recover = on_recover
        self._on_past_send = on_past_send
        self._owner_at_send = owner_at_send
        self._project_times = project_times
        self.provider_label = 'unknown'
        self.send_path = 'unknown'
        self._send_owners: List[Tuple[int, int, Optional[str]]] = []
        self._only_send_owner: Optional[str] = None
        self._send_owner_ambiguous = False

    def note_accepted(self, capture_start_sample: int, length_samples: int) -> None:
        """Record one accepted send of contiguous capture audio."""
        self.note_accepted_spans([(capture_start_sample, length_samples)])

    @property
    def project_times(self) -> bool:
        """Whether translate() rewrites start/end onto the capture wall axis."""
        return self._project_times

    def note_accepted_spans(self, spans: Sequence[Tuple[int, int]]) -> None:
        for capture_start, length in spans:
            if length <= 0:
                continue
            start = self.send_map.last_provider_sample or 0
            self.send_map.add_accepted_spans([(capture_start, length)])
            end = self.send_map.last_provider_sample or start
            owner = self._owner_at_send(capture_start, length) if self._owner_at_send is not None else None
            if self._only_send_owner is None and not self._send_owner_ambiguous:
                self._only_send_owner = owner
            if owner is None or owner != self._only_send_owner:
                self._send_owner_ambiguous = True
            if self._send_owners and self._send_owners[-1][1] == start and self._send_owners[-1][2] == owner:
                first, _, _ = self._send_owners[-1]
                self._send_owners[-1] = (first, end, owner)
            else:
                self._send_owners.append((start, end, owner))
            # Keep owner history bounded even if a session switches recording
            # generations pathologically often. Evicted ownership is unknown.
            if len(self._send_owners) > MAX_SEND_SPANS:
                self._send_owners.pop(0)

    def owner_for_provider_sample(self, sample: int) -> Optional[str]:
        for first, end, owner in reversed(self._send_owners):
            if first <= sample < end:
                return owner
        # A final beyond recorded sends can be attributed only when this
        # provider epoch sent audio for one and only one proven owner.
        return None if self._send_owner_ambiguous else self._only_send_owner

    def translate(self, segments: List[Dict]) -> List[Dict]:
        """Map provider-relative segment times onto absolute wall seconds.

        Each input segment is copied before any field is touched and the
        copies are returned: the adapter owns its dicts, and downstream
        mutation (gate remap, offset rebase, enqueue key pops) must never
        rewrite a provider-time field the adapter might still read after the
        callback returns — comparing such a boundary against another clock
        was the dev 2026-09-26 collapse.

        Segments whose provider timestamps cannot be proven to fall inside
        accepted send spans keep their text at a zero-duration capture anchor,
        marked unplaced, never clamped onto a neighboring epoch. The same
        applies to reversed intervals and intervals whose two different
        provider times would collapse onto one capture sample. Two bounded
        recoveries retain a provable audio position: an interval that begins
        exactly at a span end and ends inside the edge tolerance (the
        provider's own tail accounting) keeps a minimal one-sample window,
        and zero-length points inside a send span use one real sample.
        With ``project_times`` off, persistence
        must stay byte-identical to the legacy behavior: zero-length and
        out-of-range segments keep provider-native times with no capture
        interval; non-numeric and non-finite segments follow the existing
        drop policy.
        """
        translated: List[Dict] = []
        for original in segments:
            segment = dict(original)
            try:
                start, end = float(cast(Any, segment.get('start'))), float(cast(Any, segment.get('end')))
            except (TypeError, ValueError):
                self._reject(segment, 'non_numeric')
                if self._project_times:
                    self._append_unplaced(translated, segment)
                continue
            if not (math.isfinite(start) and math.isfinite(end)):
                self._reject(segment, 'non_finite')
                if self._project_times:
                    self._append_unplaced(translated, segment)
                continue
            rate = self.provider_sample_rate
            first_sample, last_sample = int(start * rate), int(end * rate)
            if self._project_times:
                segment['_provider_send_owner'] = self.owner_for_provider_sample(first_sample)
            interval: Optional[Tuple[int, int]] = None
            if last_sample <= first_sample:
                if self._project_times and last_sample == first_sample:
                    interval = self.send_map.point_interval(first_sample)
                if interval is None:
                    self._reject(segment, 'zero_length')
                    if self._project_times:
                        self._append_unplaced(translated, segment)
                    else:
                        translated.append(segment)
                    continue
                if self._on_recover is not None:
                    try:
                        self._on_recover('zero_length')
                    except Exception:
                        pass
            else:
                interval = self.send_map.map_interval(first_sample, last_sample)
            if interval is None:
                if self.send_map.map_sample(first_sample) is None or self.send_map.map_sample(last_sample) is None:
                    reason = 'outside_accepted_sends'
                else:
                    interval = self.send_map.minimal_tail_interval(first_sample, last_sample)
                    reason = (
                        'discontinuous_interval'
                        if interval is None
                        and self.send_map.map_sample(last_sample) != self.send_map.map_sample(first_sample)
                        else 'collapsed_interval'
                    )
                if interval is None:
                    self._reject(segment, reason)
                    if reason == 'outside_accepted_sends' and self._on_past_send is not None:
                        end = self.send_map.last_provider_sample
                        try:
                            self._on_past_send(None if end is None else (last_sample - end) / rate)
                        except Exception:
                            pass
                    if self._project_times:
                        self._append_unplaced(translated, segment)
                    else:
                        translated.append(segment)
                    continue
            if self._project_times:
                start_wall = self.timeline.wall_strict(interval[0])
                end_wall = self.timeline.wall_strict(interval[1])
                if start_wall is None or end_wall is None:
                    # The anchors describing this sample range were compacted
                    # away; projecting would invent a position. Fail closed.
                    self._reject(segment, 'evicted_interval')
                    self._append_unplaced(translated, segment)
                    continue
                segment['start'] = start_wall
                segment['end'] = max(segment['start'], end_wall)
            # Private capture interval for owner resolution; the receiver pops
            # these keys before the segment enters any buffer.
            segment['_capture_start_sample'] = interval[0]
            segment['_capture_end_sample'] = interval[1]
            if self._project_times:
                segment['audio_capture_run'] = self.send_map.capture_run_start(first_sample)
            translated.append(segment)
            if self._on_mapped is not None:
                try:
                    self._on_mapped()
                except Exception:
                    pass
        return translated

    def _append_unplaced(self, translated: List[Dict], segment: Dict) -> None:
        """Retain text without claiming audio coverage or a speaker window."""
        epoch_end = self.send_map.last_capture_sample
        anchor_sample = epoch_end if epoch_end is not None else self.timeline.next_sample
        anchor = self.timeline.wall_strict(anchor_sample) if self.timeline.anchors else 0.0
        if anchor is None:
            anchor = self.timeline.wall(self.timeline.next_sample)
        segment['start'] = anchor
        segment['end'] = anchor
        segment['_capture_unplaced'] = True
        segment['_provider_send_owner'] = segment.get('_provider_send_owner')
        segment['audio_alignment'] = 'unplaced'
        translated.append(segment)

    def _reject(self, segment: Dict, reason: str) -> None:
        self.rejected_segments += 1
        if self._on_reject is not None:
            try:
                self._on_reject(reason)
            except Exception:
                pass


# Private aliases used by utils.other.storage (kept importable for tests).
