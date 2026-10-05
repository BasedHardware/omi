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
import time
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
from utils.other import audio_chunk_replay as replay_module
from utils.other import storage as storage_module
from utils.other.audio_chunks import iter_audio_chunk_pcm


@pytest.fixture
def env(monkeypatch):
    return stagemod.env.__wrapped__(monkeypatch)


ROUND4_RED_ENV = 'OMI_ROUND4_RED'
ROUND4_RED_SHA = os.environ.get(ROUND4_RED_ENV + '_SHA', '07acece3fd')
# Freeze the main baseline used by the mixed-version probes. A shared tracking
# ref can advance mid-run and import dependencies absent from this checkout.
HISTORICAL_MAIN_SHA = '3697ab9fd0450d9e044981da9b93860f64d2dd6e'


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
def round4_replay():
    if not _red_enabled():
        return None
    return _optional_historical('r4_red_replay', ROUND4_RED_SHA, 'backend/utils/other/audio_chunk_replay.py')


def _replay_backed_reconcile(replay_mod):
    """Bind a historical ``audio_chunk_replay`` to the live storage seams.

    Historical session/storage modules import ``reconcile_committed_prefix``
    from the *current* tree at exec time; without this the red run would
    silently exercise the fixed helper.
    """

    def reconcile(uid, conversation_id, timestamp, data, sample_rate, require_spans=False, **_kwargs):
        return replay_mod.reconcile_committed_prefix(
            uid,
            conversation_id,
            timestamp,
            data,
            sample_rate,
            require_spans=require_spans,
            bucket=storage_module.get_private_cloud_sync_bucket(),
            list_chunks=storage_module.list_audio_chunks,
        )

    return reconcile


@pytest.fixture
def round4_session(monkeypatch, round4_replay):
    if not _red_enabled():
        return None
    old = _optional_historical('r4_red_session', ROUND4_RED_SHA, 'backend/utils/listen_pusher_session.py')
    if round4_replay is not None and 'reconcile_audio_chunk_prefix' in dir(old):
        monkeypatch.setattr(old, 'reconcile_audio_chunk_prefix', _replay_backed_reconcile(round4_replay))
    return old


@pytest.fixture
def round4_storage(monkeypatch, round4_replay):
    if not _red_enabled():
        return None
    old = _optional_historical('r4_red_storage', ROUND4_RED_SHA, 'backend/utils/other/storage.py')
    monkeypatch.setattr(old, '_get_storage_client', lambda: storage_module._get_storage_client())
    monkeypatch.setattr(old, 'private_cloud_sync_bucket', storage_module.private_cloud_sync_bucket)
    if round4_replay is not None and 'reconcile_audio_chunk_prefix' in dir(old):
        monkeypatch.setattr(old, 'reconcile_audio_chunk_prefix', _replay_backed_reconcile(round4_replay))
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
    return _optional_historical('r4_main_pusher', HISTORICAL_MAIN_SHA, 'backend/routers/pusher.py')


@pytest.fixture(scope='module')
def old_main_storage_module():
    return _optional_historical('r4_main_storage', HISTORICAL_MAIN_SHA, 'backend/utils/other/storage.py')


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


@pytest.fixture(scope='module')
def old_main_session_module():
    return _optional_historical('r4_main_session', HISTORICAL_MAIN_SHA, 'backend/utils/listen_pusher_session.py')


async def _interior_prefix_run(mp, *, protection, session_module=None, peer=None, storage_peer=None):
    """X commits, A's send is delivered-then-failed, the drained retry resends only A.

    A lands inside the same committed object as X (the pusher batches the
    conversation), so its retry's anchor is interior to the earlier blob —
    the exact residual the reconcile extension must prove. All calls are
    unbound/unprojected legacy ``audio_bytes_send`` on one conversation.
    """
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
    stack = f._Stack(mp, v2=False, spans=False, conversation_id=f.CONV1)
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
        stack.session.deps.is_active = lambda: False
        x, a = f._phrase(9, 1), f._phrase(1, 1)
        stack.session.audio_bytes_send(x, f.T0 + 1)
        await stack.session._audio_bytes_flush()
        socket = stack.session.pusher_ws
        original_send = socket.send

        async def delivered_then_closed(data):
            await original_send(data)
            if struct.unpack('<I', data[:4])[0] == 101:
                raise ConnectionClosedError(None, None)

        socket.send = delivered_then_closed
        stack.session.audio_bytes_send(a, f.T0 + 2)
        await stack.session._audio_bytes_flush()
        await stack.stop_pusher_server()
        stack.start_pusher_server(peer=peer)
        await stack.session.connect()
        await stack.session._audio_bytes_flush()
        await stack.stop_pusher_server()
        chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
        bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
        return _stored_pcm(bucket, f.UID, chunks), chunks
    finally:
        if stack.session.reconnect_task:
            stack.session.reconnect_task.cancel()
        stack.restore()


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
@pytest.mark.parametrize('old_peer', [False, True])
@pytest.mark.parametrize('old_listen', [False, True])
async def test_legacy_retry_interior_prefix_stores_exactly_once(
    monkeypatch,
    protection,
    old_peer,
    old_listen,
    round4_session,
    round4_storage,
    old_main_session_module,
    old_main_pusher_module,
    old_main_storage_module,
):
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    session_module = old_main_session_module if old_listen else round4_session
    peer = old_main_pusher_module if old_peer else None
    storage_peer = old_main_storage_module if old_peer else round4_storage
    if old_peer:
        _old_peer_wiring(monkeypatch, old_main_pusher_module, old_main_storage_module)
    actual, chunks = await _interior_prefix_run(
        monkeypatch,
        protection=protection,
        session_module=session_module,
        peer=peer,
        storage_peer=storage_peer,
    )
    assert actual == x + a, (protection, old_listen, old_peer, [c['path'] for c in chunks])
    assert len(chunks) == 1, 'the retried A must reconcile against the object already holding X+A'
    expected_suffix = '.batch.enc' if protection == 'enhanced' else '.batch.bin'
    assert chunks[0]['path'].endswith(expected_suffix)
    assert all(not c.get('span') for c in chunks), 'legacy storage stays spanless'
    assert f.pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc.call_count == 0


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
def test_uploader_legacy_same_key_overwrites(monkeypatch, protection, round4_storage):
    """Spanless storage has zero replay inference: A then A+B at the same
    filename key ends in one A+B blob, exactly like the literal main
    uploader."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    a, b = f._phrase(1, 1), f._phrase(2, 1)
    t0 = f.T0
    _uploader(storage, [{'data': a, 'timestamp': t0}], f.UID, f.CONV1, protection, f.RATE)
    _uploader(storage, [{'data': a + b, 'timestamp': t0}], f.UID, f.CONV1, protection, f.RATE)
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 1
    assert _stored_pcm(gcs.bucket(storage_module.private_cloud_sync_bucket), f.UID, chunks) == a + b


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_legacy_fresh_occurrence_stores_verbatim(monkeypatch, protection, round4_storage):
    """A fresh occurrence whose PCM happens to match an earlier object's
    interior is a new capture, not a replay: the whole batch is stored under
    its own key with no prefix trimmed. Reproduces the round-6 fresh-
    occurrence loss: X+A committed, then a new (suffix A)+C send."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    t0 = f.T0
    _uploader(storage, [{'data': x + a, 'timestamp': t0}], f.UID, f.CONV1, protection, f.RATE)
    fresh = a[int(0.3 * f.RATE) * 2 :] + f._phrase(2, 0.1)
    _uploader(storage, [{'data': fresh, 'timestamp': t0 + 1.3}], f.UID, f.CONV1, protection, f.RATE)
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 2
    actual = _stored_pcm(gcs.bucket(storage_module.private_cloud_sync_bucket), f.UID, chunks)
    assert actual == x + a + fresh
    assert len(actual) == 89600


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_legacy_ambiguous_tail_overwrites_same_key(monkeypatch, protection, round4_storage):
    """An earlier covering spanless object must not invalidate the same-key
    retry: Q committed at T0-2 and A at T0, then replayed A plus new B at T0
    ends in Q+A+B — B preserved, existing data intact, like literal main."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    q, a, b = f._phrase(7, 3), f._phrase(1, 1), f._phrase(2, 1)
    t0 = f.T0
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    _write_raw_object(bucket, f.UID, f.CONV1, t0 - 2, q, protection)
    _uploader(storage, [{'data': a, 'timestamp': t0}], f.UID, f.CONV1, protection, f.RATE)
    _uploader(storage, [{'data': a + b, 'timestamp': t0}], f.UID, f.CONV1, protection, f.RATE)
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 2
    actual = _stored_pcm(bucket, f.UID, chunks)
    assert actual == q + a + b
    assert len(actual) == 160000


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_legacy_does_no_listing_or_probe(monkeypatch, protection):
    """Even with sample_rate supplied, a spanless upload performs no
    reconciliation listing and no existence/content probe."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)

    def forbidden(*args, **kwargs):
        raise AssertionError('legacy upload must not reconcile or probe')

    monkeypatch.setattr(storage_module, 'reconcile_audio_chunk_prefix', forbidden)
    monkeypatch.setattr(storage_module, 'list_audio_chunks', forbidden)
    monkeypatch.setattr(f.FakeBlob, 'exists', forbidden)
    monkeypatch.setattr(f.FakeBlob, 'download_as_bytes', forbidden)
    a = f._phrase(1, 1)
    paths = storage_module.upload_audio_chunks_batch(
        [{'data': a, 'timestamp': f.T0}], f.UID, f.CONV1, protection, sample_rate=f.RATE
    )
    assert len(paths) == 1
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    assert len(bucket.blobs) == 1
    stored = next(iter(bucket.blobs.values()))
    data = stored._data
    if stored.name.endswith('.enc'):
        data = encryption.decrypt_audio_file(data, f.UID)
    assert data == a


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


def test_uploader_legacy_conflicting_key_overwrites_like_main(monkeypatch):
    """A spanless unequal collision at the same filename key overwrites like
    literal main: existence/content refusal applies only to span uploads."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    a, other = f._phrase(1, 1), f._phrase(9, 1)
    t0 = f.T0
    storage_module.upload_audio_chunks_batch(
        [{'data': a, 'timestamp': t0}], f.UID, f.CONV1, 'standard', sample_rate=f.RATE
    )
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    storage_module.upload_audio_chunks_batch(
        [{'data': other, 'timestamp': t0}], f.UID, f.CONV1, 'standard', sample_rate=f.RATE
    )
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 1
    assert bucket.blob(chunks[0]['path']).download_as_bytes() == other


def _write_raw_object(bucket, uid, cid, timestamp, pcm, protection):
    data = encryption.encrypt_audio_chunk(pcm, uid) if protection == 'enhanced' else pcm
    ext = 'batch.enc' if protection == 'enhanced' else 'batch.bin'
    blob = bucket.blob(f'chunks/{uid}/{cid}/{timestamp:.3f}.{ext}')
    blob._store(data)
    return blob


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_legacy_interior_occurrence_stores_verbatim(monkeypatch, protection, round4_storage):
    """Fresh legacy occurrences cannot be inferred from an earlier object's
    interior: X+A committed, then a new A+C send stores the whole payload —
    X+A+A+C — exactly like the literal main uploader."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    x, a, c = f._phrase(9, 1), f._phrase(1, 1), f._phrase(2, 1)
    t0 = f.T0
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    _write_raw_object(bucket, f.UID, f.CONV1, t0, x + a, protection)
    _uploader(
        storage,
        [{'data': a + c, 'timestamp': t0 + len(x) / (f.RATE * 2)}],
        f.UID,
        f.CONV1,
        protection,
        f.RATE,
    )
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 2
    assert _stored_pcm(bucket, f.UID, chunks) == x + a + a + c


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_uploader_legacy_interior_mismatch_stores_verbatim(monkeypatch, protection, round4_storage):
    """Unequal PCM at a would-be interior offset is stored verbatim: legacy
    storage does no coverage inference, so the whole envelope is a new
    object — no leading-equal-part trimming either."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    storage = round4_storage or storage_module
    x, a, c = f._phrase(9, 1), f._phrase(1, 1), f._phrase(2, 1)
    other = bytes(b ^ 0xFF for b in a)
    t0 = f.T0
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    _write_raw_object(bucket, f.UID, f.CONV1, t0, x + a, protection)
    _uploader(
        storage,
        [{'data': other + c, 'timestamp': t0 + len(x) / (f.RATE * 2)}],
        f.UID,
        f.CONV1,
        protection,
        f.RATE,
    )
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert len(chunks) == 2
    assert _stored_pcm(bucket, f.UID, chunks) == x + a + other + c


def _forbidden_io(*args, **kwargs):
    raise AssertionError('legacy reconciliation must perform no listing or download I/O')


def test_reconcile_legacy_performs_no_io(monkeypatch):
    """require_spans=False returns zero proof before any listing, download, or
    bucket acquisition — spanless storage carries zero replay inference."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    _write_raw_object(bucket, f.UID, f.CONV1, f.T0, x + a, 'standard')
    verified, proven = replay_module.reconcile_committed_prefix(
        f.UID, f.CONV1, f.T0 + 1.0, a, f.RATE, bucket=bucket, list_chunks=_forbidden_io
    )
    assert verified == 0 and proven == []


def test_reconcile_legacy_unpinned_candidate_proves_nothing(monkeypatch):
    gcs = f.gcs.__wrapped__(monkeypatch)
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    blob = _write_raw_object(bucket, f.UID, f.CONV1, f.T0, x + a, 'standard')
    blob.generation = None
    verified, proven = storage_module.reconcile_audio_chunk_prefix(f.UID, f.CONV1, f.T0 + 1.0, a, f.RATE)
    assert verified == 0 and proven == []


def test_reconcile_storage_seam_legacy_acquires_no_bucket(monkeypatch):
    """The storage-level helper must not even obtain a bucket for a spanless
    reconciliation."""
    f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module, 'get_private_cloud_sync_bucket', _forbidden_io)
    monkeypatch.setattr(storage_module, 'list_audio_chunks', _forbidden_io)
    a = f._phrase(1, 1)
    verified, proven = storage_module.reconcile_audio_chunk_prefix(f.UID, f.CONV1, f.T0 + 1.0, a, f.RATE)
    assert verified == 0 and proven == []


def test_reconcile_legacy_changed_generation_proves_nothing(monkeypatch):
    gcs = f.gcs.__wrapped__(monkeypatch)
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    _write_raw_object(bucket, f.UID, f.CONV1, f.T0, x + a, 'standard')

    def stale_list(*args, **kwargs):
        chunks = storage_module.list_audio_chunks(*args, **kwargs)
        for chunk in chunks:
            chunk['generation'] = chunk['generation'] + 1
        return chunks

    verified, proven = replay_module.reconcile_committed_prefix(
        f.UID, f.CONV1, f.T0 + 1.0, a, f.RATE, bucket=bucket, list_chunks=stale_list
    )
    assert verified == 0 and proven == []


def test_reconcile_legacy_deleted_candidate_proves_nothing(monkeypatch):
    gcs = f.gcs.__wrapped__(monkeypatch)
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    blob = _write_raw_object(bucket, f.UID, f.CONV1, f.T0, x + a, 'standard')
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    blob._data = None
    verified, proven = replay_module.reconcile_committed_prefix(
        f.UID, f.CONV1, f.T0 + 1.0, a, f.RATE, bucket=bucket, list_chunks=lambda *args, **kwargs: chunks
    )
    assert verified == 0 and proven == []


def test_reconcile_legacy_object_budget_exhaustion_proves_nothing(monkeypatch):
    gcs = f.gcs.__wrapped__(monkeypatch)
    monkeypatch.setattr(replay_module, 'RECONCILE_MAX_OBJECTS', 1)
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    t0 = f.T0
    _write_raw_object(bucket, f.UID, f.CONV1, t0, x + a, 'standard')
    _write_raw_object(bucket, f.UID, f.CONV1, t0 - 0.5, b'\x00\x00' * (f.RATE // 2) + x + a, 'standard')
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    verified, proven = replay_module.reconcile_committed_prefix(
        f.UID, f.CONV1, t0 + 1.0, a, f.RATE, bucket=bucket, list_chunks=lambda *args, **kwargs: chunks
    )
    assert verified == 0 and proven == []


def test_reconcile_legacy_encrypted_size_is_not_coverage(monkeypatch):
    """Ciphertext size bounds but never proves coverage: an enhanced object
    whose decoded PCM ends exactly at the anchor offset does not cover it."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    _write_raw_object(bucket, f.UID, f.CONV1, f.T0, x, 'enhanced')
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    assert chunks[0]['size'] > len(x), 'enhanced ciphertext carries framing overhead'
    verified, proven = replay_module.reconcile_committed_prefix(
        f.UID, f.CONV1, f.T0 + 1.0, a, f.RATE, bucket=bucket, list_chunks=lambda *args, **kwargs: chunks
    )
    assert verified == 0 and proven == []


def test_reconcile_legacy_extreme_timestamp_offset_proves_nothing(monkeypatch):
    """A finite listed timestamp whose sample delta overflows to a non-finite
    offset is an invalid candidate: it is skipped, so the envelope's prefix
    stays unproven instead of crashing or proving by accident."""
    gcs = f.gcs.__wrapped__(monkeypatch)
    bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
    x, a = f._phrase(9, 1), f._phrase(1, 1)
    _write_raw_object(bucket, f.UID, f.CONV1, f.T0, x + a, 'standard')
    chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
    chunks[0]['timestamp'] = -1e308
    verified, proven = replay_module.reconcile_committed_prefix(
        f.UID, f.CONV1, f.T0 + 1.0, a, f.RATE, bucket=bucket, list_chunks=lambda *args, **kwargs: chunks
    )
    assert verified == 0 and proven == []


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
async def test_late_ack_same_socket_resumes_through_real_pusher(monkeypatch, protection, round4_session):
    """Real pusher + real storage: a delayed capability ACK arriving after the
    connect-time timeout is processed by the ordinary receive loop, lifts the
    suspension, and flushes the retained run with its pinned projection."""
    used_module = round4_session or session_mod.pusher_session
    monkeypatch.setattr(used_module, 'AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS', 0.01)
    if round4_session is not None:
        monkeypatch.setattr(f, 'ListenPusherSession', round4_session.ListenPusherSession)
        monkeypatch.setattr(f, 'ListenPusherSessionDeps', round4_session.ListenPusherSessionDeps)
        monkeypatch.setattr(
            f,
            'ListenPusherSessionConfig',
            lambda **kw: round4_session.ListenPusherSessionConfig(
                **{k: v for k, v in kw.items() if k in round4_session.ListenPusherSessionConfig.__dataclass_fields__}
            ),
        )
    gcs = f.gcs.__wrapped__(monkeypatch)
    f.pusher_env.__wrapped__(monkeypatch)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: protection)
    stack = f._Stack(monkeypatch, v2=False, spans=True, conversation_id=f.CONV1)
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
    receiver_task = None

    class DelayedRecv:
        def __init__(self, inner):
            self.inner = inner
            self.pending_delay = True

        async def send(self, data):
            return await self.inner.send(data)

        async def recv(self):
            if self.pending_delay:
                self.pending_delay = False
                await asyncio.sleep(0.05)
            return await self.inner.recv()

        async def close(self, code=1000):
            return await self.inner.close(code)

    try:
        stack.build_session()
        session = stack.session
        session.config.max_audio_buffer_size = 16
        stack.start_pusher_server()
        await session.connect()
        assert session.audio_timeline_active
        await stack.stop_pusher_server()

        session.pusher_connected = False
        stack.start_pusher_server()
        plain_connect = session.deps.connect_to_pusher

        async def delayed_connect(*args, **kwargs):
            return DelayedRecv(await plain_connect(*args, **kwargs))

        session.deps.connect_to_pusher = delayed_connect
        seen_frames = []
        server_ws = stack.server_ws
        original_recv = server_ws.receive_bytes

        async def recording_recv():
            data = await original_recv()
            seen_frames.append(bytes(data))
            return data

        server_ws.receive_bytes = recording_recv
        await session.connect()
        assert session.audio_timeline_suspended
        assert session.pending_request_event.is_set()
        resumed_socket = session.pusher_ws

        runs = [b'aaaaaaaa', b'bbbbbbbb', b'cccccccc']
        starts = [f.T0 + i * (len(runs[0]) / (f.RATE * 2)) for i in range(3)]
        session.audio_bytes_send(runs[0], starts[0], conversation_id=f.CONV1, start_wall=starts[0])
        await session._audio_bytes_flush()
        assert session.audio_total_size == len(runs[0])

        session.transcript_send([{'id': 'seg-x', 'text': 'hi', 'speaker': 'SPEAKER_00', 'start': 0.0, 'end': 1.0}])
        await session._transcript_flush()
        assert list(session.segment_buffers) == []

        receiver_task = asyncio.create_task(session.pusher_receive())
        deadline = time.monotonic() + 5
        while session.audio_timeline_suspended and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert not session.audio_timeline_suspended, 'the late ACK must resume the same socket'
        assert session.pusher_connected
        assert session.pusher_ws is resumed_socket

        for i in (1, 2):
            session.audio_bytes_send(runs[i], starts[i], conversation_id=f.CONV1, start_wall=starts[i])
            await session._audio_bytes_flush()
        assert session.audio_total_size == 0
        receiver_task.cancel()
        try:
            await asyncio.wait_for(receiver_task, timeout=2)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        receiver_task = None
        await stack.stop_pusher_server()

        expected_suffix = '.batch.enc' if protection == 'enhanced' else '.batch.bin'
        chunks = storage_module.list_audio_chunks(f.UID, f.CONV1)
        assert all(c['path'].endswith(expected_suffix) for c in chunks)
        bucket = gcs.bucket(storage_module.private_cloud_sync_bucket)
        stored = _stored_pcm(bucket, f.UID, chunks)
        assert stored == b'aaaaaaaa' + b'bbbbbbbb' + b'cccccccc'
        spans_seen = sorted((c['span'] for c in chunks if c.get('span')), key=lambda s: s['start'])
        assert spans_seen, 'spans sessions store validated spans'
        assert sum(s['samples'] for s in spans_seen) * 2 == len(stored)
        assert abs(spans_seen[0]['start'] - starts[0]) < 0.001
        for earlier, later in zip(spans_seen, spans_seen[1:]):
            assert abs(later['start'] - (earlier['start'] + earlier['samples'] / f.RATE)) < 0.001
        audio_frames = [frame for frame in seen_frames if struct.unpack('<I', frame[:4])[0] == 101]
        assert audio_frames and abs(struct.unpack('d', audio_frames[0][4:12])[0] - starts[0]) < 0.001
        assert any(
            struct.unpack('<I', frame[:4])[0] == 102 for frame in seen_frames
        ), 'transcripts must still flow while suspended'
        assert f.pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc.call_count == 0
    finally:
        if receiver_task is not None:
            receiver_task.cancel()
        if stack.session and stack.session.reconnect_task:
            stack.session.reconnect_task.cancel()
        stack.restore()


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
    """Negotiated spans only: an uncertain envelope reconciles with
    require_spans=True and resends its frozen header and PCM verbatim."""
    calls = []

    def recording_reconcile(*args, **kwargs):
        calls.append((args[1:5], kwargs.get('require_spans')))
        return 0, []

    monkeypatch.setattr(session_mod.pusher_session, 'reconcile_audio_chunk_prefix', recording_reconcile)
    ws = session_mod.FakePusherWebSocket(
        incoming=[session_mod.audio_timeline_ack_frame()], send_errors=[None, RuntimeError('send failed')]
    )
    session = session_mod.make_session(
        ws=ws, config_overrides={'max_audio_buffer_size': 64, 'audio_timeline_spans': True}
    )
    await session.connect()
    assert session.audio_timeline_active
    session.audio_bytes_send(b'aaaa', received_at=100.0, conversation_id='conv-1', start_wall=100.0)
    await session._audio_bytes_flush()
    session.audio_bytes_send(b'bbbb', received_at=101.0)
    session.audio_bytes_send(b'cccc', received_at=102.0)
    await session._audio_bytes_flush()
    assert calls == [(('conv-1', 100.0, b'aaaa', 8000), True)]
    audio_frames = [frame for frame in ws.sent if session_mod.frame_type(frame) == 101]
    assert audio_frames[-2][12:] == b'aaaa'
    assert audio_frames[-1][12:] == b'bbbbcccc'


async def test_uncertain_envelope_keeps_frozen_conversation_across_rollover(monkeypatch):
    monkeypatch.setattr(session_mod.pusher_session, 'reconcile_audio_chunk_prefix', lambda *args, **kwargs: (0, []))
    ws = session_mod.FakePusherWebSocket(
        incoming=[session_mod.audio_timeline_ack_frame()], send_errors=[None, RuntimeError('send failed')]
    )
    session = session_mod.make_session(
        ws=ws, config_overrides={'max_audio_buffer_size': 64, 'audio_timeline_spans': True}
    )
    await session.connect()
    assert session.audio_timeline_active
    session.audio_bytes_send(b'aaaa', received_at=100.0, conversation_id='conv-1', start_wall=100.0)
    await session._audio_bytes_flush()
    session.deps.get_current_conversation_id = lambda: 'conv-2'
    session.audio_bytes_send(b'bbbb', received_at=101.0, conversation_id='conv-2', start_wall=101.0)
    await session._audio_bytes_flush()
    boundary = [frame[4:].decode() for frame in ws.sent if session_mod.frame_type(frame) == 103]
    assert boundary == ['conv-1', 'conv-2']


async def test_cancelled_send_retains_frozen_envelope_verbatim(monkeypatch):
    """On a negotiated socket even cancellation retains the frozen envelope
    for a verbatim resend."""
    monkeypatch.setattr(session_mod.pusher_session, 'reconcile_audio_chunk_prefix', lambda *args, **kwargs: (0, []))
    ws = session_mod.FakePusherWebSocket(
        incoming=[session_mod.audio_timeline_ack_frame()], send_errors=[asyncio.CancelledError()]
    )
    session = session_mod.make_session(
        ws=ws,
        current_conversation_id=None,
        config_overrides={'max_audio_buffer_size': 64, 'audio_timeline_spans': True},
    )
    await session.connect()
    assert session.audio_timeline_active
    session.audio_bytes_send(b'xyzw', received_at=100.0, start_wall=100.0)
    with pytest.raises(asyncio.CancelledError):
        await session._audio_bytes_flush()
    assert b''.join(run.data for run in session.audio_runs) == b'xyzw'
    await session._audio_bytes_flush()
    assert ws.sent[-1][12:] == b'xyzw'


async def test_unbound_runs_freeze_to_acceptance_conversation(monkeypatch):
    monkeypatch.setattr(session_mod.pusher_session, 'reconcile_audio_chunk_prefix', lambda *args, **kwargs: (0, []))
    current = {'id': 'conv-1'}
    ws = session_mod.FakePusherWebSocket(
        incoming=[session_mod.audio_timeline_ack_frame()], send_errors=[None, RuntimeError('send failed')]
    )
    session = session_mod.make_session(
        ws=ws, config_overrides={'max_audio_buffer_size': 64, 'audio_timeline_spans': True}
    )
    session.deps.get_current_conversation_id = lambda: current['id']
    await session.connect()
    assert session.audio_timeline_active
    session.audio_bytes_send(b'aaaa', received_at=100.0, start_wall=100.0)
    await session._audio_bytes_flush()
    current['id'] = 'conv-2'
    session.audio_bytes_send(b'bbbb', received_at=101.0, start_wall=101.0)
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
        'r4_main_stage', HISTORICAL_MAIN_SHA, 'backend/utils/conversations/speaker_resolution.py'
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
