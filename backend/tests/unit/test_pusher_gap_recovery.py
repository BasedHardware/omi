"""Synthetic relay failure, archive recovery, queue pressure and custody."""

import asyncio
import hashlib
import json
import struct
from unittest.mock import MagicMock

import pytest

from database import record_projection_rebuild as jobs
from utils.other import live_audio_archive, raw_audio_read
from utils.other import relay_archive_recovery as recovery
from utils.other.relay_recovery_metrics import SAMPLES
from utils.other.audio_outbox import commit_pcm
from tests.unit.test_audio_durable_outbox import remote, host  # noqa: F401
from tests.unit.test_raw_live_gapped_packs import build_pack, native_opus, tone, wire, RATE, UID, CID  # noqa: F401
from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, make_session
from tests.unit.test_pusher_runtime_protocol import FakeWebSocket
from routers import pusher
from utils.batch_pipeline import record_projection_rebuild as rebuild


@pytest.fixture(autouse=True)
def clear_proofs():
    recovery._proofs.clear()


@pytest.mark.asyncio
async def test_send_success_without_consumption_recovers_from_original(remote):
    h = host()
    archive = live_audio_archive.LiveAudioArchive(h)
    pcm = tone(320, 123)
    await archive.append(pcm, 'conv-1', 1000, 320, decoded=pcm)
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 640})
    session.pusher_ws, session.pusher_connected = ws, True
    session.audio_bytes_send(pcm, 1000.02, conversation_id='conv-1', start_wall=1000)
    await session._audio_bytes_flush()
    assert session.audio_total_size == 0  # Send success is not custody.
    assert any(struct.unpack('<I', f[:4])[0] == 101 for f in ws.sent)
    assert not list(remote.list_blobs(prefix=f'raw-live/{UID}/conv-1/'))
    await archive.close()
    jobs.mark_due.assert_called_once_with(UID, 'conv-1')
    recovered = recovery.validated_uncovered_packs(remote, UID, 'conv-1', [])
    assert sum(p['span']['samples'] for p in recovered) == 320
    assert raw_audio_read.read_pack(remote, recovered[0]['path'], UID) == pcm
    assert len(h.events) == 1
    assert recovery.validated_uncovered_packs(remote, UID, 'conv-1', recovered) == []


@pytest.mark.asyncio
async def test_marker_failure_retains_pack_and_withholds_phone_receipt(remote, monkeypatch):
    h = host()
    archive = live_audio_archive.LiveAudioArchive(h)
    pcm = tone(320, 44)
    await archive.append(pcm, CID, 1000, 320, decoded=pcm)
    pack = archive.packs[0]
    marker = MagicMock(side_effect=OSError('synthetic marker outage'))
    monkeypatch.setattr(jobs, 'mark_due', marker)
    with pytest.raises(OSError):
        await archive.close()
    assert archive.uncommitted[id(pack)][0] is pack
    assert bytes(pack.data) == pcm
    assert h.events == []
    paths = set(remote.blobs)
    marker.side_effect = None
    await archive.ensure_durable()
    assert not archive.uncommitted
    assert set(remote.blobs) == paths  # Retry preserves generation/range identity.
    assert len(h.events) == 1


@pytest.mark.asyncio
async def test_kill_switch_preserves_legacy_archive_receipt(remote, monkeypatch):
    monkeypatch.setenv('PUSHER_PROJECTION_DEBT_DURABLE_ENABLED', 'off')
    h = host()
    archive = live_audio_archive.LiveAudioArchive(h)
    await archive.append(tone(320, 1), CID, 1000, 320)
    await archive.close()
    jobs.mark_due.assert_not_called()
    assert len(h.events) == 1


@pytest.mark.asyncio
async def test_cancel_after_media_commit_retains_original_and_withholds_phone_receipt(remote, monkeypatch):
    h = host()
    archive = live_audio_archive.LiveAudioArchive(h)
    await archive.append(tone(320, 4), CID, 1000, 320)
    entered, never = asyncio.Event(), asyncio.Event()
    original = live_audio_archive.run_blocking
    blocked = [True]

    async def dispatch(executor, function, *args, **kwargs):
        if function is jobs.mark_due and blocked[0]:
            entered.set()
            await never.wait()
        return await original(executor, function, *args, **kwargs)

    monkeypatch.setattr(live_audio_archive, 'run_blocking', dispatch)
    closing = asyncio.create_task(archive.close())
    try:
        await asyncio.wait_for(entered.wait(), 3)
        assert list(remote.list_blobs(prefix=f'raw-live/{UID}/{CID}/'))
        for task in tuple(archive.inflight):
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert archive.uncommitted and h.events == []
        blocked[0] = False
        await archive.ensure_durable()
        assert not archive.uncommitted and len(h.events) == 1
    finally:
        if not closing.done():
            closing.cancel()
        await asyncio.gather(closing, return_exceptions=True)


def test_reordered_overlapping_receipts_recover_sample_union_once(remote, monkeypatch):
    wire(remote, monkeypatch)
    original = tone(160, 1) + tone(160, 2) + tone(160, 3)
    commit_pcm(UID, original[320:], CID, 1000.01, RATE, 'new-session', 0)
    commit_pcm(UID, original, CID, 1000, RATE, 'original-session', 0)
    chunks = [{'timestamp': 1000.0, 'span': {'start': 1000.0, 'samples': 160, 'sample_rate': RATE}}]
    recovered = recovery.validated_uncovered_packs(remote, UID, CID, chunks)
    assert sum(p['span']['samples'] for p in recovered) == 320
    assert [(p['timestamp'], p['raw_end']) for p in recovered] == [(1000.01, 1000.03)]
    assert recovery.validated_uncovered_packs(remote, UID, CID, [*chunks, *recovered]) == []


def test_gapped_opus_frames_do_not_fabricate_silence(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    build_pack(remote, [(1000, tone(320, 4)), (1032, tone(320, 8))])
    recovered = recovery.validated_uncovered_packs(remote, UID, CID, [])
    assert [(p['timestamp'], p['span']['samples']) for p in recovered] == [(1000, 320), (1032, 320)]


def test_opus_frame_hash_is_verified_even_when_pack_hash_matches(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    receipt, _, _, _ = build_pack(remote, [(1000, tone(320, 4))])
    manifest = remote.blob(receipt.manifest_path)
    value = json.loads(manifest.data)
    value['frames'][0]['sha256'] = '0' * 64
    manifest.data = json.dumps(value).encode()
    manifest.stored_metadata['sha256'] = hashlib.sha256(manifest.data).hexdigest()
    with pytest.raises(ValueError, match='capture decode failed'):
        recovery.validated_uncovered_packs(remote, UID, CID, [])


def test_decode_bound_retains_progress_as_metadata_without_pcm(remote, monkeypatch):
    wire(remote, monkeypatch)
    for index in range(2):
        receipt = commit_pcm(UID, tone(320, index + 1), CID, 1000 + index, RATE, str(index), 0)
        remote.blob(receipt.path).metageneration = 1
    monkeypatch.setattr(recovery, 'MAX_NEW_PACKS', 1)
    with pytest.raises(TimeoutError, match='pack budget'):
        recovery.validated_uncovered_packs(remote, UID, CID, [])
    assert len(recovery._proofs) == 1
    assert all(not isinstance(value, bytes) for value in recovery._proofs.values())
    assert sum(p['span']['samples'] for p in recovery.validated_uncovered_packs(remote, UID, CID, [])) == 640


@pytest.mark.parametrize('failure', ['hash', 'manifest', 'generation', 'bounds'])
def test_proof_failure_never_publishes_or_deletes(remote, monkeypatch, failure):
    wire(remote, monkeypatch)
    receipt = commit_pcm(UID, tone(320, 4), CID, 1000, RATE, 'session', 0)
    media = remote.blob(receipt.path)
    if failure == 'hash':
        media.data = b'\0' * len(media.data)
    elif failure == 'manifest':
        remote.blob(receipt.manifest_path).data = None
    elif failure == 'generation':
        media.stored_metadata['sha256'] = 'a' * 64
    else:
        monkeypatch.setattr(recovery, 'MAX_DECODED_BYTES', 1)
    before = SAMPLES.labels(stage='recovered')._value.get()
    with pytest.raises((ValueError, TimeoutError)):
        recovery.validated_uncovered_packs(remote, UID, CID, [])
    assert SAMPLES.labels(stage='recovered')._value.get() == before
    assert media.data is not None


def test_required_archive_batch_listing_is_fresh_and_bounded():
    list_raw = MagicMock(return_value=[])
    assert (
        raw_audio_read.raw_chunks_for_listing(
            object(), UID, CID, [], enabled=True, require_archive=True, max_count=4096, list_raw=list_raw
        )
        == []
    )
    assert list_raw.call_args.kwargs['fresh'] is True
    assert list_raw.call_args.kwargs['max_count'] == 4096


def test_privacy_hold_refuses_before_decoding(monkeypatch):
    monkeypatch.setattr(rebuild, 'projection_owner_gone', lambda *args: False)
    monkeypatch.setattr(jobs, 'preflight_projection', lambda *args: False)
    discover = MagicMock(side_effect=AssertionError('must not read audio'))
    monkeypatch.setattr(rebuild, 'discover', discover)
    assert rebuild.rebuild(UID, CID) is None
    discover.assert_not_called()


def test_cached_decode_proof_still_requires_current_manifest(remote, monkeypatch):
    wire(remote, monkeypatch)
    receipt = commit_pcm(UID, tone(320, 4), CID, 1000, RATE, 'session', 0)
    remote.blob(receipt.path).metageneration = 1
    assert recovery.validated_uncovered_packs(remote, UID, CID, [])
    assert len(recovery._proofs) == 1
    remote.blob(receipt.manifest_path).data = None
    with pytest.raises(ValueError, match='unique custody manifest'):
        recovery.validated_uncovered_packs(remote, UID, CID, [])


def test_ambiguous_manifests_and_foreign_owner_fail_closed(remote, monkeypatch):
    wire(remote, monkeypatch)
    receipt = commit_pcm(UID, tone(320, 4), CID, 1000, RATE, 'session', 0)
    manifest = remote.blob(receipt.manifest_path)
    duplicate = remote.blob(receipt.manifest_path + '-duplicate')
    duplicate.upload_from_string(manifest.data, if_generation_match=0)
    duplicate.metadata = duplicate.stored_metadata = dict(manifest.metadata)
    with pytest.raises(ValueError, match='unique custody manifest'):
        recovery.validated_uncovered_packs(remote, UID, CID, [])
    foreign = {
        'path': 'raw-live/other/conversation/pack',
        'timestamp': 1000,
        'span': {'start': 1000, 'samples': 320, 'sample_rate': RATE},
        'raw_end': 1000.02,
    }
    monkeypatch.setattr(raw_audio_read, 'list_packs', lambda *a, **kw: [foreign])
    with pytest.raises(ValueError, match='owner mismatch'):
        recovery.validated_uncovered_packs(remote, UID, CID, [])


@pytest.fixture
def app_socket(monkeypatch):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)


@pytest.mark.asyncio
async def test_optional_queue_full_drops_oldest_without_stalling_capture(app_socket, monkeypatch):
    """A stalled app/webhook consumer must neither stall the receive loop nor close the socket.

    Prod 2026-11-16: a full optional audio_bytes queue raised AudioBackpressure and closed
    live capture sockets with 1011. Optional audio is best-effort: drop the oldest item.
    """
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: True)
    monkeypatch.setattr(pusher, 'AUDIO_BYTES_QUEUE_WARN_SIZE', 2)
    entered, release = asyncio.Event(), asyncio.Event()
    processed = []

    async def blocked_app(uid, rate, data):
        processed.append(bytes(data))
        entered.set()
        await release.wait()

    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', blocked_app)
    frames = [struct.pack('<Id', 101, 1000 + i * 5) + tone(8000 * 5, i + 1) for i in range(6)]
    socket = FakeWebSocket(frames)
    task = asyncio.create_task(pusher._websocket_util_trigger(socket, UID, 8000))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        # The receive loop keeps consuming frames while the consumer is blocked.
        for _ in range(200):
            if not socket.frames:
                break
            await asyncio.sleep(0.01)
        assert not socket.frames
        assert socket.close_code in (None, 1000)
        release.set()
        await asyncio.wait_for(task, 5)
        assert socket.close_code == 1000
        payloads = [frame[12:] for frame in frames]
        # First item went straight to the consumer; later ones were best-effort.
        assert processed[0] == payloads[0]
        assert len(processed) < len(payloads)
        assert all(item in payloads for item in processed)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_failed_receiver_closes_before_drain(app_socket, monkeypatch):
    order = []

    class FailedSocket(FakeWebSocket):
        async def receive_bytes(self):
            raise OSError('synthetic failure')

        async def close(self, code=1000, reason=None):
            order.append('close')
            await super().close(code, reason)

    original_wait = pusher.asyncio.wait

    async def wait(*args, **kwargs):
        if kwargs.get('timeout') == pusher.BG_DRAIN_TIMEOUT:
            order.append('drain')
            assert order[0] == 'close'
        return await original_wait(*args, **kwargs)

    monkeypatch.setattr(pusher.asyncio, 'wait', wait)
    socket = FailedSocket()
    await asyncio.wait_for(pusher._websocket_util_trigger(socket, UID, 8000), 5)
    assert socket.close_code == 1011 and order == ['close', 'drain']
