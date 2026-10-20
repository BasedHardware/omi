"""Delayed finals through actual accepted send -> receiver -> transcript -> transaction.

The transport accepts synthetic PCM only; persistence uses StrictFirestore.
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from routers.listen.receiver import _RecordingSTTSocket
from routers.listen.stt_callbacks import build_stt_callbacks
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_audio_timeline_round3 import _receiver, _processor, _seed_row, _async_noop, RATE, T0, UID
from database import conversations as db

FLAG = 'LIVE_CAPTURE_WINDOW_RETENTION'


async def drain(monkeypatch, receiver):
    store = StrictFirestore()
    _seed_row(store, 'c', started_at=datetime.fromtimestamp(T0, tz=timezone.utc))
    processor, _ = _processor(monkeypatch, store, current='c')
    processor.host.use_custom_stt = receiver.host.use_custom_stt
    processor.host.is_multi_channel = receiver.host.is_multi_channel
    processor.host.state.active = False
    processor.host.wait = lambda seconds: asyncio.sleep(0, result=False)
    processor.host.speakers.tasks = []
    processor.host.speakers.drain = _async_noop
    processor.flush_speaker_assignments = _async_noop
    processor._deliver_live_updates = _async_noop
    processor._speaker_detection = _async_noop
    processor.segment_buffer.extend(receiver.collected)
    await asyncio.wait_for(processor.process_loop(), 3)
    row = store.rows[('users', UID, 'conversations', 'c')]
    return db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], row.get('transcript_segments_compressed', False)
    )


def setup(monkeypatch, enabled, provider):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    monkeypatch.setenv('LIVE_SPEAKER_CAPTURE_CLOCK', 'true')
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', 'false')
    receiver = _receiver(monkeypatch, v2=False, conversation='c')
    receiver.host.stt_service = SimpleNamespace(value=provider)
    _, callback, epoch = build_stt_callbacks(receiver)
    transport = SimpleNamespace(send=lambda data, **kwargs: True)
    sender = _RecordingSTTSocket(transport, epoch)
    return receiver, callback, epoch, sender


@pytest.mark.parametrize('provider', ['deepgram', 'soniox', 'modulate'])
@pytest.mark.parametrize('enabled', [False, True])
async def test_late_final_survives_more_than_64_observed_hiatuses(monkeypatch, enabled, provider):
    receiver, callback, epoch, sender = setup(monkeypatch, enabled, provider)
    pcm = b'\0\0' * RATE
    for index in range(70):
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + index * 4 + 1, index * 4 + 1)
        assert sender.send(pcm, start_sample=start)
    # A reconnect/failover gets a new map. Its creation must not rebind the old final.
    build_stt_callbacks(receiver)
    callback([dict(id='late', text='Delayed final.', start=0.1, end=0.9, speaker='SPEAKER_00', is_user=False)])
    (stored,) = await drain(monkeypatch, receiver)
    if enabled:
        assert stored.get('audio_capture_start') == pytest.approx(T0 + 0.1)
        assert stored.get('audio_capture_end') == pytest.approx(T0 + 0.9)
    else:
        assert 'audio_capture_start' not in stored
    assert len(receiver.capture_timeline.anchors) <= (512 if enabled else 64)


@pytest.mark.parametrize('enabled', [False, True])
async def test_late_final_survives_4096_vad_send_spans(monkeypatch, enabled):
    receiver, callback, epoch, sender = setup(monkeypatch, enabled, 'modulate')
    # Tiny frames reproduce retention pressure without allocating hours of PCM.
    observed = b'\0\0' * 40
    accepted = observed[:40]
    for index in range(4100):
        start, _, _ = receiver.capture_timeline.accept(observed, T0 + (index + 1) * 40 / RATE, (index + 1) * 40 / RATE)
        assert sender.send(accepted, start_sample=start)
    callback([dict(id='late', text='Early final.', start=0, end=20 / RATE, speaker='SPEAKER_00', is_user=False)])
    (stored,) = await drain(monkeypatch, receiver)
    if enabled:
        assert stored.get('audio_capture_start') == pytest.approx(T0)
        assert stored.get('audio_capture_end') == pytest.approx(T0 + 20 / RATE)
    else:
        assert 'audio_capture_start' not in stored
    assert epoch.send_map.span_count <= (16384 if enabled else 4096)
    # Retention must not fill the omitted half-frame between two accepted sends.
    callback(
        [dict(id='gap', text='Across a gap.', start=10 / RATE, end=30 / RATE, speaker='SPEAKER_00', is_user=False)]
    )
    assert '_capture_abs_start' not in receiver.collected[-1]


@pytest.mark.parametrize('enabled', [False, True])
async def test_retention_never_turns_failed_send_into_capture_proof(monkeypatch, enabled):
    receiver, callback, epoch, _ = setup(monkeypatch, enabled, 'modulate')
    failed = _RecordingSTTSocket(SimpleNamespace(send=lambda data, **kwargs: False), epoch)
    pcm = b'\0\0' * RATE
    start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 1, 1)
    assert failed.send(pcm, start_sample=start) is False
    assert epoch.send_map.span_count == 0
    callback([dict(id='failed', text='Unaccepted audio.', start=0.1, end=0.9, speaker='SPEAKER_00', is_user=False)])
    (stored,) = await drain(monkeypatch, receiver)
    assert 'audio_capture_start' not in stored and 'audio_capture_end' not in stored


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('loss', ['gap', 'unknown_side', 'partial_backward', 'partial_forward'])
async def test_preserve_provider_pieces_instead_of_discarding_known_windows(monkeypatch, enabled, loss):
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION', 'true' if enabled else 'false')
    receiver, callback, epoch, sender = setup(monkeypatch, False, 'modulate')
    pcm = b'\0\0' * (4 * RATE)
    first, _, _ = receiver.capture_timeline.accept(pcm, T0 + 4, 4)
    assert sender.send(pcm, start_sample=first)
    first, _, _ = receiver.capture_timeline.accept(pcm, T0 + (12 if loss == 'gap' else 8), 12 if loss == 'gap' else 8)
    assert sender.send(pcm, start_sample=first)
    a = dict(id='a', text='hello', start=0.1, end=3.9, speaker='SPEAKER_00', is_user=False)
    b = dict(id='b', text='again', start=4.1, end=7.9, speaker='SPEAKER_00', is_user=False)
    if loss == 'unknown_side':
        a.update(start=0, end=0)
    elif loss == 'partial_backward':
        a['text'] = 'A long unfinished phrase'
        b.update(text='yes. Another sentence.', speaker='SPEAKER_01')
    elif loss == 'partial_forward':
        a['text'] = 'Done. hi'
        b.update(text='a much longer continuation.', speaker='SPEAKER_01')
    callback([a, b])
    stored = await drain(monkeypatch, receiver)
    if enabled:
        assert [s['text'] for s in stored] == [a['text'], b['text']]
        assert [s['id'] for s in stored] == ['a', 'b']
        assert sum('audio_capture_start' in s for s in stored) == (1 if loss == 'unknown_side' else 2)
        assert stored[-1]['audio_capture_start'] == pytest.approx(T0 + (8.1 if loss == 'gap' else 4.1))
        assert stored[-1]['audio_capture_end'] == pytest.approx(T0 + (11.9 if loss == 'gap' else 7.9))
    else:
        assert all('audio_capture_start' not in s for s in stored)


@pytest.mark.parametrize('enabled,frames', [(False, 2), (True, 70)])
@pytest.mark.parametrize('strict', [False, True])
@pytest.mark.parametrize('start,end', [(0.9, 1.1), (0.9, 1.0), (1.0, 1.1)])
async def test_half_open_hiatus_window_receiver_persistence(monkeypatch, enabled, frames, strict, start, end):
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_STRICT_PROJECTION', 'true' if strict else 'false')
    receiver, callback, epoch, sender = setup(monkeypatch, enabled, 'modulate')
    pcm = b'\0\0' * RATE
    for index in range(frames):
        first, _, _ = receiver.capture_timeline.accept(pcm, T0 + index * 4 + 1, index * 4 + 1)
        assert sender.send(pcm, start_sample=first)
    callback([dict(id='boundary', text='Observed audio.', start=start, end=end, speaker='SPEAKER_00', is_user=False)])
    (stored,) = await drain(monkeypatch, receiver)
    if strict and start < 1 < end:
        assert 'audio_capture_start' not in stored and 'audio_capture_end' not in stored
    else:
        expected_start = T0 + (start if start < 1 else start + 3)
        expected_end = T0 + (end if end < 1 or (strict and end == 1) else end + 3)
        assert stored['audio_capture_start'] == pytest.approx(expected_start, rel=0, abs=1e-6)
        assert stored['audio_capture_end'] == pytest.approx(expected_end, rel=0, abs=1e-6)


@pytest.mark.parametrize('enabled,frames', [(False, 2), (True, 70)])
@pytest.mark.parametrize('start,end', [(0.9, 1.1), (0.9, 1.0), (1.0, 1.1)])
async def test_v2_receiver_half_open_projection_even_legacy_switch_off(monkeypatch, enabled, frames, start, end):
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_STRICT_PROJECTION', 'false')
    receiver, _, _, _ = setup(monkeypatch, enabled, 'modulate')
    receiver.capture_timeline_v2 = True  # Synthetic admitted row; deployment flag stays OFF.
    _, callback, epoch = build_stt_callbacks(receiver)
    sender = _RecordingSTTSocket(SimpleNamespace(send=lambda *a, **kw: True), epoch)
    pcm = b'\0\0' * RATE
    for index in range(frames):
        first, last, _ = receiver.capture_timeline.accept(pcm, T0 + index * 4 + 1, index * 4 + 1)
        receiver._note_accepted_frame(first, last)
        assert sender.send(pcm, start_sample=first)
    callback([dict(id='v2', text='Observed audio.', start=start, end=end, speaker='SPEAKER_00', is_user=False)])
    (raw,) = receiver.collected
    if start < 1 < end:
        assert raw['audio_alignment'] == 'unplaced'
        assert 'audio_capture_run' not in raw
    else:
        assert raw.get('audio_alignment') != 'unplaced'
        assert raw['start'] == pytest.approx(T0 + (start if start < 1 else start + 3), rel=0, abs=1e-6)
        assert raw['end'] == pytest.approx(T0 + (end if end <= 1 else end + 3), rel=0, abs=1e-6)
