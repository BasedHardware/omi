"""Round-4 acceptance: ambiguous-send exactly-once, verified consumer inventory,
and the OFF saved-sync rebuild path.

These tests exercise the real listen→pusher→storage stack and the real storage
helpers; only GCS itself is doubled (the in-memory bucket enforces generation
preconditions). The original reviewer probes assert the buggy behavior and are
preserved unmodified under .agent-brief; these assert the fixed behavior.

Setting OMI_ROUND4_RED=1 loads the pre-fix session/storage/stage modules from
OMI_ROUND4_RED_SHA (default 07acece3fd) so the same assertions run red.
"""

import asyncio
import os
import struct
import subprocess
import sys
import types
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from websockets.exceptions import ConnectionClosedError

from models.audio_file import AudioFile, ChunkSpan
from tests.unit import test_conversation_speaker_resolution_stage as stagemod
from tests.unit import test_listen_audio_timeline_stack as f
from tests.unit.utils import test_listen_pusher_session as session_mod
from utils import encryption
from utils.other import storage as storage_module
from utils.other.audio_chunks import iter_audio_chunk_pcm


@pytest.fixture
def env(monkeypatch):
    return stagemod.env.__wrapped__(monkeypatch)


ROUND4_RED_ENV = 'OMI_ROUND4_RED'
ROUND4_RED_SHA = os.environ.get(ROUND4_RED_ENV + '_SHA', '07acece3fd')


def _historical(name, revision, path):
    source = subprocess.check_output(
        ['git', 'show', f'{revision}:{path}'], cwd=Path(__file__).resolve().parents[2], text=True
    )
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, path, 'exec'), module.__dict__)
    return module


def _optional_historical(name, revision, path):
    try:
        return _historical(name, revision, path)
    except subprocess.CalledProcessError as error:
        pytest.skip(f'historical source {revision}:{path} unavailable: {error}')


def _red_enabled():
    return os.environ.get(ROUND4_RED_ENV) == '1'


@pytest.fixture
def round4_session():
    if not _red_enabled():
        return None
    return _optional_historical('r4_red_session', ROUND4_RED_SHA, 'backend/utils/listen_pusher_session.py')


@pytest.fixture
def round4_storage(monkeypatch):
    if not _red_enabled():
        return None
    old = _optional_historical('r4_red_storage', ROUND4_RED_SHA, 'backend/utils/other/storage.py')
    monkeypatch.setattr(old, '_get_storage_client', lambda: storage_module._get_storage_client())
    monkeypatch.setattr(old, 'private_cloud_sync_bucket', storage_module.private_cloud_sync_bucket)
    return old


@pytest.fixture
def round4_stage(monkeypatch, env):
    if not _red_enabled():
        return None
    store, diarizer = env
    old_stage = _optional_historical(
        'r4_red_stage', ROUND4_RED_SHA, 'backend/utils/conversations/speaker_resolution.py'
    )
    old_placement = _optional_historical(
        'r4_red_placement', ROUND4_RED_SHA, 'backend/utils/conversations/audio_placement.py'
    )
    monkeypatch.setattr(old_stage, 'locate', old_placement.locate)
    monkeypatch.setattr(old_stage, 'AudioPlacement', old_placement.AudioPlacement)
    stagemod._patch_stage_deps(monkeypatch, old_stage, store, diarizer)
    monkeypatch.setattr(
        old_stage, 'iter_audio_chunk_pcm', lambda *args, **kwargs: stagemod.stage.iter_audio_chunk_pcm(*args, **kwargs)
    )
    monkeypatch.setattr(stagemod.stage, 'resolve_speakers_for_processing', old_stage.resolve_speakers_for_processing)
    return old_stage


def _uploader(storage, chunks, uid, cid, level, sample_rate):
    if 'reconcile_audio_chunk_prefix' in dir(storage):
        return storage.upload_audio_chunks_batch(chunks, uid, cid, level, sample_rate=sample_rate)
    return storage.upload_audio_chunks_batch(chunks, uid, cid, level)


def _stored_pcm(bucket, uid, chunks):
    out = b''
    for chunk in chunks:
        data = bucket.blob(chunk['path']).download_as_bytes()
        if chunk['path'].endswith('.enc'):
            data = encryption.decrypt_audio_file(data, uid)
        out += data
    return out


async def _uncertain_send_run(mp, *, spans, protection, session_module=None, peer=None, storage_peer=None):
    gcs = f.gcs.__wrapped__(mp)
    f.pusher_env.__wrapped__(mp)
    mp.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    if session_module is not None:
        mp.setattr(f, 'ListenPusherSession', session_module.ListenPusherSession)
        mp.setattr(f, 'ListenPusherSessionDeps', session_module.ListenPusherSessionDeps)
        mp.setattr(
            f,
            'ListenPusherSessionConfig',
            lambda **kw: session_module.ListenPusherSessionConfig(
                **{k: v for k, v in kw.items() if k in session_module.ListenPusherSessionConfig.__dataclass_fields__}
            ),
        )
    stack = f._Stack(mp, v2=False, spans=spans, conversation_id=f.CONV1)
    mp.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
    peer = peer or f.pusher
    if storage_peer is not None:
        mp.setattr(storage_peer, '_get_storage_client', lambda: storage_module._get_storage_client())
        mp.setattr(storage_peer, 'private_cloud_sync_bucket', storage_module.private_cloud_sync_bucket)
        old_upload = storage_peer.upload_audio_chunks_batch

        def compat_upload(chunks, uid, cid, level, sample_rate=None):
            if 'reconcile_audio_chunk_prefix' in dir(storage_peer):
                return old_upload(chunks, uid, cid, level, sample_rate=sample_rate)
            return old_upload(chunks, uid, cid, level)

        mp.setattr(peer, 'upload_audio_chunks_batch', compat_upload)
    try:
        stack.build_session()
        stack.start_pusher_server(peer=peer)
        await stack.session.connect()
        socket = stack.session.pusher_ws
        original_send = socket.send

        async def delivered_then_closed(data):
            await original_send(data)
            if struct.unpack('<I', data[:4])[0] == 101:
                raise ConnectionClosedError(None, None)

        socket.send = delivered_then_closed
        stack.session.deps.is_active = lambda: False
        a, b = f._phrase(1, 1), f._phrase(2, 1)
        stack.session.audio_bytes_send(a, f.T0 + 1, conversation_id=f.CONV1, start_wall=f.T0 if spans else None)
        await stack.session._audio_bytes_flush()
        await stack.stop_pusher_server()
        stack.session.audio_bytes_send(
            b, f.T0 + (2 if spans else 61), conversation_id=f.CONV1, start_wall=f.T0 + 1 if spans else None
        )
        stack.start_pusher_server(peer=peer)
        await stack.session.connect()
        await stack.session._audio_bytes_flush()
        await stack.stop_pusher_server()
        chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
        expected_suffix = '.batch.enc' if protection == 'enhanced' else '.batch.bin'
        assert all(chunk['path'].endswith(expected_suffix) for chunk in chunks)
        bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
        return _stored_pcm(bucket, f.UID, chunks), chunks, stack
    finally:
        if stack.session.reconnect_task:
            stack.session.reconnect_task.cancel()
        stack.restore()


@pytest.mark.parametrize('spans', [False, True])
@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
async def test_ambiguous_send_stores_exactly_once(monkeypatch, spans, protection, round4_session, round4_storage):
    a, b = f._phrase(1, 1), f._phrase(2, 1)
    actual, chunks, stack = await _uncertain_send_run(
        monkeypatch,
        spans=spans,
        protection=protection,
        session_module=round4_session,
        storage_peer=round4_storage,
    )
    assert actual == a + b, (spans, protection, [c['path'] for c in chunks])
    assert f.pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc.call_count == 0
    if spans:
        spans_seen = sorted(c['span']['start'] for c in chunks if c.get('span'))
        assert len(spans_seen) == 2
        first = [c for c in chunks if c.get('span') and c['span']['start'] == spans_seen[0]][0]
        tail = [c for c in chunks if c.get('span') and c['span']['start'] == spans_seen[1]][0]
        assert abs(tail['span']['start'] - (first['span']['start'] + first['span']['samples'] / f.RATE)) < 0.001


@pytest.fixture(scope='module')
def old_main_pusher_module():
    return _optional_historical('r4_main_pusher', 'origin/main', 'backend/routers/pusher.py')


@pytest.fixture(scope='module')
def old_main_storage_module():
    return _optional_historical('r4_main_storage', 'origin/main', 'backend/utils/other/storage.py')


@pytest.fixture(scope='module')
def literal_625_session_module():
    return _optional_historical('r4_625_session', '6254862141', 'backend/utils/listen_pusher_session.py')


def _old_peer_wiring(mp, old_pusher, old_storage):
    f.pusher_env.__wrapped__(mp)
    for attr in (
        'get_audio_bytes_webhook_seconds',
        'is_audio_bytes_app_enabled',
        'is_audio_merge_dispatch_enabled',
        'schedule_person_voice_learning_retry',
        'run_authorized_person_learning',
        'PUSHER_ACTIVE_WS_CONNECTIONS',
        'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS',
    ):
        mp.setattr(old_pusher, attr, getattr(f.pusher, attr))
    if old_storage is not None:
        mp.setattr(old_storage, '_get_storage_client', lambda: storage_module._get_storage_client())
        mp.setattr(old_storage, 'private_cloud_sync_bucket', storage_module.private_cloud_sync_bucket)
        mp.setattr(old_pusher, 'upload_audio_chunks_batch', old_storage.upload_audio_chunks_batch)


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
async def test_ambiguous_send_new_listen_old_peer_old_storage(
    monkeypatch, protection, old_main_pusher_module, old_main_storage_module
):
    a, b = f._phrase(1, 1), f._phrase(2, 1)
    _old_peer_wiring(monkeypatch, old_main_pusher_module, old_main_storage_module)
    actual, chunks, _ = await _uncertain_send_run(
        monkeypatch, spans=False, protection=protection, peer=old_main_pusher_module
    )
    assert actual == a + b


@pytest.mark.parametrize('old_peer', [True, False])
async def test_ambiguous_send_literal625_listen_residual_double_store(
    monkeypatch, old_peer, literal_625_session_module, old_main_pusher_module, old_main_storage_module
):
    a, b = f._phrase(1, 1), f._phrase(2, 1)
    _old_peer_wiring(monkeypatch, old_main_pusher_module, old_main_storage_module)
    actual, chunks, _ = await _uncertain_send_run(
        monkeypatch,
        spans=False,
        protection='standard',
        session_module=literal_625_session_module,
        peer=old_main_pusher_module if old_peer else None,
    )
    assert actual == a + a + b


def _span_of(data, start):
    return {'start': start, 'samples': len(data) // 2, 'sample_rate': f.RATE}


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_reconciles_rebatched_prefix(monkeypatch, protection, round4_storage):
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    a, b = f._phrase(1, 1), f._phrase(2, 1)
    t0 = f.T0
    _uploader(storage, [{'data': a, 'timestamp': t0, 'span': _span_of(a, t0)}], f.UID, f.CONV1, protection, f.RATE)
    _uploader(
        storage,
        [{'data': a + b, 'timestamp': t0, 'span': _span_of(a + b, t0)}],
        f.UID,
        f.CONV1,
        protection,
        f.RATE,
    )
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 2
    actual = _stored_pcm(gcs.bucket(storage_module.private_cloud_sync_bucket), f.UID, chunks)
    assert actual == a + b
    assert abs(chunks[1]['span']['start'] - (t0 + len(a) / (f.RATE * 2))) < 0.001


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_reconciles_multiple_committed_prefixes(monkeypatch, protection, round4_storage):
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    a, b, c = f._phrase(1, 1), f._phrase(2, 1), f._phrase(3, 1)
    t0 = f.T0
    t1 = t0 + len(a) / (f.RATE * 2)
    _uploader(storage, [{'data': a, 'timestamp': t0, 'span': _span_of(a, t0)}], f.UID, f.CONV1, protection, f.RATE)
    _uploader(storage, [{'data': b, 'timestamp': t1, 'span': _span_of(b, t1)}], f.UID, f.CONV1, protection, f.RATE)
    _uploader(
        storage,
        [{'data': a + b + c, 'timestamp': t0, 'span': _span_of(a + b + c, t0)}],
        f.UID,
        f.CONV1,
        protection,
        f.RATE,
    )
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 3
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    assert _stored_pcm(bucket, f.UID, chunks) == a + b + c
    _uploader(
        storage,
        [{'data': a + b + c, 'timestamp': t0, 'span': _span_of(a + b + c, t0)}],
        f.UID,
        f.CONV1,
        protection,
        f.RATE,
    )
    assert len(storage_module.list_audio_chunks(f.UID, f.CONV1)) == 3


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_legacy_anchor_reconciles(monkeypatch, protection, round4_storage):
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    a, b = f._phrase(1, 1), f._phrase(2, 1)
    t0 = f.T0
    _uploader(storage, [{'data': a, 'timestamp': t0}], f.UID, f.CONV1, protection, f.RATE)
    _uploader(storage, [{'data': a + b, 'timestamp': t0}], f.UID, f.CONV1, protection, f.RATE)
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 2
    assert _stored_pcm(gcs.bucket(storage_module.private_cloud_sync_bucket), f.UID, chunks) == a + b


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_full_replay_is_noop(monkeypatch, protection, round4_storage):
    f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    a = f._phrase(1, 1)
    t0 = f.T0
    _uploader(storage, [{'data': a, 'timestamp': t0, 'span': _span_of(a, t0)}], f.UID, f.CONV1, protection, f.RATE)
    _uploader(storage, [{'data': a, 'timestamp': t0, 'span': _span_of(a, t0)}], f.UID, f.CONV1, protection, f.RATE)
    assert len(storage_module.list_audio_chunks(f.UID, f.CONV1)) == 1


def test_uploader_conflicting_prefix_refuses(monkeypatch):
    gcs = f.gcs.__wrapped__(monkeypatch)
    a, other = f._phrase(1, 1), f._phrase(9, 1)
    t0 = f.T0
    storage_module.upload_audio_chunks_batch(
        [{'data': a, 'timestamp': t0, 'span': _span_of(a, t0)}], f.UID, f.CONV1, 'standard', sample_rate=f.RATE
    )
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    before = bucket.blob(storage_module.list_audio_chunks(f.UID, f.CONV1)[0]['path']).download_as_bytes()
    with pytest.raises(ValueError):
        storage_module.upload_audio_chunks_batch(
            [{'data': other + b'_x', 'timestamp': t0, 'span': _span_of(other + b'_x', t0)}],
            f.UID,
            f.CONV1,
            'standard',
            sample_rate=f.RATE,
        )
    after = bucket.blob(storage_module.list_audio_chunks(f.UID, f.CONV1)[0]['path']).download_as_bytes()
    assert before == after
    assert len(storage_module.list_audio_chunks(f.UID, f.CONV1)) == 1


def test_uploader_legacy_conflicting_prefix_refuses(monkeypatch):
    gcs = f.gcs.__wrapped__(monkeypatch)
    a, other = f._phrase(1, 1), f._phrase(9, 1)
    t0 = f.T0
    storage_module.upload_audio_chunks_batch(
        [{'data': a, 'timestamp': t0}], f.UID, f.CONV1, 'standard', sample_rate=f.RATE
    )
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    before = bucket.blob(storage_module.list_audio_chunks(f.UID, f.CONV1)[0]['path']).download_as_bytes()
    with pytest.raises(ValueError):
        storage_module.upload_audio_chunks_batch(
            [{'data': other, 'timestamp': t0}], f.UID, f.CONV1, 'standard', sample_rate=f.RATE
        )
    after = bucket.blob(storage_module.list_audio_chunks(f.UID, f.CONV1)[0]['path']).download_as_bytes()
    assert before == after
    assert len(storage_module.list_audio_chunks(f.UID, f.CONV1)) == 1


SR = stagemod.SR
ORIGIN = round(stagemod.STARTED.timestamp(), 3)


def _voice_pcm(plan_seconds_voice):
    total = int(sum(d for d, _ in plan_seconds_voice) * SR)
    pcm = np.zeros(total, dtype=np.int16)
    position = 0
    for duration, voice in plan_seconds_voice:
        count = int(duration * SR)
        if voice is not None:
            pcm[position : position + count] = (voice + 1) * 1000
        position += count
    return pcm.tobytes()


def _write_span_object(bucket, path, start, pcm):
    blob = bucket.blob(path)
    blob.metadata = storage_module.span_blob_metadata({'start': start, 'samples': len(pcm) // 2, 'sample_rate': SR})
    blob._store(pcm)
    return blob


def _capture_conversation():
    conv = stagemod._conversation([0, 1], scopes=['old-listen:0', 'new-listen:0'])
    for i, s in enumerate(conv.transcript_segments):
        s.audio_capture_start = ORIGIN + 4 + i * 4
        s.audio_capture_end = s.audio_capture_start + 3.8
    return conv


def _segment_snapshot(conv):
    return [(s.id, s.speaker_id, s.speaker_id_scope) for s in conv.transcript_segments]


def _inventory_base(mp):
    store, diarizer = stagemod.env.__wrapped__(mp)
    mp.setenv('AUDIO_TIMELINE_SPANS', 'true')
    mp.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    mp.setenv('AUDIO_TIMELINE_V2', 'false')
    client = f.FakeStorageClient()
    mp.setattr(storage_module, '_get_storage_client', lambda: client)
    mp.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: 'standard')
    mp.setattr(stagemod.stage, 'iter_audio_chunk_pcm', iter_audio_chunk_pcm)
    lists = []
    real_list = storage_module.list_audio_chunks

    def counted(*args, **kwargs):
        lists.append(1)
        return real_list(*args, **kwargs)

    mp.setattr(storage_module, 'list_audio_chunks', counted)
    bucket = client.bucket(storage_module.private_cloud_sync_bucket)
    return store, diarizer, lists, bucket


def _resolve_stage(mp, conv, store, diarizer, round4_stage):
    target = round4_stage if round4_stage else stagemod.stage
    if round4_stage is not None:
        stagemod._patch_stage_deps(mp, round4_stage, store, diarizer)
    target.resolve_speakers_for_processing('u1', conv)


def test_matching_inventory_resolves_with_single_listing(round4_stage):
    mp = pytest.MonkeyPatch()
    try:
        store, diarizer, lists, bucket = _inventory_base(mp)
        conv = _capture_conversation()
        pcm = _voice_pcm([(4, None), (3.8, 0), (0.2, None), (3.8, 1), (0.2, None)])
        _write_span_object(bucket, f'chunks/u1/c1/{ORIGIN:.3f}.batch.bin', ORIGIN, pcm)
        conv.audio_files = [
            AudioFile(
                id='af',
                uid='u1',
                conversation_id=conv.id,
                chunk_timestamps=[ORIGIN],
                duration=12,
                chunk_spans=[ChunkSpan(start=ORIGIN, end=ORIGIN + 12)],
            )
        ]
        _resolve_stage(mp, conv, store, diarizer, round4_stage)
        assert conv.speaker_resolution.status == 'resolved'
        assert diarizer.calls == 2
        assert len(lists) == 1
        cache = stagemod.stage.decode_cache(store.get('c1'))
        assert [int(np.argmax(v)) for _, v in cache.values()] == [0, 1]
    finally:
        mp.undo()


def test_late_overlapping_blob_inserted_before_inventory_refuses(round4_stage):
    mp = pytest.MonkeyPatch()
    try:
        store, diarizer, lists, bucket = _inventory_base(mp)
        conv = _capture_conversation()
        pcm = _voice_pcm([(4, None), (3.8, 0), (0.2, None), (3.8, 1), (0.2, None)])
        _write_span_object(bucket, f'chunks/u1/c1/{ORIGIN:.3f}.batch.bin', ORIGIN, pcm)
        conv.audio_files = [
            AudioFile(
                id='af',
                uid='u1',
                conversation_id=conv.id,
                chunk_timestamps=[ORIGIN],
                duration=12,
                chunk_spans=[ChunkSpan(start=ORIGIN, end=ORIGIN + 12)],
            )
        ]
        snapshot = _segment_snapshot(conv)
        real_list = storage_module.list_audio_chunks
        injected = []

        def injecting_list(*args, **kwargs):
            if not injected:
                injected.append(1)
                late = ORIGIN + 3
                _write_span_object(bucket, f'chunks/u1/c1/{late:.3f}.batch.bin', late, _voice_pcm([(10, 1)]))
            return real_list(*args, **kwargs)

        mp.setattr(storage_module, 'list_audio_chunks', injecting_list)
        _resolve_stage(mp, conv, store, diarizer, round4_stage)
        assert diarizer.calls == 0
        assert store.get('c1') is None
        assert conv.speaker_resolution.status != 'resolved'
        assert _segment_snapshot(conv) == snapshot
    finally:
        mp.undo()


def test_inventory_missing_generation_refuses(round4_stage):
    mp = pytest.MonkeyPatch()
    try:
        store, diarizer, lists, bucket = _inventory_base(mp)
        conv = _capture_conversation()
        pcm = _voice_pcm([(4, None), (3.8, 0), (0.2, None), (3.8, 1), (0.2, None)])
        _write_span_object(bucket, f'chunks/u1/c1/{ORIGIN:.3f}.batch.bin', ORIGIN, pcm)
        conv.audio_files = [
            AudioFile(
                id='af',
                uid='u1',
                conversation_id=conv.id,
                chunk_timestamps=[ORIGIN],
                duration=12,
                chunk_spans=[ChunkSpan(start=ORIGIN, end=ORIGIN + 12)],
            )
        ]
        real_list = storage_module.list_audio_chunks

        def strip_generation(*args, **kwargs):
            return [{k: v for k, v in c.items() if k != 'generation'} for c in real_list(*args, **kwargs)]

        mp.setattr(storage_module, 'list_audio_chunks', strip_generation)
        _resolve_stage(mp, conv, store, diarizer, round4_stage)
        assert diarizer.calls == 0
        assert store.get('c1') is None
        assert conv.speaker_resolution.status != 'resolved'
    finally:
        mp.undo()


def test_inventory_duplicate_same_extent_refuses(round4_stage):
    mp = pytest.MonkeyPatch()
    try:
        store, diarizer, lists, bucket = _inventory_base(mp)
        conv = _capture_conversation()
        pcm = _voice_pcm([(4, None), (3.8, 0), (0.2, None), (3.8, 1), (0.2, None)])
        _write_span_object(bucket, f'chunks/u1/c1/{ORIGIN:.3f}.batch.bin', ORIGIN, pcm)
        _write_span_object(bucket, f'chunks/u1/c1/{ORIGIN + 0.001:.3f}.batch.bin', ORIGIN, pcm)
        conv.audio_files = [
            AudioFile(
                id='af',
                uid='u1',
                conversation_id=conv.id,
                chunk_timestamps=[ORIGIN, ORIGIN + 0.001],
                duration=12,
                chunk_spans=[
                    ChunkSpan(start=ORIGIN, end=ORIGIN + 12),
                    ChunkSpan(start=ORIGIN, end=ORIGIN + 12),
                ],
            )
        ]
        _resolve_stage(mp, conv, store, diarizer, round4_stage)
        assert diarizer.calls == 0
        assert store.get('c1') is None
        assert conv.speaker_resolution.status != 'resolved'
    finally:
        mp.undo()


def test_inventory_overlapping_spanless_objects_refuse(round4_stage):
    mp = pytest.MonkeyPatch()
    try:
        store, diarizer, lists, bucket = _inventory_base(mp)
        conv = _capture_conversation()
        pcm = _voice_pcm([(4, None), (3.8, 0), (0.2, None), (3.8, 1), (0.2, None)])
        bucket.blob(f'chunks/u1/c1/{ORIGIN:.3f}.batch.bin')._store(pcm)
        bucket.blob(f'chunks/u1/c1/{ORIGIN + 6:.3f}.batch.bin')._store(pcm[: 6 * SR * 2])
        conv.audio_files = [
            AudioFile(
                id='af',
                uid='u1',
                conversation_id=conv.id,
                chunk_timestamps=[ORIGIN, ORIGIN + 6],
                duration=12,
            )
        ]
        _resolve_stage(mp, conv, store, diarizer, round4_stage)
        assert diarizer.calls == 0
        assert store.get('c1') is None
        assert conv.speaker_resolution.status != 'resolved'
    finally:
        mp.undo()


@pytest.mark.parametrize('mutate_index', [0, 1])
def test_inventory_generation_mutation_before_prefetch_refuses(mutate_index, round4_stage):
    mp = pytest.MonkeyPatch()
    try:
        store, diarizer, lists, bucket = _inventory_base(mp)
        conv = _capture_conversation()
        pcm = _voice_pcm([(4, None), (3.8, 0), (0.2, None), (3.8, 1), (0.2, None)])
        tail_pcm = _voice_pcm([(1, 1)])
        _write_span_object(bucket, f'chunks/u1/c1/{ORIGIN:.3f}.batch.bin', ORIGIN, pcm)
        _write_span_object(bucket, f'chunks/u1/c1/{ORIGIN + 12:.3f}.batch.bin', ORIGIN + 12, tail_pcm)
        conv.audio_files = [
            AudioFile(
                id='af',
                uid='u1',
                conversation_id=conv.id,
                chunk_timestamps=[ORIGIN, ORIGIN + 12],
                duration=13,
                chunk_spans=[
                    ChunkSpan(start=ORIGIN, end=ORIGIN + 12),
                    ChunkSpan(start=ORIGIN + 12, end=ORIGIN + 13),
                ],
            )
        ]
        real_list = storage_module.list_audio_chunks

        def mutate_after_list(*args, **kwargs):
            listed = real_list(*args, **kwargs)
            target = sorted(listed, key=lambda c: c['timestamp'])[mutate_index]
            bucket.blob(target['path'])._store(_voice_pcm([(2, 1)]))
            return listed

        mp.setattr(storage_module, 'list_audio_chunks', mutate_after_list)
        _resolve_stage(mp, conv, store, diarizer, round4_stage)
        assert diarizer.calls == 0
        assert store.get('c1') is None
        assert conv.speaker_resolution.status != 'resolved'
    finally:
        mp.undo()


def test_inventory_decoded_span_count_mismatch_refuses(round4_stage):
    mp = pytest.MonkeyPatch()
    try:
        store, diarizer, lists, bucket = _inventory_base(mp)
        conv = _capture_conversation()
        pcm = _voice_pcm([(4, None), (3.8, 0), (0.2, None), (3.8, 1), (0.2, None)])
        blob = bucket.blob(f'chunks/u1/c1/{ORIGIN:.3f}.batch.bin')
        blob.metadata = storage_module.span_blob_metadata({'start': ORIGIN, 'samples': 12 * SR, 'sample_rate': SR})
        blob._store(pcm[: 6 * SR * 2])
        conv.audio_files = [
            AudioFile(
                id='af',
                uid='u1',
                conversation_id=conv.id,
                chunk_timestamps=[ORIGIN],
                duration=12,
                chunk_spans=[ChunkSpan(start=ORIGIN, end=ORIGIN + 12)],
            )
        ]
        _resolve_stage(mp, conv, store, diarizer, round4_stage)
        assert diarizer.calls == 0
        assert store.get('c1') is None
        assert conv.speaker_resolution.status != 'resolved'
    finally:
        mp.undo()


async def test_uncertain_envelope_retries_verbatim_with_later_runs(monkeypatch):
    calls = []

    def recording_reconcile(*args, **kwargs):
        calls.append(args[1:5])
        return 0, []

    monkeypatch.setattr(session_mod.pusher_session, 'reconcile_audio_chunk_prefix', recording_reconcile)
    ws = session_mod.FakePusherWebSocket(send_errors=[None, RuntimeError('send failed')])
    session = session_mod.make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    await session.connect()
    session.audio_bytes_send(b'aaaa', received_at=100.0)
    await session._audio_bytes_flush()
    session.audio_bytes_send(b'bbbb', received_at=101.0)
    session.audio_bytes_send(b'cccc', received_at=102.0)
    await session._audio_bytes_flush()
    assert calls == [('conv-1', 100.0 - 4 / 16000, b'aaaa', 8000)]
    audio_frames = [frame for frame in ws.sent if session_mod.frame_type(frame) == 101]
    assert audio_frames[-2][12:] == b'aaaa'
    assert audio_frames[-1][12:] == b'bbbbcccc'


async def test_uncertain_envelope_keeps_frozen_conversation_across_rollover(monkeypatch):
    monkeypatch.setattr(session_mod.pusher_session, 'reconcile_audio_chunk_prefix', lambda *args, **kwargs: (0, []))
    ws = session_mod.FakePusherWebSocket(send_errors=[None, RuntimeError('send failed')])
    session = session_mod.make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    await session.connect()
    session.audio_bytes_send(b'aaaa', received_at=100.0, conversation_id='conv-1')
    await session._audio_bytes_flush()
    session.deps.get_current_conversation_id = lambda: 'conv-2'
    session.audio_bytes_send(b'bbbb', received_at=101.0, conversation_id='conv-2')
    await session._audio_bytes_flush()
    boundary = [frame[4:].decode() for frame in ws.sent if session_mod.frame_type(frame) == 103]
    assert boundary == ['conv-1', 'conv-2']


async def test_cancelled_send_retains_frozen_envelope_verbatim(monkeypatch):
    monkeypatch.setattr(session_mod.pusher_session, 'reconcile_audio_chunk_prefix', lambda *args, **kwargs: (0, []))
    ws = session_mod.FakePusherWebSocket(send_errors=[asyncio.CancelledError()])
    session = session_mod.make_session(
        ws=ws, current_conversation_id=None, config_overrides={'max_audio_buffer_size': 64}
    )
    await session.connect()
    session.audio_bytes_send(b'xyzw', received_at=100.0)
    with pytest.raises(asyncio.CancelledError):
        await session._audio_bytes_flush()
    assert b''.join(run.data for run in session.audio_runs) == b'xyzw'
    await session._audio_bytes_flush()
    assert ws.sent[-1][12:] == b'xyzw'


async def test_unbound_runs_freeze_to_acceptance_conversation(monkeypatch):
    monkeypatch.setattr(session_mod.pusher_session, 'reconcile_audio_chunk_prefix', lambda *args, **kwargs: (0, []))
    current = {'id': 'conv-1'}
    ws = session_mod.FakePusherWebSocket(send_errors=[None, RuntimeError('send failed')])
    session = session_mod.make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    session.deps.get_current_conversation_id = lambda: current['id']
    await session.connect()
    session.audio_bytes_send(b'aaaa', received_at=100.0)
    await session._audio_bytes_flush()
    current['id'] = 'conv-2'
    session.audio_bytes_send(b'bbbb', received_at=101.0)
    await session._audio_bytes_flush()
    boundary = [frame[4:].decode() for frame in ws.sent if session_mod.frame_type(frame) == 103]
    assert boundary[0] == 'conv-1'
    audio_frames = [frame for frame in ws.sent if session_mod.frame_type(frame) == 101]
    assert audio_frames[-2][12:] == b'aaaa'
    assert audio_frames[-1][12:] == b'bbbb'


@pytest.mark.parametrize('cache_state', ['missing', 'corrupt'])
def test_off_saved_sync_cache_rebuild_resolves(env, monkeypatch, round4_stage, cache_state):
    store, diarizer = env
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', 'false')
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'false')
    target = round4_stage if round4_stage else stagemod.stage
    conv = stagemod._conversation([0, 1] * 4)
    audio = stagemod.FakeAudio([0, 1] * 4)
    monkeypatch.setattr(stagemod.stage, 'iter_audio_chunk_pcm', audio)
    if round4_stage is not None:
        monkeypatch.setattr(round4_stage, 'iter_audio_chunk_pcm', audio)
    target.resolve_speakers_for_processing('u1', conv)
    assert conv.speaker_resolution.status == 'resolved'
    first_calls = diarizer.calls
    first_ids = {s.id: s.speaker_id for s in conv.transcript_segments}
    first_sources = {s.id: s.audio_source for s in conv.transcript_segments}
    for s in conv.transcript_segments:
        s.audio_capture_start = stagemod.STARTED.timestamp() + s.start
        s.audio_capture_end = stagemod.STARTED.timestamp() + s.end
    if cache_state == 'missing':
        store.clear()
    else:
        store['c1'] = b'corrupt'
    target.resolve_speakers_for_processing('u1', conv)
    assert conv.speaker_resolution.status == 'resolved'
    assert diarizer.calls == first_calls + 8
    assert {s.id: s.speaker_id for s in conv.transcript_segments} == first_ids
    assert {s.id: s.audio_source for s in conv.transcript_segments} == first_sources


@pytest.mark.parametrize(
    'damage', ['retimed', 'absent', 'non_sync', 'malformed', 'nonfinite', 'unplaced', 'origin_changed']
)
def test_off_capture_history_without_saved_sync_refuses(env, monkeypatch, damage):
    store, diarizer = env
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', 'false')
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'false')
    conv = stagemod._conversation([0, 1] * 4)
    audio = stagemod.FakeAudio([0, 1] * 4)
    monkeypatch.setattr(stagemod.stage, 'iter_audio_chunk_pcm', audio)
    stagemod.stage.resolve_speakers_for_processing('u1', conv)
    assert conv.speaker_resolution.status == 'resolved'
    calls = diarizer.calls
    for s in conv.transcript_segments:
        s.audio_capture_start = stagemod.STARTED.timestamp() + s.start
        s.audio_capture_end = stagemod.STARTED.timestamp() + s.end
        if damage == 'retimed':
            s.audio_source = {
                'type': 'sync',
                'start': s.audio_source['start'] + 5,
                'end': s.audio_source['end'] + 5,
            }
        elif damage == 'absent':
            s.audio_source = None
        elif damage == 'non_sync':
            s.audio_source = {'type': 'capture', 'start': s.audio_source['start'], 'end': s.audio_source['end']}
        elif damage == 'malformed':
            s.audio_source = 'not-a-mapping'
        elif damage == 'nonfinite':
            s.audio_source = {'type': 'sync', 'start': float('nan'), 'end': s.audio_source['end']}
        elif damage == 'unplaced':
            s.audio_alignment = 'unplaced'
        elif damage == 'origin_changed':
            conv.started_at = conv.started_at + timedelta(hours=1)
    store.clear()
    stagemod.stage.resolve_speakers_for_processing('u1', conv)
    assert conv.speaker_resolution.status != 'resolved'
    assert diarizer.calls == calls


def test_off_own_capture_cache_loss_parity_with_main(env, monkeypatch, round4_stage):
    main_stage = _optional_historical(
        'r4_main_stage', 'origin/main', 'backend/utils/conversations/speaker_resolution.py'
    )
    head_stage = round4_stage if round4_stage else stagemod.stage
    results = []
    for module in (main_stage, head_stage):
        mp = pytest.MonkeyPatch()
        store, diarizer = stagemod.env.__wrapped__(mp)
        stagemod._patch_stage_deps(mp, module, store, diarizer)
        mp.setenv('AUDIO_TIMELINE_SPANS', 'false')
        mp.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
        mp.setenv('AUDIO_TIMELINE_V2', 'false')
        audio = stagemod.FakeAudio([0, 1] * 4)
        mp.setattr(module, 'iter_audio_chunk_pcm', audio)
        conv = stagemod._conversation([0, 1] * 4)
        for s in conv.transcript_segments:
            s.audio_capture_start = stagemod.STARTED.timestamp() + s.start
            s.audio_capture_end = stagemod.STARTED.timestamp() + s.end
        module.resolve_speakers_for_processing('u1', conv)
        first = (conv.speaker_resolution.status, diarizer.calls)
        store.clear()
        module.resolve_speakers_for_processing('u1', conv)
        results.append(
            {
                'first': first,
                'status': conv.speaker_resolution.status,
                'calls': diarizer.calls,
                'segments': [s.model_dump(mode='json') for s in conv.transcript_segments],
            }
        )
        mp.undo()
    assert results[0] == results[1]
