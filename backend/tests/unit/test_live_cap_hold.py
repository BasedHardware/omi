"""Live custody uses decoded, unique, denied capture and the existing hold writer."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import wave

import pytest

from utils.sync import live_cap_hold as live
from utils.sync import cap_hold, held_audio_summary, cap_hold_recovery
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def write_wav(path, data, rate):
    with wave.open(path, 'wb') as audio:
        audio.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        audio.writeframes(data)


@pytest.fixture
def host():
    return SimpleNamespace(
        request=SimpleNamespace(uid='synthetic', source='phone', websocket=SimpleNamespace(send_json=AsyncMock())),
        state=SimpleNamespace(current_conversation_id='conversation', conversation_sample_ranges=[]),
        client_device_context=SimpleNamespace(client_device_id='device'),
        session_id='socket-1',
    )


@pytest.fixture
def persistence(monkeypatch, tmp_path):
    persisted = []
    monkeypatch.setattr(live, 'fragments_enabled', lambda: False)
    monkeypatch.setattr(held_audio_summary, 'next_utc_month_start', lambda: 123)
    monkeypatch.setattr(cap_hold, 'ensure_summary', Mock())
    monkeypatch.setattr(
        live.live_cap_capacity,
        'acquire',
        lambda uid, month, identity=None: live.live_cap_capacity.Capacity(uid, month, identity or 'lease'),
    )
    monkeypatch.setattr(live.live_cap_capacity, 'release', Mock())
    monkeypatch.setattr(live.live_cap_codec, 'encode', write_wav)
    monkeypatch.setattr(
        cap_hold, 'recovery_directory', lambda uid: __import__('tempfile').TemporaryDirectory(dir=tmp_path)
    )

    def upload(uid, path, identity, meta, **kwargs):
        with wave.open(path, 'rb') as wav:
            persisted.append((wav.readframes(wav.getnframes()), wav.getframerate(), meta))
        return {'audio_path': f'chunks/{uid}/cap-held/{identity}.wav.enc', 'metadata': 'encrypted'}

    monkeypatch.setattr(cap_hold, 'upload_held_audio', upload)
    monkeypatch.setattr(
        live.live_cap_manifest,
        'publish',
        lambda uid, path, source, meta, duration, **kwargs: None,
    )
    monkeypatch.setattr(cap_hold, 'release', Mock())
    monkeypatch.setattr(cap_hold, 'holds', lambda uid: SimpleNamespace(document=lambda identity: identity))
    return persisted


async def test_only_published_seconds_are_reported_and_close_flushes_tail(host, persistence):
    hold = live.LiveHeldAudio(host)
    hold.append(b'\x01\x02' * 8000, 16000, 100.25, 'conversation')
    await hold.notice()
    assert host.request.websocket.send_json.call_args.args[0]['held_seconds'] == 0
    await hold.close()
    assert persistence[0][0] == b'\x01\x02' * 8000
    assert persistence[0][2]['timestamp'] == 100.25
    assert persistence[0][2]['target_conversation_id'] == 'conversation'
    assert persistence[0][2]['origin'] == 'live'
    assert persistence[0][2]['recording_session_id'] == 'socket-1'
    assert persistence[0][2]['client_device_id'] == 'device'
    assert hold.seconds == 0.5
    assert not hold.pending and not hold.buffers


async def test_large_packet_is_split_and_resume_drains_without_overlap(host, persistence):
    hold = live.LiveHeldAudio(host)
    hold.append(b'\0' * 80000, 16000, 10.5, 'a')
    await hold.flush(force=True)
    await hold.notice(paused=False)
    assert [len(row[0]) for row in persistence] == [80000]
    assert [row[2]['timestamp'] for row in persistence] == [10.5]
    assert host.request.websocket.send_json.call_args.args[0] == {
        'type': 'stt_cap_live_held',
        'session_id': 'socket-1',
        'paused': False,
        'held_seconds': 2,
        'reset_at': 123,
    }
    await hold.close()
    assert len(persistence) == 1


async def test_channel_and_conversation_boundaries_are_not_mixed(host, persistence):
    hold = live.LiveHeldAudio(host)
    hold.append(b'\1\0' * 100, 16000, 10, 'a', 0)
    hold.append(b'\2\0' * 100, 16000, 10, 'a', 1)
    hold.append(b'\3\0' * 100, 16000, 11, 'b', 0)
    await hold.close()
    assert {(m['channel'], m['target_conversation_id']) for _, _, m in persistence} == {(0, 'a'), (1, 'a'), (0, 'b')}
    assert hold.seconds == pytest.approx(300 / 16000)


def test_live_identity_includes_session_channel_without_changing_sync_identity(tmp_path):
    path = tmp_path / '100.wav'
    path.write_bytes(b'same')
    meta = {'timestamp': 100, 'source': 'phone', 'origin': 'live', 'recording_session_id': 'a', 'channel': 0}
    first = cap_hold.capture_identity(str(path), meta)
    assert first != cap_hold.capture_identity(str(path), {**meta, 'channel': 1})
    assert first != cap_hold.capture_identity(str(path), {**meta, 'recording_session_id': 'b'})


async def test_failed_persistence_does_not_increment_receipt_or_discard_pcm(host, persistence, monkeypatch):
    hold = live.LiveHeldAudio(host)
    hold.append(b'\0' * 32000, 16000, 10, 'a')
    save = Mock(side_effect=RuntimeError('synthetic upload fault'))
    monkeypatch.setattr(live.live_cap_manifest, 'publish', save)
    with pytest.raises(RuntimeError):
        await hold.flush(force=True)
    assert hold.seconds == 0 and len(hold.pending) == 1
    save.side_effect = None
    save.return_value = {'audio_path': 'chunks/synthetic/cap-held/retry.wav.enc', 'metadata': 'encrypted'}
    await hold.close()
    assert hold.seconds == 1 and not hold.pending


def test_reservation_is_per_user_month_and_fail_closed(monkeypatch):
    from contextlib import nullcontext

    client = StrictFirestore()
    monkeypatch.setattr(live, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(live, 'external_write_fence', lambda uid: nullcontext())
    monkeypatch.setattr(live, 'MAX_MONTHLY_BYTES', 100)
    monkeypatch.setattr(live, 'MAX_MONTHLY_CHUNKS', 2)
    live.reserve('synthetic', 50)
    live.reserve('synthetic', 50)
    with pytest.raises(RuntimeError, match='capacity'):
        live.reserve('synthetic', 1)
    live.reserve('another', 50)
    assert sorted(row['bytes'] for row in client.rows.values()) == [50, 100]


@pytest.fixture
def receiver_type():
    from routers.listen.receiver import ListenReceiver

    return ListenReceiver


def test_capture_replay_and_successful_prefix_are_never_held_twice(host, receiver_type):
    receiver = receiver_type.__new__(receiver_type)
    receiver.host = host
    receiver.live_hold = live.LiveHeldAudio(host)
    receiver.capture_timeline = SimpleNamespace(wall=lambda sample: 100 + sample / 16000)
    receiver._cap_decided_spans = []
    pcm = b'\0' * 32000
    receiver._observe_cap_capture(pcm, 16000, 0, True)
    receiver._observe_cap_capture(pcm, 16000, 0, False)  # Failed successor replay of paid prefix.
    receiver._observe_cap_capture(pcm, 16000, 16000, False)
    receiver._observe_cap_capture(pcm, 16000, 16000, False)  # Replayed held tail.
    assert receiver.live_hold.pending_bytes == 0
    assert receiver.live_hold.buffered_seconds() == 1
    (span,) = receiver.live_hold._capture.spans
    assert bytes(span.data) == pcm and span.timestamp == 101


async def test_receive_cap_transition_and_resume_have_no_gap_or_paid_overlap(
    host, persistence, receiver_type, monkeypatch
):
    from utils.stt_cap_dispatch import LiveAdmission
    from routers.listen import legacy_recovery

    receiver = receiver_type.__new__(receiver_type)
    receiver.host = host
    host.request.sample_rate = 16000
    host.stt_service = 'soniox'
    receiver.cap_admission = LiveAdmission('synthetic')
    receiver.cap_admission.managed, receiver.cap_admission.remaining = False, 0
    receiver.cap_admission.reason = 'plan_allowance_exhausted'
    receiver.cap_admission.omi_selected = True
    receiver.cap_paused = False
    receiver.live_hold = live.LiveHeldAudio(host)
    receiver.capture_timeline = SimpleNamespace(wall=lambda sample: 100 + sample / 16000)
    receiver._cap_decided_spans = []
    receiver._stt_buffer_start_sample = 16000
    receiver._cap_capture_cursor = 0
    receiver._cap_capture_origin = 100
    receiver.recovery = None
    # A successful live prefix cannot be retained even when replayed at the cap.
    receiver._observe_cap_capture(b'\1\0' * 16000, 16000, 0, True)
    held_pcm = b'\2\0' * 16000
    host.state.last_audio_received_time = 500.0
    await receiver._flush_stt_buffer(bytearray(held_pcm))
    assert not persistence  # Sub-minute denied audio stays buffered until seal.
    # The receipt span is excluded from the elapsed usage meter.
    assert receiver.cap_admission.held_spans == [[499.0, 500.0]]
    forwarded = []

    async def forward(self, buffer, **kwargs):
        assert host.request.websocket.send_json.call_args.args[0]['paused'] is False
        forwarded.append(bytes(buffer))
        buffer.clear()

    monkeypatch.setattr(legacy_recovery, 'flush_stt_buffer', forward)
    receiver.cap_admission.managed, receiver.cap_admission.remaining = True, None
    receiver._stt_buffer_start_sample = 32000
    resumed = b'\3\0' * 8000
    host.state.last_audio_received_time = 500.5
    await receiver._flush_stt_buffer(bytearray(resumed))
    assert persistence[0][2]['timestamp'] == 101
    assert forwarded == [resumed]
    assert b''.join(item[0] for item in persistence) == held_pcm
    assert receiver.cap_admission.held_spans == [[499.0, 500.0]]  # Resumed audio is not held.


def test_recovery_storage_uses_the_capture_month_and_combined_ceiling(monkeypatch):
    from contextlib import nullcontext

    client = StrictFirestore()
    monkeypatch.setattr(live, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(live, 'external_write_fence', lambda uid: nullcontext())
    monkeypatch.setattr(live, 'MAX_MONTHLY_BYTES', 100)
    live.reserve('synthetic', 100, month='2026-09')
    live.reserve('synthetic', 100, month='2026-09', recovery=True)
    with pytest.raises(RuntimeError):
        live.reserve('synthetic', 1, month='2026-09', recovery=True)
    row = client.rows[('users', 'synthetic', 'stt_cap_live_storage', '2026-09')]
    assert row['bytes'] == 200 and row['source_bytes'] == 100


def test_group_recovery_joins_pcm_without_duplicate_wav_headers(tmp_path, monkeypatch):
    def decode(uid, row, path):
        write_wav(path, (b'\1\0' if row['audio_path'].endswith('a') else b'\2\0') * 16000, 16000)

    monkeypatch.setattr(cap_hold, '_read_single_audio', decode)
    path = str(tmp_path / '100.wav')
    cap_hold.read_audio(
        'synthetic', {'audio_parts': ['chunks/synthetic/cap-held/a', 'chunks/synthetic/cap-held/b']}, path
    )
    with wave.open(path) as wav:
        assert wav.getnframes() == 32000
        assert wav.readframes(32000) == b'\1\0' * 16000 + b'\2\0' * 16000


def test_source_reservation_retries_do_not_consume_capacity_twice(monkeypatch):
    from contextlib import nullcontext

    client = StrictFirestore()
    monkeypatch.setattr(live, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(live, 'external_write_fence', lambda uid: nullcontext())
    for _ in range(3):
        live.reserve('synthetic', 123, month='2026-10', reservation_id='part-a')
    row = client.rows[('users', 'synthetic', 'stt_cap_live_storage', '2026-10')]
    assert row['bytes'] == 123 and row['chunks'] == 1


def test_channels_at_same_timestamp_have_distinct_recovery_ingest_anchors():
    from utils.sync.capture import chunk_identity

    first = chunk_identity('u', 'phone_call', 'device', False, 100, capture_partition='live:hold:channel:0')
    second = chunk_identity('u', 'phone_call', 'device', False, 100, capture_partition='live:hold:channel:1')
    assert first != second
    assert first == chunk_identity('u', 'phone_call', 'device', False, 100, capture_partition='live:hold:channel:0')


async def test_cancelled_owner_keeps_supervised_tail_flush_alive(host, persistence):
    import asyncio
    from utils.executors import start_background_task

    hold = live.LiveHeldAudio(host)
    hold.append(b'\1\0' * 8000, 16000, 100, 'a')
    stop, entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_close = hold.close

    async def delayed_close():
        entered.set()
        await release.wait()
        await original_close()

    hold.close = delayed_close
    custody = None

    async def owner():
        nonlocal custody
        custody = start_background_task(hold.finish_updates(None, stop), name='test_held_final_flush')
        await asyncio.shield(custody)

    task = start_background_task(owner(), name='test_held_owner')
    await entered.wait()
    task.cancel()
    await asyncio.wait({task})
    assert task.cancelled() and not custody.done()
    release.set()
    await custody
    assert hold.seconds == 0.5 and persistence[0][0] == b'\1\0' * 8000


async def test_cancel_during_executor_upload_keeps_wav_and_retires_once(host, persistence, monkeypatch):
    import asyncio
    import threading
    from pathlib import Path

    entered, release = threading.Event(), threading.Event()
    original = cap_hold.upload_held_audio
    paths = []

    def blocked_upload(uid, path, *args, **kwargs):
        paths.append(path)
        entered.set()
        assert release.wait(timeout=5)
        assert Path(path).is_file()
        return original(uid, path, *args, **kwargs)

    monkeypatch.setattr(cap_hold, 'upload_held_audio', blocked_upload)
    hold = live.LiveHeldAudio(host)
    hold.append(b'\x01\x02' * 8000, 16000, 100.25, 'conversation')
    caller = asyncio.create_task(hold.flush(force=True))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert Path(paths[0]).is_file()
        closer = asyncio.create_task(hold.close())
        release.set()
        await asyncio.wait_for(closer, timeout=5)
    finally:
        release.set()
    assert hold.seconds == 0.5 and len(persistence) == 1
    assert not hold.pending and not hold.buffers
    assert not Path(paths[0]).exists()


async def test_funded_resume_retries_recovery_after_final_live_group_seals(host, persistence):
    hold = live.LiveHeldAudio(host)
    hold.append(b'\x01\x02' * 8000, 16000, 100.25, 'conversation')
    await hold.flush(force=True)
    await hold.notice(paused=False)
    assert not hold.pending and not hold.buffers
    await hold.notice(paused=False)
    assert hold.seconds == 0.5  # Scheduler discovers durable intent; no memory timer.


async def test_two_contiguous_minutes_publish_two_objects_even_across_packet_boundary(host, persistence):
    hold = live.LiveHeldAudio(host)
    rate, total, first = 16000, 120 * 16000, 0
    while first < total:
        frames = min(7350, total - first)
        await hold.append_async(b'\1\0' * frames, rate, 100 + first / rate, 'a')
        await hold.flush()
        first += frames
    await hold.close()
    assert [len(data) for data, _, _ in persistence] == [60 * rate * 2] * 2
    assert [meta['timestamp'] for _, _, meta in persistence] == [100, 160]
    assert hold.seconds == 120


async def test_capture_month_boundary_flushes_exact_frames(host, persistence):
    from datetime import datetime, timezone

    boundary = datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()
    hold = live.LiveHeldAudio(host)
    hold.append(b'\1\0' * 16000, 16000, boundary - 0.5, 'a')
    await hold.close()
    assert [len(data) for data, _, _ in persistence] == [16000, 16000]
    assert [meta['live_storage_month'] for _, _, meta in persistence] == ['2026-10', '2026-11']


async def test_minute_publication_does_not_age_and_flush_its_new_tail(host, persistence, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(live.time, 'monotonic', lambda: clock[0])
    hold = live.LiveHeldAudio(host)
    hold.append(b'\1\0' * (59 * 16000 + 8000), 16000, 100, 'a')
    clock[0] = 160.0
    await hold.append_async(b'\1\0' * 16000, 16000, 159.5, 'a')
    await hold.flush()
    assert [len(data) for data, _, _ in persistence] == [60 * 16000 * 2]
    assert len(next(iter(hold.buffers.values()))[0]) == 16000
    await hold.close()
    assert hold.seconds == 60.5


async def test_multisecond_capture_callbacks_fit_the_existing_aggregate_bound(host, persistence):
    hold = live.LiveHeldAudio(host)
    hold.append(b'\1\0' * 3 * 16000, 16000, 100, 'a')
    hold.append(b'\2\0' * 4 * 16000, 16000, 103, 'a')
    await hold.close()
    assert hold.seconds == 7
    assert persistence[0][0] == b'\1\0' * 3 * 16000 + b'\2\0' * 4 * 16000


async def test_straddle_never_accepts_more_than_sixty_seconds(host, persistence, monkeypatch):
    hold = live.LiveHeldAudio(host)
    hold.append(b'\1\0' * (59 * 16000 + 8000), 16000, 100, 'a')
    with pytest.raises(RuntimeError, match='custody bound'):
        hold.append(b'\2\0' * 16000, 16000, 159.5, 'a')
    assert hold.buffered_seconds() == 59.5
    original = hold.append
    observed = []

    def append(*args, **kwargs):
        original(*args, **kwargs)
        observed.append(hold.buffered_seconds())

    monkeypatch.setattr(hold, 'append', append)
    await hold.append_async(b'\2\0' * 16000, 16000, 159.5, 'a')
    await hold.close()
    assert max(observed) <= 60
    assert [len(data) for data, _, _ in persistence] == [60 * 32000, 16000]
    assert b''.join(data for data, _, _ in persistence) == b'\1\0' * (59 * 16000 + 8000) + b'\2\0' * 16000
