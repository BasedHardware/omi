"""Integer capture/send proof must deliver complete PCM to the live matcher."""

import struct

import numpy as np
import pytest

from routers.listen import transcripts
from routers.listen.speaker_audio import select_query_audio
from routers.listen.stt_callbacks import attach_legacy_capture_window
from tests.unit.test_owner_recognition_diagnostics import live, snapshot
from tests.unit.test_owner_recognition_embedding_budget import _clock
from tests.unit.test_speaker_targeted_fairness import serve
from utils.audio import AudioRingBuffer
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator
from utils.observability.speaker_embedding_budget import PCM_WINDOWS_RESTORED


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.parametrize('write_mode', ['positioned', 'arrival'])
@pytest.mark.parametrize('rate', [8000, 16000, 48000])
def test_full_received_spans_keep_all_samples_at_epoch_timestamps(write_mode, rate):
    ring = AudioRingBuffer(60, rate)
    base = 1_791_800_000.0
    frame = struct.pack('<h', 517) * (rate // 50)
    for i in range(100):
        if write_mode == 'positioned':
            ring.write_positioned(frame, base + i / 50)
        else:
            ring.write(frame, base + (i + 1) / 50)
    bounds = ring.get_time_range()
    assert bounds is not None
    pcm = ring.extract(*bounds)
    assert pcm is not None and len(pcm) == len(frame) * 100
    assert pcm == frame * 100
    positions = ring.proven_byte_ranges(*bounds)
    assert sum(end - start for start, end in positions) == len(frame) * 100


@pytest.mark.anyio
async def test_capture_proven_two_two_one_seconds_reaches_owner_comparison_in_real_runner(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = live(monkeypatch, [owner] * 3)
    restored_before = PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')._value.get()
    host.state.audio_ring_buffer = AudioRingBuffer(60, 16000)
    timeline = CaptureTimeline(16000)
    translator = ProviderEpochTranslator(timeline, 16000, project_times=False)
    processor = object.__new__(transcripts.TranscriptProcessor)
    host.speakers = matcher
    processor.host = host
    processor.suggested_segments = set()
    base = 1_791_800_000.0
    frame = struct.pack('<h', 517) * 320
    frame_index = 0
    for start, end in [(0, 2), (2, 4), (4, 5)]:
        while frame_index < end * 50:
            first, last, _ = timeline.accept(frame, base + (frame_index + 1) / 50, (frame_index + 1) / 50)
            host.state.audio_ring_buffer.write_positioned(frame, timeline.wall(first))
            translator.note_accepted(first, last - first)
            frame_index += 1
        raw = translator.translate([dict(id=f'piece-{start}', start=start, end=end, speaker_id=1)])[0]
        attach_legacy_capture_window(raw, timeline)
        assert not raw.get('_capture_window_unavailable')
        window = (raw.pop('_capture_abs_start'), raw.pop('_capture_abs_end'))
        processor._queue_raw_detections([raw], {raw['id']: window}, base)
        await serve(matcher, host, monkeypatch, 1)
    assert matcher._embedding_attempts[1] == 3
    assert matcher.speaker_to_person[1] == ('user', 'User')
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 5
    assert PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')._value.get() == restored_before + 3


@pytest.mark.parametrize('rate', [8000, 16000, 48000])
def test_interior_end_keeps_sample_floor_without_endpoint_rounding(rate):
    ring = AudioRingBuffer(60, rate)
    base = 1_791_800_000.0
    frame = struct.pack('<h', 517) * (rate // 50)
    ring.write_positioned(frame, base)
    end = base + 0.01
    pcm = ring.extract(base, end)
    assert pcm is not None
    assert len(pcm) == int((end - base) * ring.bytes_per_second) // 2 * 2
    assert pcm == frame[: len(pcm)]
    assert getattr(pcm, 'restored_samples', 0) == 0


@pytest.mark.parametrize('rate', [8000, 16000, 48000])
def test_full_span_correction_keeps_wrap_and_eviction_fences(rate):
    ring = AudioRingBuffer(2, rate)
    base = 1_791_800_000.0
    frames = []
    for i in range(250):
        frame = struct.pack('<h', i) * (rate // 50)
        frames.append(frame)
        ring.write_positioned(frame, base + i / 50)
    bounds = ring.get_time_range()
    assert bounds is not None
    pcm = ring.extract(*bounds)
    assert pcm is not None and len(pcm) == rate * 2 * 2
    assert pcm == b''.join(frames[-100:])
    assert ring.extract(base, base + 2) is None
    assert ring.proven_byte_ranges(base, base + 2) == []
    ranges = ring.proven_byte_ranges(*bounds)
    assert sum(end - start for start, end in ranges) == len(pcm)
    assert min(start for start, _ in ranges) == ring.total_bytes_written - ring.capacity


@pytest.mark.anyio
async def test_real_runner_never_pads_gaps_into_a_qualified_query(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = live(monkeypatch, [owner])
    host.state.audio_ring_buffer = AudioRingBuffer(60, 16000)
    base = 1_791_800_000.0
    half = struct.pack('<h', 517) * 8000
    host.state.audio_ring_buffer.write_positioned(half, base)
    host.state.audio_ring_buffer.write_positioned(half, base + 1.5)
    restored_before = PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')._value.get()
    matcher.queue.put_nowait(
        dict(id='physically-one-second', speaker_id=1, abs_start=base, abs_end=base + 2, duration=2)
    )
    tokens = matcher._socket_embedding_tokens
    await serve(matcher, host, monkeypatch, 1)
    assert matcher._embedding_attempts[1] == 0
    assert matcher._socket_embedding_tokens >= tokens  # refill only
    assert not matcher.speaker_evidence and not matcher.speaker_to_person
    assert PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')._value.get() == restored_before


def test_restoration_counter_has_one_closed_reason_and_no_ids():
    samples = [s for family in PCM_WINDOWS_RESTORED.collect() for s in family.samples if s.name.endswith('_total')]
    assert len(samples) == 1
    assert samples[0].labels == {'reason': 'full_span_rounding'}


@pytest.mark.anyio
@pytest.mark.parametrize('cap', ['voice', 'socket'])
async def test_corrected_candidate_cannot_bypass_existing_budget(monkeypatch, cap):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [])  # extraction would fail if erroneously admitted
    ring = host.state.audio_ring_buffer = AudioRingBuffer(60, 16000)
    base = 1_791_800_000.0
    frame = struct.pack('<h', 517) * 320
    for i in range(100):
        ring.write_positioned(frame, base + i / 50)
    matcher._admit_voice(1)
    matcher._embedding_attempts[1] = 12 if cap == 'voice' else 0
    matcher._socket_embedding_tokens = 16 if cap == 'voice' else 0
    attempts, tokens = matcher._embedding_attempts[1], matcher._socket_embedding_tokens
    before = PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')._value.get()
    matcher.queue.put_nowait(
        dict(id='qualified-but-capped', speaker_id=1, abs_start=base, abs_end=base + 2, duration=2)
    )
    await serve(matcher, host, monkeypatch, 1)
    assert matcher._embedding_attempts[1] == attempts
    assert matcher._socket_embedding_tokens == tokens
    assert not matcher.speaker_evidence and not matcher.speaker_to_person
    assert snapshot(matcher)['reasons']['embedding_budget'] == 1
    assert PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')._value.get() == before + 1


@pytest.mark.parametrize('new_seconds', [0.5, 2])
def test_newer_pool_restoration_counts_only_at_actual_caller_floor(new_seconds):
    ring = AudioRingBuffer(60, 16000)
    base = 1_791_800_000.0
    old = struct.pack('<h', 41) * (6 * 16000)
    ring.write_positioned(old, base)
    frame = struct.pack('<h', 517) * 320
    for i in range(round(new_seconds * 50)):
        ring.write_positioned(frame, base + 8 + i / 50)
    before = PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')._value.get()
    pcm, selected = select_query_audio(
        ring,
        [(base, base + 6), (base + 8, base + 8 + new_seconds)],
        prefer_recent=True,
        sample_rate=16000,
        capture_watermark=base + 6,
        minimum_seconds=2,
    )
    assert len(pcm) >= 2 * 16000 * 2
    if new_seconds == 2:
        assert selected == [(base + 8, base + 10)]
        assert pcm == frame * 100
    else:
        assert (base, base + 6) in selected
    assert PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')._value.get() == before + (new_seconds == 2)
