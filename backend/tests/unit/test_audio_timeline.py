"""Unit coverage for the pure audio-timeline v2 primitives.

These tests prove the two properties the v2 design depends on:

1. one capture coordinate: the integer sample cursor positions accepted decoded
   PCM exactly, anchors only at the first frame and at measured inter-arrival
   hiatuses, and ``started_at + segment.start`` points at *the correct stored
   samples* (identified by content, not merely by the existence of a chunk);
2. fail-closed mapping: provider timestamps translate only through spans the
   provider actually accepted, and coverage never guesses.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from models.audio_file import AudioFile, ChunkSpan
from utils.audio_timeline import (
    ANCHOR_GAP_SECONDS,
    CaptureTimeline,
    ProviderEpochTranslator,
    SendMap,
    covered_window,
    coverage_outcome,
    is_audio_timeline_v2,
    segment_wall_window,
)

RATE = 16000


def _silence(samples: int) -> bytes:
    return b'\x00\x00' * samples


def _pcm(samples: int, fill: int = 0) -> bytes:
    return bytes([fill & 0xFF, (fill >> 8) & 0xFF]) * samples


def _phrase_pcm(marker: int, samples: int) -> bytes:
    """Identifiable PCM: every sample encodes (marker, sample index)."""
    out = bytearray()
    for i in range(samples):
        value = (marker * 2048 + i) & 0x7FFF
        out += value.to_bytes(2, 'little')
    return bytes(out)


class TestCaptureTimelineExactPosition:
    def test_mono_16k_exact_position(self):
        timeline = CaptureTimeline(sample_rate=RATE)
        start, end, new_anchor = timeline.accept(_pcm(1600), arrival_wall=1000.0, arrival_monotonic=5.0)
        assert (start, end, new_anchor) == (0, 1600, True)
        assert math.isclose(timeline.wall(0), 999.9, abs_tol=1e-9)
        assert math.isclose(timeline.wall(1600), 1000.0, abs_tol=1e-9)

        start2, end2, anchored2 = timeline.accept(_pcm(1600), arrival_wall=1000.2, arrival_monotonic=5.2)
        assert (start2, end2, anchored2) == (1600, 3200, False)
        # No anchor: contiguous frames project linearly from the first anchor.
        assert math.isclose(timeline.wall(1600), 999.9 + 0.1, abs_tol=1e-9)

    def test_empty_and_odd_frames_do_not_advance(self):
        timeline = CaptureTimeline(sample_rate=RATE)
        timeline.accept(_pcm(100), arrival_wall=10.0, arrival_monotonic=1.0)
        start, end, anchored = timeline.accept(b'', arrival_wall=10.1, arrival_monotonic=1.1)
        assert (start, end, anchored) == (100, 100, False)
        assert timeline.next_sample == 100

    def test_arrival_hiatus_anchors_but_ongoing_silence_does_not(self):
        timeline = CaptureTimeline(sample_rate=RATE)
        # 10 s of delivered PCM silence in 100 ms frames: contiguous arrivals.
        silence = _silence(RATE * 10)
        wall = 2000.0
        for offset in range(0, len(silence), 3200):
            piece = silence[offset : offset + 3200]
            timeline.accept(piece, wall + 0.1, wall + 0.1)
            wall += 0.1
        assert len(timeline.anchors) == 1
        assert timeline.next_sample == RATE * 10

        # A measured 3 s inter-arrival hiatus creates a second anchor at the
        # resumed frame's estimated first-sample wall.
        before_end_wall = timeline.wall(timeline.next_sample)
        start, end, anchored = timeline.accept(_pcm(3200), arrival_wall=wall + 3.0 + 0.2, arrival_monotonic=wall + 3.2)
        assert anchored is True
        assert math.isclose(timeline.wall(start), before_end_wall + 3.0, abs_tol=1e-6)
        # The silent PCM still advanced samples; the hiatus did not consume them.
        assert start == RATE * 10

    def test_burst_of_buffered_frames_never_anchors(self):
        """A client bursting buffered audio arrives faster than real time.

        Inter-arrival gaps are negative, so no anchor is set even though the
        wall estimate runs backwards; positions stay exact.
        """
        timeline = CaptureTimeline(sample_rate=RATE)
        timeline.accept(_pcm(3200), arrival_wall=3000.0, arrival_monotonic=10.0)
        burst_wall = 3000.05
        for _ in range(50):
            _, _, anchored = timeline.accept(_pcm(3200), arrival_wall=burst_wall, arrival_monotonic=10.05)
            assert anchored is False
            burst_wall += 0.001
        assert len(timeline.anchors) == 1
        assert timeline.next_sample == 3200 * 51

    def test_wall_clock_jump_backward_is_not_new_audio(self):
        timeline = CaptureTimeline(sample_rate=RATE)
        timeline.accept(_pcm(3200), arrival_wall=5000.0, arrival_monotonic=42.0)
        # NTP steps the wall clock back an hour; monotonic keeps flowing.
        timeline.accept(_pcm(3200), arrival_wall=5000.1 - 3600.0, arrival_monotonic=42.1)
        assert len(timeline.anchors) == 1
        assert timeline.wall_backward_events == 1
        # Projection stays on the pre-jump axis.
        assert math.isclose(timeline.wall(6400), 4999.8 + 0.4, abs_tol=1e-6)

    def test_monotonic_guard_blocks_false_hiatus_from_wall_jump(self):
        timeline = CaptureTimeline(sample_rate=RATE)
        timeline.accept(_pcm(3200), arrival_wall=100.0, arrival_monotonic=0.0)
        # Wall estimate jumps 10 s ahead but monotonic says 0.1 s elapsed: the
        # wall clock moved, the client did not stop recording.
        _, _, anchored = timeline.accept(_pcm(3200), arrival_wall=110.1, arrival_monotonic=0.1)
        assert anchored is False


class TestSendMap:
    def test_map_interval_through_preroll_and_skipped_silence(self):
        """Pre-roll is sent at speech onset; skipped silence never maps."""
        sm = SendMap(RATE)
        # Pre-roll 300 ms + 100 ms chunk sent together at provider t=0.
        sm.add_accepted_spans([(0, 300 * RATE // 1000), (300 * RATE // 1000, 100 * RATE // 1000)])
        # 5 s of silence skipped; then 1 s of speech at provider t=0.4.
        sm.add_accepted_spans([(400 * RATE // 1000 + 5 * RATE, RATE)])
        # A provider segment inside the first (pre-roll + speech) burst.
        first = sm.map_interval(int(0.05 * RATE), int(0.35 * RATE))
        assert first == (int(0.05 * RATE), int(0.35 * RATE))
        # A segment after the skip maps through the later span only: the burst
        # sits at provider time [0.4s, 1.4s] but capture time [5.4s, 6.4s].
        second = sm.map_interval(int(0.5 * RATE), int(0.9 * RATE))
        assert second == (int(5.5 * RATE), int(5.9 * RATE))
        # Silence-time (inside the skip) is outside accepted sends.
        assert sm.map_interval(int(1.0 * RATE), int(2.0 * RATE)) is None

    def test_failed_send_is_not_recorded_and_replay_starts_new_epoch(self):
        timeline = CaptureTimeline(sample_rate=RATE)
        timeline.accept(_pcm(3200), arrival_wall=10.0, arrival_monotonic=1.0)
        first = ProviderEpochTranslator(timeline, RATE)
        first.note_accepted(0, 1600)
        # The send that followed failed: provider time did not advance.
        # A new connection (new epoch) restarts provider time at zero and
        # maps onto the same capture timeline.
        second = ProviderEpochTranslator(timeline, RATE)
        second.note_accepted(1600, 1600)
        seg = {'start': 0.05, 'end': 0.09, 'text': 'x'}
        translated = second.translate([dict(seg)])
        assert translated and translated[0]['start'] == timeline.wall(1600 + int(0.05 * RATE))

    def test_provider_time_out_of_range_rejects(self):
        translator = ProviderEpochTranslator(CaptureTimeline(RATE), RATE)
        translated = translator.translate([{'start': 10.0, 'end': 11.0, 'text': 'late'}])
        assert translated == []
        assert translator.rejected_segments == 1

    def test_clock_only_mode_keeps_provider_times_and_unmapped_segments(self):
        """project_times=False (flag-off sessions): persistence stays legacy.

        A mapped segment keeps its provider-native start/end untouched and
        gains only the private capture interval; a segment whose provider
        time falls outside accepted sends is still delivered (origin/main
        persisted it too) but carries no capture interval, so only its
        speaker-ID window falls back.
        """
        timeline = CaptureTimeline(sample_rate=RATE)
        timeline.accept(_pcm(RATE), arrival_wall=100.0, arrival_monotonic=0.0)
        translator = ProviderEpochTranslator(timeline, RATE, project_times=False)
        translator.note_accepted(0, RATE)
        mapped, unmapped = {'start': 0.25, 'end': 0.75, 'text': 'a'}, {'start': 9.0, 'end': 9.5, 'text': 'b'}
        translated = translator.translate([dict(mapped), dict(unmapped)])
        assert [segment['text'] for segment in translated] == ['a', 'b']
        assert translated[0]['start'] == 0.25 and translated[0]['end'] == 0.75
        assert translated[0]['_capture_start_sample'] == int(0.25 * RATE)
        assert translated[0]['_capture_end_sample'] == int(0.75 * RATE)
        assert '_capture_start_sample' not in translated[1]
        assert translated[1]['start'] == 9.0
        assert translator.rejected_segments == 1

    def test_edge_tolerance_accepts_provider_tail_overshoot(self):
        sm = SendMap(RATE)
        sm.add_accepted_spans([(0, RATE)])
        # 100 ms beyond the accepted end: within tolerance, clamps to the end.
        assert sm.map_interval(int(0.9 * RATE), int(1.1 * RATE)) == (int(0.9 * RATE), RATE)
        # 2 s beyond: rejected.
        assert sm.map_interval(int(2.5 * RATE), int(2.6 * RATE)) is None

    def test_evicted_spans_fail_closed(self):
        sm = SendMap(RATE, max_spans=2)
        sm.add_accepted_spans([(0, RATE)])
        sm.add_accepted_spans([(10 * RATE, RATE)])
        sm.add_accepted_spans([(20 * RATE, RATE)])
        assert sm.evicted_spans == 1
        # Provider time 0..1s was evicted: mapping it fails closed.
        assert sm.map_interval(0, RATE // 2) is None
        # Provider time continues across the capture skips (1s..2s of sent
        # audio maps to capture 10s..11s).
        assert sm.map_interval(RATE, RATE + RATE // 2) == (10 * RATE, 10 * RATE + RATE // 2)


class TestTwoRolloversWithIdentifiablePhrases:
    """End-to-end pure-module scenario: >30 min rollovers, distinct phrases, provider reset."""

    def test_started_at_plus_segment_start_points_at_the_correct_phrase(self):
        timeline = CaptureTimeline(sample_rate=RATE)
        conversation: Dict[str, Optional[float]] = {'started_at': None}
        stored: List[Tuple[float, float, bytes]] = []  # (abs_start_wall, samples, pcm)

        def store_run(pcm: bytes, first_sample_wall: float) -> None:
            stored.append((first_sample_wall, len(pcm) // 2, pcm))

        wall = 1_700_000_000.0
        mono = 0.0

        def accept(pcm: bytes, arrive_wall: float) -> Tuple[int, int]:
            start, end, _ = timeline.accept(pcm, arrive_wall, mono + (arrive_wall - wall))
            if conversation['started_at'] is None:
                conversation['started_at'] = timeline.wall(start)
            return start, end

        # Conversation 1: 31 minutes containing phrase A at minute 5.
        phrase_a = _phrase_pcm(marker=1, samples=8 * RATE)
        a_first_sample: Optional[int] = None
        elapsed = 0.0
        while elapsed < 31 * 60:
            if 5 * 60 - 0.1 <= elapsed < 5 * 60 - 0.1 + len(phrase_a) / RATE / 2:
                if a_first_sample is None:
                    a_first_sample = timeline.next_sample
                start, _ = accept(phrase_a, wall + elapsed + 0.1)
                store_run(phrase_a, timeline.wall(start))
                elapsed += len(phrase_a) / (RATE * 2)
                continue
            chunk = _pcm(1600)
            accept(chunk, wall + elapsed + 0.1)
            elapsed += 0.1
        conv1_started = conversation['started_at']

        # Rollover 1: new conversation, provider resets (new epoch + translator).
        conversation['started_at'] = None
        translator1 = ProviderEpochTranslator(timeline, RATE)
        phrase_b = _phrase_pcm(marker=2, samples=8 * RATE)
        b_first_sample: Optional[int] = None
        elapsed = 0.0
        while elapsed < 31 * 60:
            if 10 * 60 - 0.1 <= elapsed < 10 * 60 - 0.1 + len(phrase_b) / RATE / 2:
                if b_first_sample is None:
                    b_first_sample = timeline.next_sample
                start, _ = accept(phrase_b, wall + 31 * 60 + elapsed + 0.1)
                store_run(phrase_b, timeline.wall(start))
                elapsed += len(phrase_b) / (RATE * 2)
                continue
            chunk = _pcm(1600)
            start, _ = accept(chunk, wall + 31 * 60 + elapsed + 0.1)
            translator1.note_accepted(start, len(chunk) // 2)
            elapsed += 0.1
        conv2_started = conversation['started_at']
        assert conv2_started > conv1_started

        # Rollover 2 with another provider reset.
        conversation['started_at'] = None
        translator2 = ProviderEpochTranslator(timeline, RATE)
        epoch3_base: List[int] = []
        phrase_c = _phrase_pcm(marker=3, samples=8 * RATE)
        c_first_sample: Optional[int] = None
        elapsed = 0.0
        while elapsed < 60:
            if 20 - 0.1 <= elapsed < 20 - 0.1 + len(phrase_c) / RATE / 2:
                if c_first_sample is None:
                    c_first_sample = timeline.next_sample
                start, _ = accept(phrase_c, wall + 62 * 60 + elapsed + 0.1)
                store_run(phrase_c, timeline.wall(start))
                if not epoch3_base:
                    epoch3_base.append(start)
                translator2.note_accepted(start, len(phrase_c) // 2)
                elapsed += len(phrase_c) / (RATE * 2)
                continue
            chunk = _pcm(1600)
            start, _ = accept(chunk, wall + 62 * 60 + elapsed + 0.1)
            if not epoch3_base:
                epoch3_base.append(start)
            translator2.note_accepted(start, len(chunk) // 2)
            elapsed += 0.1
        conv3_started = conversation['started_at']

        # Provider segments for each phrase (provider time relative to each
        # reset epoch): translate to wall, subtract conversation started_at,
        # and check the offset selects the phrase's own samples.
        def offset_selects_phrase(started: float, segment_offset_start: float, marker: int, samples: int) -> bool:
            abs_start = started + segment_offset_start
            for run_start, run_samples, pcm in stored:
                if math.isclose(run_start, abs_start, abs_tol=0.01):
                    want = _phrase_pcm(marker, min(samples, run_samples))
                    return pcm[: len(want)] == want
            return False

        # Phrase A in conversation 1.
        seg_a = {'start': timeline.wall(a_first_sample or 0) - conv1_started}
        assert offset_selects_phrase(
            conv1_started, seg_a['start'], marker=1, samples=len(phrase_a) // 2
        ), 'started_at + segment.start must point at phrase A samples'
        # Phrase B belongs to conversation 2, not conversation 1.
        seg_b = {'start': timeline.wall(b_first_sample or 0) - conv2_started}
        assert offset_selects_phrase(conv2_started, seg_b['start'], marker=2, samples=len(phrase_b) // 2)
        assert not offset_selects_phrase(conv1_started, seg_b['start'], marker=1, samples=len(phrase_a) // 2)
        # Phrase C in conversation 3 after the second provider reset.
        seg_c = {'start': timeline.wall(c_first_sample or 0) - conv3_started}
        assert offset_selects_phrase(conv3_started, seg_c['start'], marker=3, samples=len(phrase_c) // 2)

        # A translated provider segment from the third epoch lands on phrase C.
        provider_rel_c = ((c_first_sample or 0) - epoch3_base[0]) / RATE  # provider time of phrase C
        translated = translator2.translate([{'start': provider_rel_c, 'end': provider_rel_c + 1.0, 'text': 'c'}])
        assert translated and math.isclose(translated[0]['start'] - conv3_started, seg_c['start'], abs_tol=0.01)


class TestWallWindowAndCoverage:
    def _conversation(self, **extra) -> Dict:
        base = {
            'started_at': datetime.fromtimestamp(1_700_000_000.0, tz=timezone.utc),
            'private_cloud_sync_enabled': True,
            'audio_files': [],
        }
        base.update(extra)
        return base

    def test_segment_wall_window_v2_and_v1_formula(self):
        conv = self._conversation(audio_timeline={'version': 2})
        window = segment_wall_window(conv, 5.0, 12.0)
        assert window == (1_700_000_005.0, 1_700_000_012.0)
        assert segment_wall_window(conv, 12.0, 5.0) is None
        assert segment_wall_window(conv, float('nan'), 1.0) is None
        assert segment_wall_window(conv, 0.0, float('inf')) is None
        assert segment_wall_window(self._conversation(started_at=None), 0.0, 1.0) is None
        # Half-open: a zero-width window at a covered point is still a window.
        assert segment_wall_window(conv, 5.0, 5.0) == (1_700_000_005.0, 1_700_000_005.0)
        # v1 rows keep the same formula without the marker.
        assert segment_wall_window(self._conversation(), 5.0, 12.0) == (1_700_000_005.0, 1_700_000_012.0)

    def test_is_audio_timeline_v2(self):
        assert is_audio_timeline_v2({'audio_timeline': {'version': 2}})
        assert not is_audio_timeline_v2({'audio_timeline': {'version': 1}})
        assert not is_audio_timeline_v2({})

    def test_covered_window_requires_validated_spans(self):
        files = [{'chunk_spans': [{'start': 100.0, 'end': 160.0}, {'start': 160.0, 'end': 220.0}]}]
        assert covered_window(files, 100.0, 220.0)
        assert covered_window(files, 120.0, 200.0)
        # Uncovered window never claims coverage.
        assert not covered_window(files, 90.0, 120.0)
        assert not covered_window(files, 200.0, 260.0)
        assert not covered_window(files, 220.0, 230.0)
        # Legacy timestamp lists never claim coverage.
        assert not covered_window([{'chunk_timestamps': [100.0, 160.0]}], 100.0, 160.0)
        # Malformed spans fail closed.
        assert not covered_window([{'chunk_spans': [{'start': 100.0, 'end': 90.0}]}], 95.0, 99.0)
        assert not covered_window([{'chunk_spans': [{'start': float('nan'), 'end': 10.0}]}], 0.0, 5.0)
        assert not covered_window([{'chunk_spans': [{'start': True, 'end': 10.0}]}], 0.0, 5.0)
        assert not covered_window([{'chunk_spans': [{'start': 1.0}]}], 0.0, 5.0)
        assert not covered_window([], 0.0, 1.0)

    def test_coverage_outcome_enum(self):
        base = 1_700_000_000.0
        v2 = self._conversation(audio_timeline={'version': 2})
        assert coverage_outcome(v2, 0.0, 5.0) == 'pending_upload'
        no_storage = self._conversation(private_cloud_sync_enabled=False)
        assert coverage_outcome(no_storage, 0.0, 5.0) == 'no_audio'
        legacy = self._conversation(audio_files=[{'chunk_timestamps': [base]}])
        assert coverage_outcome(legacy, 0.0, 5.0) == 'unsupported'
        partial = self._conversation(audio_files=[{'chunk_spans': [{'start': base, 'end': base + 2.0}]}])
        assert coverage_outcome(partial, 0.0, 2.0) == 'covered'
        assert coverage_outcome(partial, 0.0, 5.0) == 'missing'

    def test_audio_file_chunk_spans_dump_without_nested_arrays(self):
        # Firestore rejects an array directly inside an array, so persisted
        # chunk_spans must be objects, never [start, end] pairs.
        audio_file = AudioFile(
            id='f',
            uid='u',
            conversation_id='c',
            chunk_timestamps=[100.0],
            duration=60.0,
            chunk_spans=[ChunkSpan(start=100.0, end=160.0)],
        )

        def has_nested_array(value):
            if isinstance(value, list):
                return any(isinstance(item, list) or has_nested_array(item) for item in value)
            if isinstance(value, dict):
                return any(has_nested_array(item) for item in value.values())
            return False

        dumped = audio_file.model_dump()
        assert dumped['chunk_spans'] == [{'start': 100.0, 'end': 160.0}]
        assert not has_nested_array(dumped)
        assert covered_window([dumped], 110.0, 150.0)

    def test_chunk_span_bounds_and_covered_window_accept_pydantic_models(self):
        from database.audio_timeline import chunk_span_bounds

        span = ChunkSpan(start=100.0, end=160.0)
        assert chunk_span_bounds(span) == (100.0, 160.0)

        audio_file = AudioFile(
            id='f',
            uid='u',
            conversation_id='c',
            chunk_timestamps=[100.0],
            duration=60.0,
            chunk_spans=[span],
        )
        assert covered_window([audio_file], 110.0, 150.0)

    def test_anchor_gap_constant_is_jitter_guard(self):
        # The 2 s trigger is only an initial jitter guard, documented as such.
        assert ANCHOR_GAP_SECONDS == 2.0
