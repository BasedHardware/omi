"""Fault injection for the capture -> immutable receipt custody boundary."""

import asyncio
from collections import deque
from contextlib import nullcontext
import hashlib
import json
import struct
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from starlette.websockets import WebSocketState
from fastapi.websockets import WebSocketDisconnect
from google.api_core.exceptions import PreconditionFailed
from google.cloud.exceptions import NotFound

from config.audio_outbox import enabled
from utils.other import storage, live_audio_archive, audio_outbox
from utils.other.audio_outbox import AudioReceipt, commit_pcm, read_pcm
from routers.listen.transcripts import TranscriptProcessor
from utils.other.live_audio_archive import LiveAudioArchive
from utils.other.raw_audio import CapturePack, AudioSegment, decode_capture
from utils.other.raw_audio_read import list_packs, read_pack
from utils.pusher_protocol import AudioBackpressure, ByteBudget, append_bounded, extend_bounded, bound_private_pending
import routers.pusher as pusher


class Blob:
    def __init__(self, name):
        self.name = name
        self.metadata = {}
        self.stored_metadata = {}
        self.data = None
        self.generation = None

    @property
    def size(self):
        return len(self.data or b'')

    def upload_from_string(self, data, *, if_generation_match, **kwargs):
        assert if_generation_match == 0
        if self.data is not None:
            raise PreconditionFailed('immutable')
        self.data = data
        self.stored_metadata = dict(self.metadata)
        self.generation = 17

    def reload(self, **kwargs):
        if self.data is None:
            raise NotFound('missing')
        self.metadata = dict(self.stored_metadata)

    def download_as_bytes(self, **kwargs):
        if kwargs.get('if_generation_match', self.generation) != self.generation:
            raise PreconditionFailed('generation changed')
        return self.data


class Bucket:
    name = 'test-audio-outbox'

    def __init__(self):
        self.blobs = {}

    def blob(self, name, generation=None):
        blob = self.blobs.setdefault(name, Blob(name))
        if generation is not None and blob.generation != generation:
            raise NotFound('pinned generation missing')
        return blob

    def list_blobs(self, prefix, **kwargs):
        return [blob for name, blob in self.blobs.items() if name.startswith(prefix) and blob.data is not None]


@pytest.fixture
def remote(monkeypatch):
    bucket = Bucket()
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', bucket.name)
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda *a: nullcontext())
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: False)
    return bucket


def host():
    result = SimpleNamespace(
        private_cloud_sync_enabled=True,
        request=SimpleNamespace(
            uid='owner',
            codec='pcm16',
            sample_rate=16000,
            source='omi',
            client_device_context=None,
            websocket=SimpleNamespace(headers={}, query_params={'audio_custody': '1'}),
        ),
        events=[],
    )
    result.spawn = lambda coro, **kw: asyncio.create_task(coro)
    result.send_event = result.events.append
    return result


def test_default_on_and_only_explicit_emergency_rollback(monkeypatch):
    monkeypatch.delenv('AUDIO_DURABLE_OUTBOX_ENABLED', raising=False)
    assert enabled()
    for value in ('', 'garbage', '0', 'true'):
        monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', value)
        assert enabled()
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')
    assert not enabled()


def test_full_queue_keeps_old_and_new_unacknowledged():
    queue = deque([b'old'] * 20, maxlen=20)
    with pytest.raises(AudioBackpressure) as error:
        append_bounded(queue, b'new', 'private_cloud')
    assert error.value.pending == b'new'
    assert list(queue) == [b'old'] * 20


def test_20_mib_budget_does_not_reject_or_truncate_new_frame():
    budget = ByteBudget(20 * 1024 * 1024)
    retained = bytearray()
    extend_bounded(retained, b'a' * budget.limit, 'private_cloud_buffer', budget)
    with pytest.raises(AudioBackpressure) as error:
        extend_bounded(retained, b'new-frame', 'private_cloud_buffer', budget)
    assert error.value.pending == b'new-frame'
    assert len(retained) == budget.limit == budget.used


def test_pending_overflow_never_removes_conversation():
    pending = {str(i): {'data': b'frame'} for i in range(20)}
    budget = ByteBudget(1000)
    budget.reserve(100)
    with pytest.raises(AudioBackpressure):
        bound_private_pending(pending, budget)
    assert len(pending) == 20 and pending['0']['data'] == b'frame' and budget.used == 100


def test_receipt_survives_pod_loss_and_playback_checks_actual_bytes(remote):
    pcm = struct.pack('<160h', *range(160))
    original = commit_pcm('owner', pcm, 'conversation', 1000, 16000, 'root', 0)
    # Only a serialized receipt and remote objects cross the process boundary.
    restored = AudioReceipt(**json.loads(json.dumps(original.to_dict())))
    assert restored.generation == '17' and restored.manifest_generation == '17'
    assert read_pcm('owner', restored) == pcm
    manifest = json.loads(remote.blob(restored.manifest_path).data)
    assert manifest['frames'][0]['samples'] == 160
    assert manifest['media']['generation'] == '17'
    assert manifest['capture_end_checkpoint']['sequence'] == 0
    indexed = list_packs(remote, 'owner', 'conversation')
    assert indexed and read_pack(remote, indexed[0]['path'], 'owner') == pcm
    # Exercise the production playback read path after losing process state,
    # rather than treating object existence or a receipt alone as acceptance.
    assert storage.download_audio_chunks_and_merge('owner', 'conversation', [1000]) == pcm
    # Same logical commit is immutable and retry-safe after a lost ACK.
    assert commit_pcm('owner', pcm, 'conversation', 1000, 16000, 'root', 0) == restored
    remote.blob(restored.path).generation = 18
    with pytest.raises(NotFound):
        read_pcm('owner', restored)


def test_manifest_failure_never_issues_receipt(remote, monkeypatch):
    real = storage.archive_capture_bytes

    def write(uid, raw, prefix, *args, **kwargs):
        if prefix == 'audio-outbox':
            raise OSError('manifest unavailable')
        return real(uid, raw, prefix, *args, **kwargs)

    monkeypatch.setattr(storage, 'archive_capture_bytes', write)
    with pytest.raises(OSError):
        commit_pcm('owner', b'\x01\x00' * 160, 'conversation', 1000, 16000, 'root', 0)
    assert len(remote.list_blobs('raw-live/owner/conversation/')) == 1


def test_one_sample_commits_exact_pcm_even_when_encoder_is_unavailable(remote, monkeypatch):
    encoder = MagicMock(side_effect=RuntimeError('encoder unavailable'))
    monkeypatch.setattr(AudioSegment, 'export', encoder)
    receipt = commit_pcm('owner', b'\x01\x00', 'conversation', 1000, 16000, 'root', 0)
    assert remote.blob(receipt.path).data == b'\x01\x00'
    assert read_pcm('owner', receipt) == b'\x01\x00'
    encoder.assert_not_called()


def test_unsigned_pcm8_original_and_decoded_sample_count_are_preserved():
    pack = CapturePack('pcm8', 16000)
    pack.append(b'\x00\x80\xff', 'conversation', 1000, 3)
    raw, metadata = pack.encoded(preserve_pcm=True)
    assert raw == b'\x00\x80\xff'
    assert decode_capture(raw, metadata) == struct.pack('<3h', -32768, 0, 32512)


@pytest.mark.asyncio
async def test_legacy_client_gets_no_unsolicited_audio_receipt(remote):
    h = host()
    h.request.websocket.query_params = {}
    archive = LiveAudioArchive(h)
    await archive.append(b'\x01\x00', 'conversation', 1000, 1)
    await archive.close()
    assert not h.events and remote.list_blobs('audio-outbox/owner/')


def test_conversation_deletion_refuses_new_archive_without_audio_ack(remote, monkeypatch):
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: True)
    with pytest.raises(storage.audio_packs.CaptureDeleted):
        commit_pcm('owner', b'\x01\x00', 'conversation', 1000, 16000, 'root', 0)
    assert not remote.list_blobs('raw-live/')


def test_enhanced_receipt_verifies_encrypted_media_and_manifest(remote, monkeypatch):
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'enhanced')
    pcm = b'\x01\x00' * 160
    receipt = commit_pcm('owner', pcm, 'conversation', 1000, 16000, 'root', 0)
    assert receipt.path.endswith('.enc') and receipt.manifest_path.endswith('.enc')
    assert read_pcm('owner', receipt) == pcm
    remote.blob(receipt.manifest_path).data = b'corrupt'
    with pytest.raises(Exception):
        read_pcm('owner', receipt)


@pytest.mark.asyncio
async def test_transcript_write_waits_for_audio_custody_before_any_database_call():
    persistence = MagicMock()

    async def unavailable():
        raise OSError('archive unavailable')

    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(
        receiver=SimpleNamespace(raw_archive=SimpleNamespace(durable=True, ensure_durable=unavailable)),
        persistence=persistence,
    )
    with pytest.raises(OSError):
        await processor._update_live_conversation(None, [object()], [], None, None)
    persistence.call.assert_not_called()


@pytest.mark.asyncio
async def test_raw_upload_failure_keeps_only_copy_and_retries_exact_pack(remote, monkeypatch):
    h = host()
    archive = LiveAudioArchive(h)
    pcm = b'\x01\x00' * 160
    await archive.append(
        pcm,
        'conversation',
        1000,
        160,
        source_frame={
            'capture_root': 'device-root',
            'clock_epoch': 1,
            'source_frame': 7,
        },
    )
    real = live_audio_archive.commit_capture
    monkeypatch.setattr(live_audio_archive, 'commit_capture', MagicMock(side_effect=OSError('offline')))
    with pytest.raises(OSError):
        await archive.close()
    assert not h.events
    assert archive.uncommitted and bytes(next(iter(archive.uncommitted.values()))[0].data) == pcm
    monkeypatch.setattr(live_audio_archive, 'commit_capture', real)
    await archive.close()
    assert not archive.uncommitted
    event = h.events[0]
    assert event.to_json()['type'] == 'audio_custody'
    assert event.frames[0]['source']['source_frame'] == 7
    assert read_pcm('owner', AudioReceipt(**event.receipt)) == pcm


@pytest.mark.asyncio
async def test_four_concurrent_commits_backpressure_fifth_without_clearing(remote, monkeypatch):
    h = host()
    archive = LiveAudioArchive(h)
    release = asyncio.Event()
    started = []
    real = archive._write

    async def blocked(pack, channel):
        started.append(channel)
        await release.wait()
        await real(pack, channel)

    monkeypatch.setattr(archive, '_write', blocked)
    for channel in range(4):
        await archive.append(b'\x01\x00', 'conversation', 1000, 1, channel)
        await archive.flush(channel)
    await archive.append(b'\x05\x00', 'conversation', 1000, 1, 4)
    fifth = asyncio.create_task(archive.flush(4))
    await asyncio.sleep(0)
    assert len(archive.inflight) == 4 and not fifth.done()
    assert archive.packs[4].data == b'\x05\x00'
    release.set()
    await fifth
    await archive.close()
    assert len(h.events) == 5 and not archive.uncommitted and not archive.packs


@pytest.mark.asyncio
async def test_cancelled_commit_keeps_frozen_pack_unacknowledged(remote, monkeypatch):
    archive = LiveAudioArchive(host())
    await archive.append(b'\x01\x00', 'conversation', 1000, 1)
    release = asyncio.Event()

    async def blocked(*args):
        await release.wait()

    real = archive._write
    monkeypatch.setattr(archive, '_write', blocked)
    await archive.flush(0)
    task = next(iter(archive.inflight))
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert archive.uncommitted and not archive.host.events
    monkeypatch.setattr(archive, '_write', real)
    await archive.ensure_durable()
    assert not archive.uncommitted and archive.host.events


class Socket:
    def __init__(self, frames):
        self.frames = deque(frames)
        self.sent = []
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None
        self.queued = asyncio.Event()

    async def accept(self):
        pass

    async def send_bytes(self, data):
        self.sent.append(data)
        if len(self.sent) == 22:
            self.queued.set()

    async def receive_bytes(self):
        await asyncio.sleep(0)
        if self.frames:
            return self.frames.popleft()
        raise WebSocketDisconnect(1000)

    async def close(self, code, **kwargs):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_real_pusher_more_than_20_chunks_and_projection_failure_still_has_receipts(remote, monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', MagicMock(side_effect=OSError('projection unavailable')))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.001)
    frames = [struct.pack('<I', 103) + b'conversation']
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(25)]
    frames.extend(struct.pack('<Id', 101, 1000 + n * 0.01) + pcm for n, pcm in enumerate(payloads))
    sock = Socket(frames)
    # Force a projection flush after each receipt, hold the first hydration,
    # then fill all 20 queue slots. Frame 22 can commit but cannot enqueue;
    # the receiver must stop before reading any later frame from its producer.
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    release = threading.Event()
    real_read = pusher.read_pcm

    def blocked_read(*args):
        if not release.wait(30):
            raise TimeoutError('test projection release not signalled')
        return real_read(*args)

    monkeypatch.setattr(pusher, 'read_pcm', blocked_read)
    task = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    try:
        await asyncio.wait_for(sock.queued.wait(), 30)
        assert len(sock.frames) >= 3 and not task.done()
    finally:
        release.set()
    await task
    receipts = [AudioReceipt(**json.loads(frame[4:])['receipt']) for frame in sock.sent]
    assert len(receipts) == 25
    assert [read_pcm('owner', receipt) for receipt in receipts] == payloads
    assert pusher.upload_audio_chunks_batch.call_count >= 1


@pytest.mark.asyncio
async def test_reconnect_recovers_receipts_after_pusher_process_state_is_lost(remote, monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', MagicMock(side_effect=OSError('projection unavailable')))
    frames = [struct.pack('<I', 103) + b'conversation', struct.pack('<Id', 101, 1000) + b'\x01\x00' * 160]
    first = Socket(frames)
    await pusher._websocket_util_trigger(first, 'owner', 16000, audio_custody=1)
    receipt = json.loads(first.sent[0][4:])['receipt']
    del first
    second = Socket(frames)
    await pusher._websocket_util_trigger(second, 'owner', 16000, audio_custody=1)
    assert read_pcm('owner', AudioReceipt(**receipt)) == b'\x01\x00' * 160
    assert read_pcm('owner', AudioReceipt(**json.loads(second.sent[0][4:])['receipt'])) == b'\x01\x00' * 160


@pytest.mark.asyncio
async def test_pusher_upload_failure_never_audio_acknowledges(remote, monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher, 'commit_pcm', MagicMock(side_effect=OSError('archive unavailable')))
    sock = Socket([struct.pack('<I', 103) + b'conversation', struct.pack('<Id', 101, 1000) + b'\x01\x00'])
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert not sock.sent and sock.close_code == 1011
