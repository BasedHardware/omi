"""Exercise listing-free live projections through the real parser and grouping code."""

import asyncio
import struct
from collections import deque
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import FailedPrecondition, NotFound
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

import routers.pusher as pusher
from database import record_audio
from utils.other.audio_outbox import AudioReceipt

from database import conversations as db
from database.audio_timeline import span_blob_metadata
from utils import pusher_audio_projection as projection
from utils.batch_pipeline import record_projection_rebuild as full_projection
from utils.other import storage


@pytest.fixture
def world(monkeypatch):
    monkeypatch.delenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', raising=False)
    monkeypatch.delenv('PUSHER_PROJECTION_DEBT_DURABLE_ENABLED', raising=False)
    monkeypatch.setattr(projection.record_projection_rebuild, 'mark_due', MagicMock())
    monkeypatch.setattr(projection.record_projection_rebuild, 'mark_many', MagicMock())
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: False)
    monkeypatch.setattr(projection, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(projection, 'record_fallback', MagicMock())
    clock = [1000.0]
    blobs = {}
    lists = []
    gets = []
    stored = []
    rows = {}
    writes = []
    gone = [False]
    conflict = [False]

    class Bucket:
        def __init__(self, name):
            self.name = name

        def list_blobs(self, prefix):
            lists.append(prefix)
            return [b for (bucket, path), b in blobs.items() if bucket == self.name and path.startswith(prefix)]

        def get_blob(self, path):
            gets.append((self.name, path))
            return blobs.get((self.name, path))

    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=Bucket))

    def add(start, samples=16000, cid='c', bucket=None, generation=1):
        name = bucket or storage.private_cloud_sync_bucket
        path = f'chunks/u/{cid}/{start:.3f}.batch.bin'
        blobs[name, path] = SimpleNamespace(
            name=path,
            bucket=Bucket(name),
            size=samples * 2,
            generation=generation,
            md5_hash='md5',
            crc32c='crc',
            metadata=span_blob_metadata({'start': start, 'samples': samples, 'sample_rate': 16000}),
        )
        return path

    def update(uid, cid, payload, *, expected_audio_files=None):
        if gone[0]:
            return False
        if expected_audio_files is not None:
            if conflict[0] or db.audio_files_revision(rows.get(cid, [])) != db.audio_files_revision(
                expected_audio_files
            ):
                conflict[0] = False
                raise db.AudioFilesChanged()
        rows[cid] = deepcopy(payload['audio_files'])
        stored[:] = rows[cid]
        writes.append(deepcopy(stored))
        return True

    monkeypatch.setattr(db, 'update_conversation', update)
    monkeypatch.setattr(
        db,
        'get_conversation_raw_snapshot',
        lambda uid, cid, **kw: {'audio_files': deepcopy(rows.get(cid, [])), 'deleted': gone[0]},
    )
    return SimpleNamespace(
        add=add,
        lists=lists,
        gets=gets,
        stored=stored,
        writes=writes,
        clock=clock,
        gone=gone,
        conflict=conflict,
        blobs=blobs,
    )


def test_default_on_appends_current_spans_and_exact_playback_identity_without_listing(world):
    cache = projection.PusherAudioProjection('u')
    a = world.add(100)
    assert cache.refresh('c', [a]) is True
    b = world.add(101)
    assert cache.refresh('c', [b]) is True
    assert len(world.lists) == 1
    assert len(world.gets) == 1
    assert len(world.writes) == 2  # deletion check and speaker evidence stay per flush
    listed = storage.list_audio_chunks('u', 'c', source_identity=True)
    expected = [af.model_dump() for af in db.create_audio_files_from_chunks('u', 'c', listed_chunks=listed)]
    assert world.stored == expected
    assert world.stored[0]['duration'] == 2
    assert world.stored[0]['chunk_timestamps'] == [100, 101]


def test_discontinuity_retry_and_submillisecond_clock_match_full_listing(world):
    cache = projection.PusherAudioProjection('u')
    a = world.add(100.0004)
    cache.refresh('c', [a])
    b = world.add(200.0004)
    cache.refresh('c', [b, b])
    cache.refresh('c', [b])  # identical replay never duplicates a chunk
    full = [af.model_dump() for af in db.create_audio_files_from_chunks('u', 'c')]
    assert world.stored == full
    assert len(full) == 2


def test_refresh_deadline_never_slides_on_append_and_finish_rebuilds_an_empty_tail(world):
    cache = projection.PusherAudioProjection('u')
    a = world.add(100)
    cache.refresh('c', [a])
    world.clock[0] += 299
    cache.refresh('c', [world.add(101)])
    assert len(world.lists) == 1
    world.clock[0] += 1
    cache.refresh('c', [world.add(102)])
    assert len(world.lists) == 2
    cache.finish('c')
    assert len(world.lists) == 3
    assert not cache.inventory


def test_gone_owner_is_checked_during_incremental_flush(world):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    world.gone[0] = True
    assert cache.refresh('c', [world.add(101)]) is False
    assert len(world.lists) == 1
    assert not cache.inventory


def test_other_pod_and_reconnect_force_full_rebuild(world):
    first = projection.PusherAudioProjection('u')
    second = projection.PusherAudioProjection('u')
    first.refresh('c', [world.add(100)])
    second.refresh('c', [world.add(101)])
    first.refresh('c', [world.add(102)])
    assert len(world.lists) == 3
    assert world.stored[0]['chunk_timestamps'] == [100, 101, 102]
    projection.PusherAudioProjection('u').refresh('c', [world.add(103)])
    assert len(world.lists) == 4


def test_revision_race_and_metadata_failure_rebuild_in_same_flush(world, monkeypatch):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    world.conflict[0] = True
    cache.refresh('c', [world.add(101)])
    assert len(world.lists) == 2
    monkeypatch.setattr(projection, 'get_uploaded_audio_chunks', MagicMock(side_effect=OSError()))
    cache.refresh('c', [world.add(102)])
    assert len(world.lists) == 3
    projection.record_fallback.assert_called_once()


def test_failure_keeps_full_close_rebuild_due(world, monkeypatch):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    update = db.update_conversation
    monkeypatch.setattr(db, 'update_conversation', MagicMock(side_effect=OSError()))
    with pytest.raises(OSError):
        cache.refresh('c', [world.add(101)])
    monkeypatch.setattr(db, 'update_conversation', update)
    cache.finish('c')
    assert world.stored[0]['chunk_timestamps'] == [100, 101]
    assert len(world.lists) == 2


@pytest.mark.parametrize('rollback', [True, False])
def test_kill_switch_keeps_listing_while_archive_recomputes_overlays(world, monkeypatch, rollback):
    if rollback:
        monkeypatch.setenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', '0')
    else:
        monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: True)
        monkeypatch.setattr(storage, 'list_packs', lambda *_: [])
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    cache.refresh('c', [world.add(101)])
    assert len(world.lists) == (2 if rollback else 1)
    assert len(world.gets) == (0 if rollback else 1)
    assert bool(cache.inventory) is not rollback


def test_bounded_state_and_missing_inventory_fail_toward_listing(world, monkeypatch):
    monkeypatch.setattr(projection, 'MAX_CONVERSATIONS', 1)
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    cache.refresh('other', [world.add(101, cid='other')])
    cache.refresh('other', [world.add(102, cid='other')])
    assert len(cache.inventory) == 1
    assert len(world.lists) == 3
    monkeypatch.setattr(projection, 'MAX_CHUNKS', 1)
    cache.refresh('c', [world.add(103)])
    assert not cache.inventory
    cache.refresh('c', [world.add(104)])
    assert len(world.lists) == 4


def test_exact_metadata_prefers_regional_copy_like_full_listing(world, monkeypatch):
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'regional')
    path = world.add(100)
    world.add(100, bucket='regional', generation=2)
    exact = projection.get_uploaded_audio_chunks('u', 'c', [path])
    listed = storage.list_audio_chunks('u', 'c', source_identity=True)
    assert exact == listed
    assert exact[0]['generation'] == 2
    with pytest.raises(ValueError):
        projection.get_uploaded_audio_chunks('u', 'c', ['raw-live/u/c/pack'])


@pytest.mark.parametrize('failure', ['changed', 'raced', 'deleted'])
def test_real_update_conversation_checks_cached_revision_and_write_precondition(monkeypatch, failure):
    # SDK boundary fake: force real read/compare/precondition/error handling.
    client = MagicMock()
    ref = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    snapshot = ref.get.return_value
    snapshot.exists = True
    snapshot.update_time = 'revision'
    snapshot.to_dict.return_value = {'audio_files': [{'id': 'old', 'source_fingerprint': 'old'}]}
    monkeypatch.setattr(db, 'db', client)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(db, '_prepare_conversation_for_write', lambda data, *_, **_kwargs: data)
    monkeypatch.setattr(db, 'guard_match_score_size', lambda *_: None)
    # Restore the actual function instead of world's projection update fake.
    update = REAL_UPDATE
    expected = [{'id': 'different' if failure == 'changed' else 'old', 'source_fingerprint': 'old'}]
    ref.update.side_effect = NotFound('gone') if failure == 'deleted' else FailedPrecondition('raced')
    if failure == 'deleted':
        assert update('u', 'c', {'audio_files': []}, expected_audio_files=expected) is False
    else:
        with pytest.raises(db.AudioFilesChanged):
            update('u', 'c', {'audio_files': []}, expected_audio_files=expected)
    if failure == 'changed':
        ref.update.assert_not_called()
    else:
        client.write_option.assert_called_once_with(last_update_time='revision')
        assert ref.update.call_args.kwargs['option'] == client.write_option.return_value


REAL_UPDATE = db.update_conversation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'durable,ending',
    [
        (durable, ending)
        for ending in ('disconnect', 'switch', 'deleted', 'retry', 'terminal')
        for durable in (False, True)
        if durable or ending not in {'retry', 'terminal'}
    ],
)
async def test_real_socket_flushes_keep_identity_fresh_and_finalize(world, monkeypatch, durable, ending):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true' if durable else 'false')
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda _: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda _: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda _: True)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda _: 'standard')
    monkeypatch.setattr(pusher.ReadinessGate, 'is_serving', lambda: True)
    monkeypatch.setattr(record_audio, 'set_record_upload_pending', MagicMock(return_value=True))
    monkeypatch.setattr(record_audio, 'mark_record_upload_failed', MagicMock(return_value=True))
    monkeypatch.setattr(record_audio, 'seal_record_audio', MagicMock(return_value='not_batch_owner'))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 0)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.01)
    learning = MagicMock()
    identity = MagicMock()
    monkeypatch.setattr(pusher, 'schedule_person_voice_learning_retry', learning)
    monkeypatch.setattr(projection, 'schedule_person_voice_learning_retry', learning)
    monkeypatch.setattr(pusher, 'schedule_completed_identity_retries', identity)
    loop = asyncio.get_running_loop()
    handled = asyncio.Event()
    uploads = []
    retry = [3 if ending == 'terminal' else int(ending == 'retry')]
    update = db.update_conversation

    def apply(*args, **kwargs):
        if retry[0] and len(uploads) >= 2:
            retry[0] -= 1
            if ending == 'terminal' and retry[0] == 0:
                loop.call_soon_threadsafe(handled.set)
            raise OSError('synthetic metadata failure')
        result = update(*args, **kwargs)
        loop.call_soon_threadsafe(handled.set)
        return result

    monkeypatch.setattr(db, 'update_conversation', apply)

    def upload(chunks, uid, cid, *_args, **_kwargs):
        uploads.append(cid)
        return [world.add(chunks[0]['timestamp'], sum(len(c['data']) // 2 for c in chunks), cid=cid)]

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    pcm = b'\x01\x00' * 16000

    def commit(uid, payload, cid, start, rate, *_args, **_kwargs):
        return AudioReceipt(
            'bucket', 'path', '1', 'digest', 'manifest', '1', 'digest', 'digest', cid, start, len(payload) // 2, rate
        )

    monkeypatch.setattr(pusher, 'commit_pcm_window', commit)
    monkeypatch.setattr(pusher, 'read_pcm', lambda *_: pcm)

    class Socket:
        client_state = WebSocketState.CONNECTED
        close_code = None

        def __init__(self):
            self.initial = deque([struct.pack('<I', 103) + b'c', struct.pack('<Id', 101, 100) + pcm])
            self.round = 0

        async def accept(self):
            pass

        async def close(self, code=1000, reason=None):
            self.close_code = code
            self.client_state = WebSocketState.DISCONNECTED

        async def send_bytes(self, data):
            pass

        async def receive_bytes(self):
            if self.initial:
                return self.initial.popleft()
            if self.round < 2:
                await asyncio.wait_for(handled.wait(), 3)
                handled.clear()
                self.round += 1
                if ending == 'deleted' and self.round == 1:
                    world.gone[0] = True
                if ending == 'terminal' and self.round == 2:
                    raise WebSocketDisconnect(1000)
                if ending == 'switch' and self.round == 2:
                    return struct.pack('<I', 103) + b'next'
                return struct.pack('<Id', 101, 100 + self.round) + pcm
            raise WebSocketDisconnect(1000)

    await asyncio.wait_for(pusher._websocket_util_trigger(Socket(), 'u', 16000, audio_timeline=2), 5)
    if ending == 'deleted':
        assert uploads == ['c', 'c']  # same-flush deletion result stops the third upload
        assert learning.call_count == 1
    else:
        assert len(world.lists) >= 2  # initial plus explicit close/disconnect, even if no tail
        assert world.stored[0]['chunk_timestamps'][:2] == [100, 101]
        assert learning.call_count >= (2 if ending == 'terminal' else 3)
    assert identity.called
    assert 'c' in identity.call_args.args[1]


@pytest.mark.parametrize('mode', ['eligible', 'archive', 'unknown_paths'])
def test_full_listing_race_cannot_clobber_other_pod(world, monkeypatch, mode):
    listing = storage.list_audio_chunks
    cache = projection.PusherAudioProjection('u')
    a = world.add(100)
    once = [True]

    def racing_list(*args, **kwargs):
        old = listing(*args, **kwargs)
        if once[0]:
            once[0] = False
            world.add(101)
            newer = [
                af.model_dump()
                for af in db.create_audio_files_from_chunks('u', 'c', listed_chunks=listing(*args, **kwargs))
            ]
            db.update_conversation('u', 'c', {'audio_files': newer})
        return old

    monkeypatch.setattr(storage, 'list_audio_chunks', racing_list)
    monkeypatch.setattr(db, 'list_audio_chunks', racing_list)
    if mode == 'archive':
        monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: True)
        monkeypatch.setattr(storage, 'list_packs', lambda *_: [])
    assert cache.refresh('c', None if mode == 'unknown_paths' else [a]) is True
    assert world.stored[0]['chunk_timestamps'] == [100, 101]
    assert len(world.writes) == 2  # only the peer and the successful rebuild


@pytest.mark.parametrize('spanless', [True, False])
def test_mutable_or_nonbatch_sources_never_enter_inventory(world, spanless):
    a = world.add(100)
    blob = next(iter(world.blobs.values()))
    if spanless:
        blob.metadata = None
    else:
        key = next(iter(world.blobs))
        del world.blobs[key]
        blob.name = a.replace('.batch.bin', '.opus')
        a = blob.name
        world.blobs[key[0], a] = blob
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [a])
    assert not cache.inventory
    cache.refresh('c', [world.add(101)])
    assert len(world.lists) == 2
    assert not cache.inventory


def test_cache_cap_miss_still_rebuilds_on_explicit_close(world, monkeypatch):
    monkeypatch.setattr(projection, 'MAX_CONVERSATIONS', 1)
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    cache.refresh('other', [world.add(101, cid='other')])
    before = len(world.lists)
    assert cache.finish('other') is True
    assert len(world.lists) == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('deterministic', [False, True])
async def test_close_discovery_errors_are_bounded_and_cannot_abort_custody(world, monkeypatch, deterministic):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    error = projection.InvalidArgument('private path') if deterministic else OSError('private path')
    finish = MagicMock(side_effect=error)
    monkeypatch.setattr(cache, 'finish', finish)
    identities = set()
    if not deterministic:
        assert await cache.finish_pending('c', set(), identities) is False
        assert await cache.finish_pending('c', set(), identities) is False
    assert await cache.finish_pending('c', set(), identities) is True
    assert finish.call_count == (1 if deterministic else 3)
    assert not cache.inventory and not cache.close_retries
    assert not identities
    await cache.persist_pending()
    projection.record_projection_rebuild.mark_many.assert_called_once_with('u', {'c'})


def test_empty_listing_still_observes_deleted_owner(world):
    world.gone[0] = True
    cache = projection.PusherAudioProjection('u')
    assert cache.refresh('c', ['chunks/u/c/100.000.batch.bin']) is False
    assert not world.writes


@pytest.mark.parametrize('mode', ['archive', 'unknown_paths', 'rollback'])
def test_empty_fallback_listing_still_detects_gone_owner(world, monkeypatch, mode):
    monkeypatch.setattr(db, 'get_conversation_raw_snapshot', lambda *a, **kw: None)
    if mode == 'archive':
        monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: True)
    if mode == 'rollback':
        monkeypatch.setenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', '0')
    cache = projection.PusherAudioProjection('u')
    assert cache.refresh('c', None if mode == 'unknown_paths' else ['chunks/u/c/100.batch.bin']) is False
    assert not world.writes


def test_terminal_projection_failure_retains_independent_close_debt(world, monkeypatch):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    update = db.update_conversation
    monkeypatch.setattr(db, 'update_conversation', MagicMock(side_effect=OSError()))
    with pytest.raises(OSError):
        cache.refresh('c', [world.add(101)])
    # The durable worker can discard an invalid cache after retry exhaustion,
    # but its independent close obligation must survive that terminal failure.
    cache.inventory.pop('c', None)
    assert cache.close_debt == {'c'}
    monkeypatch.setattr(db, 'update_conversation', update)
    for cid in list(cache.close_debt):
        cache.finish(cid)
    assert not cache.close_debt
    assert world.stored[0]['chunk_timestamps'] == [100, 101]


def test_seal_retry_does_not_repeat_successful_close_listing(world):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    assert cache.finish('c') is True
    before = len(world.lists)
    assert cache.finish('c') is None
    assert len(world.lists) == before
    cache.refresh('c', [world.add(101)])
    assert cache.finish('c') is True
    assert world.stored[0]['chunk_timestamps'] == [100, 101]


def test_failed_forced_rebuild_invalidates_inventory_before_later_flush(world, monkeypatch):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    world.add(101)  # Peer upload has not published a Firestore projection yet.
    listing = storage.list_audio_chunks
    monkeypatch.setattr(storage, 'list_audio_chunks', MagicMock(side_effect=OSError()))
    monkeypatch.setattr(db, 'list_audio_chunks', MagicMock(side_effect=OSError()))
    with pytest.raises(OSError):
        cache.finish('c')
    assert not cache.inventory
    assert cache.close_debt == {'c'}
    monkeypatch.setattr(storage, 'list_audio_chunks', listing)
    monkeypatch.setattr(db, 'list_audio_chunks', listing)
    cache.refresh('c', [world.add(102)])
    assert len(world.lists) == 2
    assert world.stored[0]['chunk_timestamps'] == [100, 101, 102]


def raw_pack(start, end, name='pack', generation=9):
    return {
        'timestamp': start,
        'path': f'raw-live/u/c/{name}.flac',
        'size': 123,
        'is_batch': False,
        'span': {'start': start, 'samples': round((end - start) * 16000), 'sample_rate': 16000},
        'raw_end': end,
        'generation': generation,
        'pcm_sha256': 'digest',
    }


def test_fleet_archive_read_recomputes_split_overlays_without_encoded_prefix_list(world, monkeypatch):
    # READ is on by default in production: this must be an optimization there,
    # not just when tests disable the archive phase.
    monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: True)
    packs = [raw_pack(100.0004, 104.0004)]
    pack_index = MagicMock(side_effect=lambda *_: packs)
    monkeypatch.setattr(storage, 'list_packs', pack_index)
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100.0004)])
    packs.append(raw_pack(104.0004, 106.0004, 'new-tail', 10))
    cache.refresh('c', [world.add(102.0004)])
    assert len(world.lists) == 1
    assert pack_index.call_count == 2  # Existing raw index is consulted each time.
    assert all(c['path'].startswith('chunks/') for c in cache.inventory['c'].chunks)
    expected = [af.model_dump() for af in db.create_audio_files_from_chunks('u', 'c')]
    assert world.stored == expected
    timestamps = world.stored[0]['chunk_timestamps']
    assert len(timestamps) == 5  # two encoded parts + split raw bridge/tail + new pack
    assert max(timestamps) >= 104


def test_stop_pcm_raw_only_flushes_refresh_pack_projection_without_encoded_lists(world, monkeypatch):
    monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: True)
    packs = [raw_pack(100, 101, 'first')]
    monkeypatch.setattr(storage, 'list_packs', lambda *_: packs)
    cache = projection.PusherAudioProjection('u')
    assert cache.refresh('c', [packs[0]['path']]) is True
    assert cache.inventory['c'].chunks == []
    packs.append(raw_pack(101, 102, 'second', 10))
    assert cache.refresh('c', [packs[1]['path']]) is True
    assert len(world.lists) == 1
    assert not world.gets  # Raw metadata comes from the unchanged pack index.
    assert world.stored[0]['chunk_timestamps'] == [100, 101]
    expected = [af.model_dump() for af in db.create_audio_files_from_chunks('u', 'c')]
    assert world.stored == expected
    assert cache.finish('c') is True
    assert not cache.close_debt


def test_archive_index_failure_uses_full_legacy_fallback_without_caching(world, monkeypatch):
    monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: True)
    packs = [raw_pack(100, 106)]
    monkeypatch.setattr(storage, 'list_packs', lambda *_: packs)
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    before = deepcopy(world.stored)
    monkeypatch.setattr(storage, 'list_packs', MagicMock(side_effect=OSError()))
    assert cache.refresh('c', [world.add(102)]) is True
    fallback = [af.model_dump() for af in db.create_audio_files_from_chunks('u', 'c')]
    assert world.stored == fallback
    assert world.stored != before
    assert not cache.inventory.get('c')
    assert cache.close_debt == {'c'}
    monkeypatch.setattr(storage, 'list_packs', lambda *_: packs)
    cache.refresh('c', [world.add(103)])
    expected = [af.model_dump() for af in db.create_audio_files_from_chunks('u', 'c')]
    assert world.stored == expected


def test_closing_flush_counts_as_final_discovery_without_second_listing(world):
    cache = projection.PusherAudioProjection('u')
    assert cache.refresh('c', [world.add(100)], force=True) is True
    assert not cache.inventory
    assert not cache.close_debt
    assert cache.finish('c') is None
    assert len(world.lists) == 1
    cache.refresh('c', [world.add(101)])  # Later audio reopens the obligation.
    assert cache.close_debt == {'c'}
    assert cache.finish('c') is True


@pytest.mark.asyncio
async def test_failed_marker_write_keeps_debt_for_eviction_retry(world, monkeypatch):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    monkeypatch.setattr(cache, 'finish', MagicMock(side_effect=projection.InvalidArgument('private path')))
    marker = projection.record_projection_rebuild.mark_many
    marker.side_effect = [OSError('private path'), None]
    # Marker persistence never changes successful recording completion.
    assert await cache.finish_pending('c', set(), set()) is True
    await cache.persist_pending()
    assert not cache.close_debt and not cache.marker_retry and marker.call_count == 2


@pytest.mark.asyncio
async def test_eviction_and_switch_off_marker_handoff(world, monkeypatch):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    projection.record_projection_rebuild.mark_due.assert_not_called()  # no hot-path writes
    projection.record_projection_rebuild.mark_many.assert_not_called()
    await cache.persist_pending()
    projection.record_projection_rebuild.mark_many.assert_called_once_with('u', {'c'})
    cache.refresh('c', [world.add(101)])
    monkeypatch.setenv('PUSHER_PROJECTION_DEBT_DURABLE_ENABLED', 'off')
    await cache.persist_pending()
    projection.record_projection_rebuild.mark_due.assert_not_called()
    assert projection.record_projection_rebuild.mark_many.call_count == 1


@pytest.mark.parametrize('incremental', ['0', '1'])
def test_socket_independent_rebuild_always_uses_full_discovery_and_privacy_writer(world, monkeypatch, incremental):
    world.add(100)
    monkeypatch.setenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', incremental)
    monkeypatch.setattr(full_projection, 'projection_owner_gone', lambda *_: False)
    write = MagicMock(side_effect=db.update_conversation)
    monkeypatch.setattr(projection.record_projection_rebuild, 'apply_projection', write)
    assert full_projection.rebuild('u', 'c') is True
    assert len(world.lists) == 1
    assert write.call_args.kwargs['expected_audio_files'] == []
    projection.record_projection_rebuild.mark_due.assert_not_called()


def test_socket_independent_rebuild_refuses_deleted_before_storage(world, monkeypatch):
    monkeypatch.setattr(full_projection, 'projection_owner_gone', lambda *_: True)
    assert full_projection.rebuild('u', 'c') is False
    assert not world.lists and not world.writes


def test_rebuild_refuses_incomplete_raw_index_without_metadata_write(world, monkeypatch):
    world.add(100)
    monkeypatch.setattr(full_projection, 'projection_owner_gone', lambda *_: False)
    monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: True)
    monkeypatch.setattr(storage, 'list_packs', MagicMock(side_effect=OSError()))
    with pytest.raises(OSError):
        full_projection.rebuild('u', 'c')
    assert not world.writes


@pytest.mark.asyncio
@pytest.mark.parametrize('incomplete', ['raw_index', 'empty'])
async def test_incomplete_close_discovery_hands_off_durable_debt(world, monkeypatch, incomplete):
    cache = projection.PusherAudioProjection('u')
    cache.refresh('c', [world.add(100)])
    if incomplete == 'raw_index':
        monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *_: True)
        monkeypatch.setattr(storage, 'list_packs', MagicMock(side_effect=OSError()))
        assert await cache.finish_pending('c', set(), set()) is False
        assert await cache.finish_pending('c', set(), set()) is False
    else:
        world.blobs.clear()
    assert await cache.finish_pending('c', set(), set()) is True
    await cache.persist_pending()
    projection.record_projection_rebuild.mark_many.assert_called_once_with('u', {'c'})
    assert not cache.close_debt


@pytest.mark.asyncio
async def test_terminal_batch_persists_debt_even_when_close_inventory_is_full(world, monkeypatch):
    monkeypatch.setattr(projection, 'MAX_CONVERSATIONS', 0)
    await test_real_socket_flushes_keep_identity_fresh_and_finalize(world, monkeypatch, True, 'terminal')
    assert any('c' in call.args[1] for call in projection.record_projection_rebuild.mark_many.call_args_list)


@pytest.mark.asyncio
async def test_failed_terminal_handoff_outside_full_cache_is_retried_by_real_socket_cleanup(world, monkeypatch):
    monkeypatch.setattr(projection, 'MAX_CONVERSATIONS', 0)
    failed = [False]

    def fail_once(*args):
        if not failed[0]:
            failed[0] = True
            raise OSError('synthetic marker outage')

    projection.record_projection_rebuild.mark_many.side_effect = fail_once
    await test_real_socket_flushes_keep_identity_fresh_and_finalize(world, monkeypatch, True, 'terminal')
    assert failed[0] and projection.record_projection_rebuild.mark_many.call_count >= 2
    assert any('c' in call.args[1] for call in projection.record_projection_rebuild.mark_many.call_args_list)


@pytest.mark.asyncio
async def test_cleanup_batches_all_obligations_and_retains_them_on_failure(world):
    cache = projection.PusherAudioProjection('u')
    cache.close_debt.update(str(i) for i in range(128))
    cache.marker_retry['overflow'] = 1
    expected = cache.close_debt | {'overflow'}
    write = projection.record_projection_rebuild.mark_many
    write.side_effect = OSError('synthetic marker outage')
    await cache.persist_pending()
    assert cache.close_debt | set(cache.marker_retry) == expected
    assert all(call.args == ('u', expected) for call in write.call_args_list)
    write.side_effect = None
    await cache.persist_pending()
    assert not cache.close_debt and not cache.marker_retry


@pytest.mark.asyncio
async def test_all_close_markers_share_small_total_deadline(world, monkeypatch):
    import asyncio
    import time

    cache = projection.PusherAudioProjection('u')
    cache.close_debt.update(str(i) for i in range(128))
    monkeypatch.setattr(projection, 'MARKER_ATTEMPT_SECONDS', 0.02)
    monkeypatch.setattr(projection, 'MARKER_CLOSE_SECONDS', 0.05)

    async def stuck(*args):
        await asyncio.sleep(10)

    monkeypatch.setattr(projection, 'run_blocking', stuck)
    started = time.monotonic()
    await cache.persist_pending()
    assert time.monotonic() - started < 0.2
    assert len(cache.marker_retry) == 128
    # The independently bounded task also terminates, leaving no socket waiter.
    await cache.marker_task


@pytest.mark.asyncio
async def test_overflow_inventory_is_bounded_and_reports_failed_handoff(world, monkeypatch):
    cache = projection.PusherAudioProjection('u')
    monkeypatch.setattr(projection, 'MAX_MARKER_RETRIES', projection.MAX_CONVERSATIONS + 2)
    projection.record_projection_rebuild.mark_many.side_effect = OSError()
    assert await cache.defer_rebuild('one')
    assert await cache.defer_rebuild('two')
    assert not await cache.defer_rebuild('three')
    assert set(cache.marker_retry) == {'one', 'two'}
    await cache.persist_pending()
    assert set(cache.marker_retry) == {'one', 'two'}


def test_confirmed_empty_cold_discovery_is_distinct_from_privacy_deferral(world, monkeypatch):
    monkeypatch.setattr(full_projection, 'projection_owner_gone', lambda *_: False)
    write = MagicMock(side_effect=AssertionError('empty inventory must not write the conversation'))
    monkeypatch.setattr(projection.record_projection_rebuild, 'apply_projection', write)
    assert full_projection.rebuild('u', 'c') == 'no_objects'
    write.assert_not_called()
    assert not world.writes


@pytest.mark.asyncio
@pytest.mark.parametrize('empty', [False, True])
async def test_full_overflow_list_preserves_cached_close_debt_until_cleanup(world, monkeypatch, empty):
    cache = projection.PusherAudioProjection('u')
    cache.has_uploaded_paths = True
    cache.close_debt.add('cached')
    cache.marker_retry.update({str(i): i for i in range(128)})
    finish = (
        MagicMock(return_value=None)
        if empty
        else MagicMock(side_effect=projection.InvalidArgument('synthetic projection rejection'))
    )
    monkeypatch.setattr(cache, 'finish', finish)
    # Best-effort queue refusal cannot block close or discard the cached owner.
    assert await cache.finish_pending('cached', set(), set()) is True
    assert cache.close_debt == {'cached'}
    await cache.persist_pending()
    assert not cache.marker_retry and not cache.close_debt
    assert any('cached' in call.args[1] for call in projection.record_projection_rebuild.mark_many.call_args_list)


def test_full_discovery_names_its_cause_once_per_listing(world):
    def counts():
        return {cause: projection.FULL_DISCOVERIES.labels(cause=cause)._value.get() for cause in projection.FULL_CAUSES}

    def delta(before):
        return {cause: value - before[cause] for cause, value in counts().items() if value != before[cause]}

    cache = projection.PusherAudioProjection('u')
    before = counts()
    cache.refresh('c', [world.add(100)])
    assert delta(before) == {'no_inventory': 1}
    cache.refresh('c', [world.add(101)])  # incremental append pays no discovery
    assert delta(before) == {'no_inventory': 1}
    world.clock[0] += 300
    cache.refresh('c', [world.add(102)])
    assert delta(before) == {'no_inventory': 1, 'listing_expired': 1}
    cache.refresh('c', [world.add(50)])  # older than the cached tail needs listing order
    assert delta(before) == {'no_inventory': 1, 'listing_expired': 1, 'order_fallback': 1}
    world.conflict[0] = True
    cache.refresh('c', [world.add(103)])
    assert delta(before) == {'no_inventory': 1, 'listing_expired': 1, 'order_fallback': 1, 'cas_conflict': 1}
    cache.refresh('c', [world.add(104)], force=True)
    assert delta(before)['forced'] == 1
    assert len(world.lists) == sum(delta(before).values())
