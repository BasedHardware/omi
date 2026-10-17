"""Live custody uses decoded, unique, denied capture and the existing hold writer."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import wave

import pytest

from utils.sync import live_cap_hold as live
from utils.sync import cap_hold, held_audio_summary
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture
def host():
    return SimpleNamespace(
        request=SimpleNamespace(uid='synthetic', source='phone', websocket=SimpleNamespace(send_json=AsyncMock())),
        state=SimpleNamespace(current_conversation_id='conversation', conversation_sample_ranges=[]),
        client_device_context=SimpleNamespace(device_id='device'),
        session_id='socket-1',
    )


@pytest.fixture
def persistence(monkeypatch, tmp_path):
    persisted = []
    monkeypatch.setattr(held_audio_summary, 'next_utc_month_start', lambda: 123)
    monkeypatch.setattr(live, 'reserve', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cap_hold, 'recovery_directory', lambda uid: __import__('tempfile').TemporaryDirectory(dir=tmp_path)
    )

    def upload(uid, path, identity, meta, **kwargs):
        with wave.open(path, 'rb') as wav:
            persisted.append((wav.readframes(wav.getnframes()), wav.getframerate(), meta))
        return {'audio_path': f'chunks/{uid}/cap-held/{identity}.wav.enc', 'metadata': 'encrypted'}

    monkeypatch.setattr(cap_hold, 'upload_held_audio', upload)
    monkeypatch.setattr(
        live.live_cap_manifest, 'append', lambda uid, group, fields, duration: group['seconds'] + duration
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
    assert hold.seconds == 0.5
    assert not hold.pending and not hold.buffers


async def test_large_packet_is_split_and_resume_drains_without_overlap(host, persistence):
    hold = live.LiveHeldAudio(host)
    hold.append(b'\0' * 80000, 16000, 10.5, 'a')
    await hold.flush(force=True)
    await hold.notice(paused=False)
    assert [len(row[0]) for row in persistence] == [32000, 32000, 16000]
    assert [row[2]['timestamp'] for row in persistence] == [10.5, 11.5, 12.5]
    assert host.request.websocket.send_json.call_args.args[0] == {
        'type': 'stt_cap_live_held',
        'session_id': 'socket-1',
        'paused': False,
        'held_seconds': 2,
        'reset_at': 123,
    }
    await hold.close()
    assert len(persistence) == 3


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
    monkeypatch.setattr(cap_hold, 'upload_held_audio', save)
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
    assert receiver.live_hold.pending_bytes == 32000
    assert len(receiver.live_hold.pending) == 1
    assert receiver.live_hold.pending[0][2] == 101


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
    await receiver._flush_stt_buffer(bytearray(held_pcm))
    assert persistence[0][0] == held_pcm
    assert persistence[0][2]['timestamp'] == 101
    forwarded = []

    async def forward(self, buffer, **kwargs):
        assert host.request.websocket.send_json.call_args.args[0]['paused'] is False
        forwarded.append(bytes(buffer))
        buffer.clear()

    monkeypatch.setattr(legacy_recovery, 'flush_stt_buffer', forward)
    receiver.cap_admission.managed, receiver.cap_admission.remaining = True, None
    receiver._stt_buffer_start_sample = 32000
    resumed = b'\3\0' * 8000
    await receiver._flush_stt_buffer(bytearray(resumed))
    assert forwarded == [resumed]
    assert b''.join(item[0] for item in persistence) == held_pcm


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


def test_grouped_live_manifest_is_idempotent_and_fenced_after_recovery_claim(monkeypatch):
    from contextlib import nullcontext
    from utils.sync import live_cap_manifest as manifest

    total = ('users', 'synthetic', 'stt_cap_hold_summary', 'current')
    client = StrictFirestore({total: {'version': 2, 'seconds': 0, 'count': 0}})
    for module in (manifest, cap_hold):
        monkeypatch.setattr(module, 'get_firestore_client', lambda: client)
        monkeypatch.setattr(module, 'external_write_fence', lambda uid: nullcontext())
    group = manifest.new_group(100, 0, 16000, 'owner', '2026-10')
    fields = {'audio_path': 'chunks/synthetic/cap-held/a', 'metadata': 'encrypted'}
    assert manifest.append('synthetic', group, fields, 1) == 1
    assert manifest.append('synthetic', group, fields, 1) == 1
    assert manifest.append('synthetic', group, {**fields, 'audio_path': 'chunks/synthetic/cap-held/b'}, 1) == 2
    assert client.rows[total] == {'version': 2, 'seconds': 2, 'count': 1}
    ref = cap_hold.holds('synthetic').document(group['id'])
    assert cap_hold.claim('synthetic', ref, manifest.time.time()) is None
    cap_hold.release('synthetic', ref, group['token'])
    assert cap_hold.claim('synthetic', ref, manifest.time.time())
    assert manifest.append('synthetic', group, {**fields, 'audio_path': 'chunks/synthetic/cap-held/c'}, 1) is None
    assert client.rows[total]['seconds'] == 2


def test_group_recovery_joins_pcm_without_duplicate_wav_headers(tmp_path, monkeypatch):
    def decode(uid, row, path):
        live.write_wav(path, (b'\1\0' if row['audio_path'].endswith('a') else b'\2\0') * 16000, 16000)

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
