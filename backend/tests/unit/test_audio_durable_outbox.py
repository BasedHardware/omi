"""Fault injection for the capture -> immutable receipt custody boundary."""

import asyncio
from collections import deque
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
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
from utils.other import audio_outbox_metrics
from utils.other.audio_outbox import AudioReceipt, commit_pcm, read_pcm
from routers.listen.transcripts import TranscriptProcessor
from utils.other.live_audio_archive import LiveAudioArchive
from utils.other.raw_audio import CapturePack, AudioSegment, decode_capture
from utils.other.raw_audio_read import list_packs, read_pack
from database.audio_timeline import span_blob_metadata
from database import _client, sync_ledger
from utils.other import local_storage
from utils.sync import staging_custody
from utils.other.audio_chunks import iter_audio_chunk_pcm
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

    def delete(self, *, if_generation_match, **kwargs):
        assert if_generation_match == self.generation
        self.data = None


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


def test_first_refusal_before_first_scrape_has_an_alert_timestamp(monkeypatch):
    monkeypatch.setattr(audio_outbox_metrics, 'time', SimpleNamespace(time=lambda: 1234567))
    audio_outbox_metrics.record_would_drop('pusher_queue')
    assert audio_outbox_metrics.LAST_RISK._value.get() == 1234567
    audio_outbox_metrics.record_failure('commit')
    assert audio_outbox_metrics.LAST_RISK._value.get() == 1234567


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


@pytest.mark.parametrize('manifest_committed', [False, True])
@pytest.mark.parametrize('incident_hold', [False, True])
def test_sync_cleanup_cannot_spend_outbox_custody(remote, monkeypatch, tmp_path, manifest_committed, incident_hold):
    """A sync completion never authorizes deletion of live media or manifests.

    Exercise the real archive writer and both receipt builders, including the
    media-only state left by an interrupted outbox commit. Only independently
    receipted sync staging is eligible, and its incident hold still wins.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.delenv('AUDIO_CLEANUP_HOLD_ENABLED', raising=False)
    monkeypatch.setenv(
        'AUDIO_CLEANUP_HOLD_WINDOWS',
        '2026-10-24T08:00:00Z..2026-10-24T09:00:00Z' if incident_hold else '2026-10-22T13:36:30Z..2026-10-24T07:16:00Z',
    )
    stamp = int(datetime(2026, 10, 24, 8, tzinfo=timezone.utc).timestamp())
    raw = f'syncing/owner/job/audio_pcm16_{stamp}.bin'
    Path(raw).parent.mkdir(parents=True)
    Path(raw).write_bytes(b'synthetic sync original')
    archive = storage.archive_capture_bytes('owner', Path(raw).read_bytes(), 'raw-sync', Path(raw).name, {})
    receipt = staging_custody.make_staging_custody_receipt('owner', [raw], [archive])
    assert receipt is not None
    staged = remote.blob(raw)
    staged.upload_from_string(Path(raw).read_bytes(), if_generation_match=0)
    staged.md5_hash = receipt['staging'][0]['md5']
    ledger = {
        'job_id': 'job',
        'status': 'completed',
        'staging_custody': receipt,
        'result': {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'},
    }
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: None)
    ref = SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: ledger))
    monkeypatch.setattr(sync_ledger, 'sync_content_reference', lambda *args: ref)
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: SimpleNamespace(bucket=lambda name: remote))
    monkeypatch.setattr(storage, 'syncing_local_bucket', remote.name)
    real_archive = storage.archive_capture_bytes

    def write(uid, payload, prefix, *args, **kwargs):
        if prefix == 'audio-outbox' and not manifest_committed:
            raise OSError('manifest unavailable')
        return real_archive(uid, payload, prefix, *args, **kwargs)

    monkeypatch.setattr(storage, 'archive_capture_bytes', write)
    pcm = b'\x01\x00' * 160
    if manifest_committed:
        outbox_receipt = commit_pcm('owner', pcm, 'conversation', stamp, 16000, 'root', 0)
    else:
        with pytest.raises(OSError, match='manifest unavailable'):
            commit_pcm('owner', pcm, 'conversation', stamp, 16000, 'root', 0)
    outbox = remote.list_blobs('raw-live/owner/') + remote.list_blobs('audio-outbox/owner/')
    assert len(outbox) == (2 if manifest_committed else 1)
    outbox_paths = [blob.name for blob in outbox]
    assert staging_custody.make_staging_custody_receipt('owner', [raw], outbox_paths) is None
    context = {'uid': 'owner', 'content_id': 'content', 'job_id': 'job'}
    assert staging_custody.cleanup_sync_staging([raw, *outbox_paths], **context) == 0
    assert staged.data is not None
    assert staging_custody.cleanup_sync_staging([raw], **context) == (0 if incident_hold else 1)
    assert (staged.data is not None) is incident_hold
    assert remote.blob(archive).data == Path(raw).read_bytes()
    assert all(blob.data is not None for blob in outbox)
    if manifest_committed:
        assert read_pcm('owner', outbox_receipt) == pcm


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


@pytest.mark.asyncio
async def test_spawn_refusal_keeps_pack_and_next_barrier_retries(remote):
    h = host()
    archive = LiveAudioArchive(h)
    await archive.append(b'\x01\x00', 'conversation', 1000, 1)

    def refused(*args, **kwargs):
        raise RuntimeError('supervisor closing')

    h.spawn = refused
    with pytest.raises(RuntimeError):
        await archive.flush(0)
    assert archive.uncommitted and not h.events and not archive.running
    await archive.ensure_durable()
    assert not archive.uncommitted and h.events


@pytest.mark.asyncio
async def test_retry_snapshot_skips_pack_committed_while_another_retry_awaited(remote, monkeypatch):
    h = host()
    archive = LiveAudioArchive(h)
    await archive.append(b'\x01\x00', 'conversation', 1000, 1, 0)
    await archive.append(b'\x02\x00', 'conversation', 1000, 1, 1)
    release_second = asyncio.Event()
    attempts = []
    second_task = None
    real_write = archive._write

    async def interleaved_write(pack, channel):
        attempts.append(channel)
        if channel == 0 and attempts.count(0) == 1:
            raise OSError('first pack needs retry')
        if channel == 0:
            release_second.set()
            assert second_task is not None
            await second_task
        elif attempts.count(1) == 1:
            await release_second.wait()
        await real_write(pack, channel)

    monkeypatch.setattr(archive, '_write', interleaved_write)
    await archive.flush(0)
    first_task = next(iter(archive.inflight))
    await archive.flush(1)
    second_task = next(task for task in archive.inflight if task is not first_task)
    await asyncio.gather(first_task, return_exceptions=True)
    await archive.ensure_durable()
    assert attempts == [0, 1, 0]
    assert len(h.events) == 2 and all(event.frames for event in h.events)
    assert not archive.uncommitted


class Socket:
    def __init__(self, frames):
        self.frames = deque(frames)
        self.sent = []
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None

    async def accept(self):
        pass

    async def send_bytes(self, data):
        self.sent.append(data)

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
    # then fill all 20 queue slots. The next frame can commit but cannot
    # enqueue; observe actual queue pressure rather than assuming how many
    # receipts the consumer drained before its first hydration awaited.
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    release = threading.Event()
    hydration_started = asyncio.Event()
    pressured = asyncio.Event()
    loop = asyncio.get_running_loop()
    real_read = pusher.read_pcm
    real_would_drop = pusher.record_would_drop
    real_receive = sock.receive_bytes
    received = 0

    async def gate_after_first_audio():
        nonlocal received
        if received == 2:  # Conversation binding plus the first PCM frame.
            await hydration_started.wait()
        frame = await real_receive()
        received += 1
        return frame

    monkeypatch.setattr(sock, 'receive_bytes', gate_after_first_audio)

    def observe_pressure(stage):
        real_would_drop(stage)
        if stage == 'pusher_queue':
            pressured.set()

    monkeypatch.setattr(pusher, 'record_would_drop', observe_pressure)

    def blocked_read(*args):
        loop.call_soon_threadsafe(hydration_started.set)
        if not release.wait(30):
            raise TimeoutError('test projection release not signalled')
        return real_read(*args)

    monkeypatch.setattr(pusher, 'read_pcm', blocked_read)
    task = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    try:
        await asyncio.wait_for(pressured.wait(), 30)
        assert 20 < len(sock.sent) < len(payloads) and not task.done()
        assert len(sock.frames) == len(payloads) - len(sock.sent)
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
    # A replacement producer may send DIFFERENT bytes for the same projected
    # clock. Custody preserves both generations rather than trusting the clock
    # or overwriting the earlier capture.
    second = Socket([frames[0], struct.pack('<Id', 101, 1000) + b'\x02\x00' * 160])
    await pusher._websocket_util_trigger(second, 'owner', 16000, audio_custody=1)
    assert read_pcm('owner', AudioReceipt(**receipt)) == b'\x01\x00' * 160
    assert read_pcm('owner', AudioReceipt(**json.loads(second.sent[0][4:])['receipt'])) == b'\x02\x00' * 160


@pytest.mark.asyncio
async def test_real_pending_conversation_overflow_keeps_every_receipt_after_projection_failure(remote, monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    interval = 0.123456
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', interval)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 1000000)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 1000000)
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', MagicMock(side_effect=OSError('projection unavailable')))
    stages = []
    real_would_drop = pusher.record_would_drop

    def observe(stage):
        stages.append(stage)
        real_would_drop(stage)

    monkeypatch.setattr(pusher, 'record_would_drop', observe)
    frames = []
    payloads = [struct.pack('<h', value) * 160 for value in range(21)]
    for index, pcm in enumerate(payloads):
        frames += [
            struct.pack('<I', 103) + f'conversation-{index}'.encode(),
            struct.pack('<Id', 101, 1000 + index) + pcm,
        ]
    sock = Socket(frames)
    first_archived = asyncio.Event()
    first_pending = asyncio.Event()
    all_archived = asyncio.Event()
    real_wait = pusher.wait_for_event
    real_send = sock.send_bytes
    real_receive = sock.receive_bytes
    private_waits = 0
    receipt_count = 0
    received = 0

    async def controlled_wait(event, seconds):
        nonlocal private_waits
        if seconds != interval or private_waits >= 2:
            return await real_wait(event, seconds)
        if private_waits == 0:
            await first_archived.wait()
        else:
            first_pending.set()
            await all_archived.wait()
        private_waits += 1
        await asyncio.sleep(0)

    async def observe_receipt(data):
        nonlocal receipt_count
        await real_send(data)
        if struct.unpack('<I', data[:4])[0] == 203:
            receipt_count += 1
            if receipt_count == 1:
                first_archived.set()
            if receipt_count == 21:
                all_archived.set()

    async def hold_rollover_until_first_pending():
        nonlocal received
        if received == 2:
            await first_pending.wait()
        frame = await real_receive()
        received += 1
        return frame

    # First retain one pending conversation, then deliver twenty more before
    # the next worker tick. Explicit latches exercise pending overflow without
    # racing the ordinary conversation-close flush or the queue's own cap.
    monkeypatch.setattr(pusher, 'wait_for_event', controlled_wait)
    monkeypatch.setattr(sock, 'send_bytes', observe_receipt)
    monkeypatch.setattr(sock, 'receive_bytes', hold_rollover_until_first_pending)
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    receipts = [
        AudioReceipt(**json.loads(frame[4:])['receipt'])
        for frame in sock.sent
        if struct.unpack('<I', frame[:4])[0] == 203
    ]
    assert 'pending_refs' in stages
    assert [receipt.conversation_id for receipt in receipts] == [f'conversation-{index}' for index in range(21)]
    assert [read_pcm('owner', receipt) for receipt in receipts] == payloads
    assert pusher.upload_audio_chunks_batch.call_count == 21


@pytest.mark.asyncio
async def test_pusher_projects_verified_receipts_in_capture_order(remote, monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    uploaded = []

    def project(chunks, *args, **kwargs):
        uploaded.extend(chunks)
        return ['projected']

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', project)
    monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda *a: [])
    payloads = [b'\x01\x00' * 160, b'\x02\x00' * 160]
    frames = [struct.pack('<I', 103) + b'conversation']
    frames.extend(struct.pack('<Id', 101, 1000 + i * 0.01) + pcm for i, pcm in enumerate(payloads))
    sock = Socket(frames)
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    assert [chunk['data'] for chunk in uploaded] == payloads
    assert [chunk['span']['samples'] for chunk in uploaded] == [160, 160]
    assert len(sock.sent) == 3  # Timeline negotiation, then two custody receipts.


@pytest.mark.asyncio
async def test_legacy_arrival_jitter_keeps_one_spanless_projection_and_exact_receipts(remote, monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    uploaded = []

    def project(chunks, *args, **kwargs):
        uploaded.append(chunks)
        assert len(chunks) == 1 and 'span' not in chunks[0]
        blob = remote.blob('chunks/owner/conversation/1000.000.batch.bin')
        blob.data = chunks[0]['data']

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', project)
    monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda *a: [])
    payloads = [struct.pack('<16000h', *[value] * 16000) for value in (1, 2, 3)]
    frames = [struct.pack('<I', 103) + b'conversation']
    frames += [struct.pack('<Id', 101, start) + pcm for start, pcm in zip((1000, 1001.02, 1002.01), payloads)]
    sock = Socket(frames)
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert len(uploaded) == 1 and uploaded[0] == [{'data': b''.join(payloads), 'timestamp': 1000}]
    receipts = [AudioReceipt(**json.loads(frame[4:])['receipt']) for frame in sock.sent]
    assert [read_pcm('owner', receipt) for receipt in receipts] == payloads
    assert all(remote.blob(receipt.path).metadata['clock_source'] == 'arrival_estimate' for receipt in receipts)
    # Estimated clocks never fabricate positioned raw fallback or duplicate
    # the legacy projection. Originals still recover by pinned receipts.
    assert not list_packs(remote, 'owner', 'conversation')
    chunks = storage.list_audio_chunks('owner', 'conversation')
    assert len(chunks) == 1 and chunks[0]['path'].startswith('chunks/')
    assert storage.download_audio_chunk_pcm('owner', chunks[0]['path']) == b''.join(payloads)


@pytest.mark.asyncio
async def test_pusher_upload_failure_never_audio_acknowledges(remote, monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher, 'commit_pcm', MagicMock(side_effect=OSError('archive unavailable')))
    sock = Socket([struct.pack('<I', 103) + b'conversation', struct.pack('<Id', 101, 1000) + b'\x01\x00'])
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert not sock.sent and sock.close_code == 1011


@pytest.mark.parametrize('stage', ['raw-live', 'audio-outbox'])
def test_deletion_during_upload_removes_the_new_generation_before_receipt(remote, monkeypatch, stage):
    deleted = False
    real_upload = Blob.upload_from_string

    def upload(blob, data, **kwargs):
        nonlocal deleted
        if blob.name.startswith(stage + '/'):
            deleted = True
            # Privacy purge sees only objects committed before this upload.
            for existing in remote.blobs.values():
                existing.data = None
        real_upload(blob, data, **kwargs)

    monkeypatch.setattr(Blob, 'upload_from_string', upload)
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: deleted)
    with pytest.raises(storage.audio_packs.CaptureDeleted):
        commit_pcm('owner', b'\x01\x00' * 160, 'conversation', 1000, 16000, 'root', 0)
    assert not any(blob.data is not None for blob in remote.blobs.values())


@pytest.mark.asyncio
async def test_outbox_is_the_sole_custody_kill_and_legacy_live_applies_after_rollback(remote, monkeypatch):
    monkeypatch.setenv('AUDIO_ARCHIVE_LIVE_ENABLED', 'false')
    monkeypatch.delenv('AUDIO_DURABLE_OUTBOX_ENABLED', raising=False)
    durable = LiveAudioArchive(host())
    await durable.append(b'\x01\x00', 'conversation', 1000, 1)
    await durable.close()
    assert durable.host.events
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')
    legacy = LiveAudioArchive(host())
    await legacy.append(b'\x02\x00', 'conversation', 1000, 1)
    await legacy.close()
    assert not legacy.packs and not legacy.host.events


@pytest.mark.asyncio
async def test_v2_projection_trims_replays_while_custody_keeps_every_original(remote, monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    projected = []
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', lambda chunks, *a, **kw: projected.extend(chunks))
    monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda *a: [])
    first = b'\x01\x00' * 16000
    replay = b'\x09\x00' * 8000 + b'\x02\x00' * 8000
    frames = [struct.pack('<I', 103) + b'conversation']
    frames += [
        struct.pack('<Id', 101, start) + data for start, data in ((1000, first), (1000.5, replay), (1000, first))
    ]
    sock = Socket(frames)
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    assert [chunk['data'] for chunk in projected] == [first, replay[16000:]]
    assert [chunk['timestamp'] for chunk in projected] == [1000, 1001]
    receipts = [
        AudioReceipt(**json.loads(frame[4:])['receipt'])
        for frame in sock.sent
        if struct.unpack('<I', frame[:4])[0] == 203
    ]
    assert [read_pcm('owner', receipt) for receipt in receipts] == [first, replay, first]


def _legacy_chunk(remote, start, pcm, name=None, *, is_batch=True):
    extension = 'batch.bin' if is_batch else 'bin'
    blob = remote.blob(f'chunks/owner/conversation/{name or f"{start:.3f}"}.{extension}')
    blob.metadata = {
        **span_blob_metadata({'start': start, 'samples': len(pcm) // 2, 'sample_rate': 16000}),
        'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
    }
    blob.upload_from_string(pcm, if_generation_match=0)


def test_sixty_custody_packs_and_projected_minute_publish_one_audio_file(remote):
    pcm = b'\x01\x00' * 16000
    for sequence in range(60):
        commit_pcm('owner', pcm, 'conversation', 1000 + sequence, 16000, 'root', sequence)
    _legacy_chunk(remote, 1000, pcm * 60, '1000.000-1059.000')
    chunks = storage.list_audio_chunks('owner', 'conversation')
    assert len(chunks) == 1 and chunks[0]['span']['samples'] == 60 * 16000
    files = pusher.conversations_db.create_audio_files_from_chunks('owner', 'conversation')
    assert len(files) == 1 and files[0].duration == 60
    assert storage.download_audio_chunks_and_merge('owner', 'conversation', [1000]) == pcm * 60


def test_partial_raw_overlap_serves_only_uncovered_bytes_and_keeps_legacy_identity(remote):
    parts = [bytes([value, 0]) * 16000 for value in (1, 2, 3)]
    commit_pcm('owner', b''.join(parts), 'conversation', 1000, 16000, 'root', 0)
    accepted_middle = b'\x09\x00' * 16000
    _legacy_chunk(remote, 1001, accepted_middle)
    chunks = storage.list_audio_chunks('owner', 'conversation')
    assert [chunk['timestamp'] for chunk in chunks] == [1000, 1001, 1002]
    files = pusher.conversations_db.create_audio_files_from_chunks('owner', 'conversation')
    assert len(files) == 1 and files[0].duration == 3
    expected = parts[0] + accepted_middle + parts[2]
    assert storage.download_audio_chunks_and_merge('owner', 'conversation', [1000, 1001, 1002]) == expected
    decoded = iter_audio_chunk_pcm('owner', 'conversation', lambda *a: True)
    assert b''.join(pcm for _, pcm in decoded) == expected


@pytest.mark.parametrize('is_batch', [False, True])
def test_submillisecond_raw_fragments_cannot_replace_rounded_legacy_audio(remote, is_batch):
    prefix, original_middle, suffix = b'\x01\x00' * 4, b'\x02\x00' * 16000, b'\x03\x00' * 4
    receipt = commit_pcm('owner', prefix + original_middle + suffix, 'conversation', 1000, 16000, 'root', 0)
    accepted_middle = b'\x09\x00' * 16000
    _legacy_chunk(remote, 1000.00025, accepted_middle, is_batch=is_batch)
    chunks = storage.list_audio_chunks('owner', 'conversation')
    expected = prefix + accepted_middle + suffix
    timestamps = [chunk['timestamp'] for chunk in chunks]

    def same_pcm(actual, wanted):
        assert len(actual) == len(wanted)
        assert hashlib.sha256(actual).digest() == hashlib.sha256(wanted).digest()

    same_pcm(storage.download_audio_chunks_and_merge('owner', 'conversation', timestamps), expected)
    assert timestamps == pytest.approx([1000, 1000.00025, 1001.00025])
    loader = lambda path: storage.download_audio_chunk_pcm('owner', path)
    same_pcm(
        storage.download_audio_chunks_and_merge(
            'owner', 'conversation', timestamps, listed_chunks=chunks, chunk_loader=loader
        ),
        expected,
    )
    same_pcm(b''.join(pcm for _, pcm in iter_audio_chunk_pcm('owner', 'conversation', lambda *a: True)), expected)
    # Previously persisted AudioFiles can still request the millisecond key.
    same_pcm(storage.download_audio_chunks_and_merge('owner', 'conversation', [1000]), accepted_middle)
    assert read_pcm('owner', receipt) == prefix + original_middle + suffix


@pytest.mark.parametrize('is_batch', [False, True])
@pytest.mark.parametrize('raw_start', [1000, 999.99975])
def test_persisted_fingerprinted_audio_file_survives_precise_source_aliases(remote, monkeypatch, is_batch, raw_start):
    from copy import deepcopy
    from utils.other.playback_identity import source_fingerprint, validate_sources, retain_aliases
    from utils.other.raw_audio_read import invalidate_pack_index
    from utils.sync import playback

    accepted = b'\x09\x00' * 16000
    _legacy_chunk(remote, 1000.00025, accepted, is_batch=is_batch)
    invalidate_pack_index(remote, 'owner', 'conversation')
    old_file = pusher.conversations_db.create_audio_files_from_chunks('owner', 'conversation')[0].model_dump()
    assert old_file['chunk_timestamps'] == [1000] and old_file['source_fingerprint']
    count = round((1000.00025 - raw_start) * 16000)
    prefix = b'\x01\x00' * count
    commit_pcm('owner', prefix + b'\x02\x00' * 16000 + b'\x03\x00' * 4, 'conversation', raw_start, 16000, 'root', 0)
    chunks = storage.list_audio_chunks('owner', 'conversation', source_identity=True)
    validate_sources([old_file], chunks)

    class PcmExport:
        def __init__(self, data, **kwargs):
            self.data = data

        def export(self, stream, **kwargs):
            stream.write(self.data)

    # Exercise the actual artifact builder and both source guards; only the
    # final MP3 encoder is replaced with a PCM canary for exact-byte assertions.
    monkeypatch.setattr(playback, 'AudioSegment', PcmExport)
    monkeypatch.setattr(playback, 'list_audio_chunks', storage.list_audio_chunks)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', storage.download_audio_chunks_and_merge)
    built = playback.build_playback_artifact(
        'owner', 'conversation', old_file['chunk_timestamps'], source_fingerprint=old_file['source_fingerprint']
    )
    assert len(built) == len(accepted) and hashlib.sha256(built).digest() == hashlib.sha256(accepted).digest()
    built, _ = playback.build_conversation_playback_artifact(
        'owner', 'conversation', [old_file], 1000, strict_sources=True
    )
    assert len(built) == len(accepted) and hashlib.sha256(built).digest() == hashlib.sha256(accepted).digest()
    raw_prefix = next(chunk for chunk in chunks if chunk['timestamp'] == raw_start)
    built = playback.build_playback_artifact(
        'owner', 'conversation', [raw_start], source_fingerprint=source_fingerprint([raw_prefix])
    )
    assert built == prefix
    current = [
        item.model_dump() for item in pusher.conversations_db.create_audio_files_from_chunks('owner', 'conversation')
    ]
    assert old_file['id'] in retain_aliases(current, [old_file])[0]['legacy_ids']
    replaced = deepcopy(chunks)
    next(chunk for chunk in replaced if chunk['path'].startswith('chunks/'))['generation'] = 18
    with pytest.raises(RuntimeError, match='source manifest changed'):
        validate_sources([old_file], replaced)
    with pytest.raises(RuntimeError, match='source manifest changed'):
        validate_sources([old_file], [chunk for chunk in chunks if not chunk['path'].startswith('chunks/')])
