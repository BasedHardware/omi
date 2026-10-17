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

    async def save(uid, path, meta, reason, receipt):
        with wave.open(path, 'rb') as wav:
            persisted.append((wav.readframes(wav.getnframes()), wav.getframerate(), meta))

    monkeypatch.setattr(cap_hold, '_hold_capture', save)
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
    save = AsyncMock(side_effect=RuntimeError('synthetic upload fault'))
    monkeypatch.setattr(cap_hold, '_hold_capture', save)
    with pytest.raises(RuntimeError):
        await hold.flush(force=True)
    assert hold.seconds == 0 and len(hold.pending) == 1
    save.side_effect = None
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
