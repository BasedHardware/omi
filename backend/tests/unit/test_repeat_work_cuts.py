"""Behavioral contracts for the three independent default-off repeat-work cuts."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config import repeat_work, sync_reprocess
from database import conversations
from models.structured import Structured
from utils.conversations import llm_input_dedupe as dedupe
from utils.other import storage
from utils.other.playback_identity import source_fingerprint
from utils.sync import repeat_work_metrics as metrics
from utils.sync.poll_limit import with_poll_hint


def chunks():
    return [
        dict(
            path=f'chunks/u/c/{1000+i*5}.pcm', timestamp=1000 + i * 5, generation='7', md5_hash=f'hash-{i}', size=160000
        )
        for i in range(2)
    ]


def test_stable_source_identity_and_changed_sources(monkeypatch):
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'true')
    source = chunks()
    first = conversations._finalize_audio_file_group('u', 'c', source, [])
    again = conversations._finalize_audio_file_group('u', 'c', source, [])
    assert first.id == again.id
    assert first.source_fingerprint == source_fingerprint(source)
    assert first.chunk_timestamps == [1000, 1005] and first.duration == 10
    assert conversations._finalize_audio_file_group('other', 'c', source, []).id != first.id
    assert source_fingerprint(list(reversed(source))) != first.source_fingerprint
    for key, value in [
        ('path', 'different.pcm'),
        ('generation', '8'),
        ('md5_hash', 'different'),
        ('timestamp', 1001),
        ('size', 160001),
        ('span', {'start': 1000, 'samples': 80000, 'sample_rate': 16000}),
    ]:
        changed = deepcopy(source)
        changed[0][key] = value
        assert source_fingerprint(changed) != first.source_fingerprint
    missing = chunks()
    missing[0].pop('generation')
    a = conversations._finalize_audio_file_group('u', 'c', missing, [])
    b = conversations._finalize_audio_file_group('u', 'c', missing, [])
    assert a.id != b.id and a.source_fingerprint is None
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    assert conversations._finalize_audio_file_group('u', 'c', source, []).id == first.id


@pytest.mark.parametrize(('enabled', 'source_identity'), [(False, False), (True, False), (False, True)])
def test_chunk_listing_checksums_only_when_requested(monkeypatch, enabled, source_identity):
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', str(enabled).lower())
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *_: False)
    blob = SimpleNamespace(
        name='chunks/u/c/1000.000.bin', size=160000, generation='7', md5_hash='md5', crc32c='crc', metadata=None
    )
    client = Mock()
    client.bucket.return_value.list_blobs.return_value = [blob]
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    expected = dict(timestamp=1000.0, path=blob.name, size=blob.size, is_batch=False, generation='7')
    if enabled or source_identity:
        expected.update(md5_hash='md5', crc32c='crc')
    assert storage.list_audio_chunks('u', 'c', source_identity=source_identity) == [expected]


@pytest.mark.parametrize('representation', ['file', 'conversation'])
def test_source_validation_drains_with_checksums_after_rollback(monkeypatch, representation):
    from utils.sync import playback

    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'true')
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *_: False)
    blob = SimpleNamespace(
        name='chunks/u/c/1000.000.bin', size=32000, generation='7', md5_hash='md5', crc32c='crc', metadata=None
    )
    client = Mock()
    client.bucket.return_value.list_blobs.return_value = [blob]
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    fingerprint = source_fingerprint(storage.list_audio_chunks('u', 'c'))
    assert fingerprint
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', lambda *a, **kw: b'\0' * 32000)
    if representation == 'file':
        assert playback.build_playback_artifact('u', 'c', [1000.0], source_fingerprint=fingerprint)
    else:
        files = [dict(id='stable', chunk_timestamps=[1000.0], source_fingerprint=fingerprint)]
        audio, spans = playback.build_conversation_playback_artifact('u', 'c', files, 1000.0, strict_sources=True)
        assert audio and spans


def test_background_updates_do_not_build_but_open_and_play_enqueue(monkeypatch):
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'true')
    enqueue = Mock()
    monkeypatch.setattr(storage, 'enqueue_audio_merge_job', enqueue)
    files = [{'id': 'stable', 'chunk_timestamps': [1000], 'source_fingerprint': 'source'}]
    storage.precache_conversation_audio('u', 'c', files)
    storage.enqueue_conversation_audio_merge('u', 'c', files, 'process_conversation')
    storage.enqueue_conversation_artifact_build('u', 'c', 'fp', 'sync_finalize')
    enqueue.assert_not_called()
    storage.enqueue_conversation_audio_merge('u', 'c', files, 'sync_download')
    storage.enqueue_conversation_artifact_build('u', 'c', 'fp', 'sync_urls')
    assert enqueue.call_count == 2
    assert all(call.args[0]['on_demand'] and call.args[0]['requested_at'] > 0 for call in enqueue.call_args_list)
    first = storage.compute_audio_files_fingerprint(files)
    assert first == storage.compute_audio_files_fingerprint(deepcopy(files))
    files[0]['chunk_timestamps'] = [999, 1000]  # Interior changes also invalidate.
    assert storage.compute_audio_files_fingerprint(files) != first


def test_demand_task_names_coalesce_and_recover_tombstones():
    from utils.cloud_tasks import _audio_merge_task_id

    old = dict(schema_version=2, conversation_id='c', fingerprint='source')
    demand = dict(old, on_demand=True, requested_at=3601)
    assert _audio_merge_task_id(old) != _audio_merge_task_id(demand)
    assert _audio_merge_task_id(demand) == _audio_merge_task_id(dict(demand, requested_at=3700))
    assert _audio_merge_task_id(demand) != _audio_merge_task_id(dict(demand, requested_at=7201))


def test_conversation_artifact_paths_are_immutable_per_fingerprint(monkeypatch):
    client = Mock()
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    bucket = client.bucket.return_value
    storage._conversation_playback_blob('u', 'c', 'fp-a')
    storage._conversation_playback_blob('u', 'c', 'fp-b')
    assert bucket.blob.call_args_list[0].args == ('playback/u/c/conversation-fp-a.mp3',)
    assert bucket.blob.call_args_list[1].args == ('playback/u/c/conversation-fp-b.mp3',)


def test_revision_mode_reuses_loaded_snapshot_without_firestore_reads(monkeypatch):
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    monkeypatch.setattr(conversations, 'get_conversation', Mock(side_effect=AssertionError('extra read')))
    monkeypatch.setattr(conversations, 'get_conversation_raw_snapshot', Mock(side_effect=AssertionError('extra read')))
    conv = SimpleNamespace(id='c', sync_content_revision=4, structured=Structured(title='old'), discarded=False)
    generate = Mock(return_value=Structured(title='Durable notes'))
    hashes = {}
    output = dedupe.notes('u', conv, {'transcript': 'Ship Friday'}, generate, hashes, language='en')
    conv.structured = output
    for name, value in hashes.items():
        setattr(conv, name, value)  # Simulate the existing durable payload commit.
    assert dedupe.notes('u', conv, {'transcript': 'Ship Friday'}, generate, {}, language='en') == output
    generate.assert_called_once()
    conv.sync_content_revision += 1
    dedupe.notes('u', conv, {'transcript': 'Ship Friday'}, generate, {}, language='en')
    assert generate.call_count == 2
    digest, matched = dedupe.l1_input('u', conv, {'owner': 'u', 'language': 'en'})
    assert not matched
    conv.l1_llm_input_hash = digest
    assert dedupe.l1_input('u', conv, {'owner': 'u', 'language': 'en'}) == (digest, True)
    monkeypatch.setenv('REPEAT_WORK_LLM_VERSION', 'next-model')
    assert not dedupe.l1_input('u', conv, {'owner': 'u', 'language': 'en'})[1]


def test_default_off_flags_are_independent(monkeypatch):
    for name in (
        'PLAYBACK_ON_DEMAND_ENABLED',
        'REPEAT_WORK_REVISION_ENABLED',
        'SYNC_POLL_BACKOFF_ENABLED',
        'SYNC_REPROCESS_COALESCE_ENABLED',
        'CONVERSATION_LLM_INPUT_DEDUPE_ENABLED',
    ):
        monkeypatch.delenv(name, raising=False)
    assert not repeat_work.playback_on_demand() and not repeat_work.revision_reuse() and not repeat_work.poll_backoff()
    assert not sync_reprocess.coalesce_enabled() and not sync_reprocess.dedupe_enabled()
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    assert sync_reprocess.coalesce_enabled() and sync_reprocess.dedupe_enabled()
    assert not repeat_work.playback_on_demand() and not repeat_work.poll_backoff()


def test_poll_hint_uses_only_response_state_and_surface_demand(monkeypatch):
    row = {'status': 'queued', 'job_id': 'j'}
    monkeypatch.delenv('SYNC_POLL_BACKOFF_ENABLED', raising=False)
    assert with_poll_hint(row) is row
    monkeypatch.setenv('SYNC_POLL_BACKOFF_ENABLED', 'true')
    assert with_poll_hint(row)['poll_after_ms'] == 60000
    assert with_poll_hint(row, surface_open=True)['poll_after_ms'] == 20000
    assert with_poll_hint({'status': 'processing'})['poll_after_ms'] == 20000
    for state in ['completed', 'failed', 'partial_failure']:
        assert with_poll_hint({'status': state})['poll_after_ms'] == 0
    assert row == {'status': 'queued', 'job_id': 'j'}


def test_call_join_is_content_free_scoped_and_counts_actual_callbacks(monkeypatch, caplog):
    from langchain_core.outputs import LLMResult
    from utils.llm.usage_tracker import LLMUsageCallback

    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    caplog.set_level('INFO', logger=metrics.__name__)
    handler = LLMUsageCallback()
    conv = SimpleNamespace(id='secret-conversation-id', sync_content_revision=5, transcript='DO NOT LOG THIS')

    @metrics.conversation_scope
    def process(uid, conversation):
        handler.on_llm_end(LLMResult(generations=[]))
        handler.on_llm_error(RuntimeError('DO NOT LOG ERROR CONTENT'))
        metrics.record_final(uid, conversation)

    before = metrics.CALLS.labels('completed')._value.get()
    process('secret-uid', conv)
    handler.on_llm_end(LLMResult(generations=[]))  # Outside scope: no join.
    assert metrics.CALLS.labels('completed')._value.get() - before == 1
    assert len(caplog.records) == 3
    assert 'conversation_key=' in caplog.text and 'revision=5' in caplog.text
    assert 'secret-' not in caplog.text and 'DO NOT LOG' not in caplog.text
    assert 'secret' not in str(metrics.CALLS.collect())


def test_source_replacement_during_build_is_rejected():
    from utils.other.playback_identity import validate_sources

    original = chunks()
    files = [{'chunk_timestamps': [1000, 1005], 'source_fingerprint': source_fingerprint(original)}]
    validate_sources(files, original)
    replaced = deepcopy(original)
    replaced[0]['generation'] = '8'
    with pytest.raises(RuntimeError, match='source manifest changed'):
        validate_sources(files, replaced)
    with pytest.raises(RuntimeError, match='source manifest changed'):
        validate_sources(files, original[:1])


def test_pre_projection_stamp_survives_raw_entries_under_colliding_keys():
    from utils.other.playback_identity import resolve_sources

    stamped = chunks()
    af = {'chunk_timestamps': [1000, 1005], 'source_fingerprint': source_fingerprint(stamped)}
    whole_pack = dict(
        path='raw-live/u/c/1000.000.opus',
        timestamp=1000,
        generation='9',
        size=8192,
        span={'start': 1000, 'samples': 80000, 'sample_rate': 16000},
        raw_end=1005,
        pcm_sha256='p',
    )
    split_fragment = {**whole_pack, 'path': 'raw-live/u/c/1005.000.opus', 'timestamp': 1005, 'raw_source_start': 1005}
    projected = [dict(stamped[0]), whole_pack, dict(stamped[1]), split_fragment]
    resolved = resolve_sources(af, projected)
    assert [chunk['path'] for chunk in resolved] == ['chunks/u/c/1000.pcm', 'chunks/u/c/1005.pcm']


def test_pre_projection_stamp_still_refuses_when_encoded_core_changed():
    from utils.other.playback_identity import validate_sources

    stamped = chunks()
    af = {'chunk_timestamps': [1000, 1005], 'source_fingerprint': source_fingerprint(stamped)}
    whole_pack = dict(
        path='raw-live/u/c/1000.000.opus',
        timestamp=1000,
        generation='9',
        size=8192,
        raw_end=1005,
        pcm_sha256='p',
    )
    drifted = [deepcopy(stamped[0]), {**stamped[1], 'generation': '8'}, whole_pack]
    with pytest.raises(RuntimeError, match='source manifest changed'):
        validate_sources([af], drifted)


def test_initial_generation_calls_join_the_chosen_durable_id(monkeypatch, caplog):
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    caplog.set_level('INFO', logger=metrics.__name__)

    @metrics.conversation_scope
    def process(uid, conversation):
        metrics.bind_generation(uid, 'generated-c')
        metrics.record_llm_call('completed', 'conv_structure')
        metrics.record_feature(uid, conversation, 'notes', 'invoked')
        metrics.record_final(uid, SimpleNamespace(id='generated-c', sync_content_revision=None))

    process('u', SimpleNamespace())
    assert len(caplog.records) == 3
    keys = {record.message.split('conversation_key=')[1].split()[0] for record in caplog.records}
    assert len(keys) == 1
    assert 'feature=notes' in caplog.text
    assert metrics._scope.get() is None


@pytest.fixture(scope='module')
def sync_router_module():
    from routers import sync

    return sync


@pytest.mark.asyncio
@pytest.mark.parametrize(('schema', 'surface'), [(1, 'urls'), (2, 'urls'), (1, 'precache'), (1, 'download')])
async def test_deferred_eager_task_survives_tombstone_and_builds_after_rollback(
    monkeypatch, sync_router_module, schema, surface
):
    from copy import deepcopy
    from utils import cloud_tasks

    sync = sync_router_module
    files = [dict(id='legacy-file', chunk_timestamps=[1000.0])]
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    fingerprint = storage.compute_audio_files_fingerprint(files)
    row = dict(started_at=1000.0, audio_files=files)
    payload = dict(uid='u', conversation_id='c', schema_version=schema)
    payload.update(
        dict(fingerprint=fingerprint) if schema == 2 else dict(audio_file_id='legacy-file', timestamps=[1000.0])
    )
    queued, reserved = {}, set()

    def enqueue(_queue, _url, name, body, **kwargs):
        if name not in reserved:  # Cloud Tasks AlreadyExists is success, even after acknowledgement.
            reserved.add(name)
            queued[name] = (deepcopy(body), kwargs)

    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    stamp = Mock(side_effect=lambda u, c, epoch: row.update(playback_eager_epoch=epoch) or True)
    monkeypatch.setattr(sync.conversations_db, 'mark_playback_deferred', stamp, raising=False)
    monkeypatch.setattr(sync, 'try_acquire_job_run_lock', lambda *_: 'lock')
    monkeypatch.setattr(sync, 'release_job_run_lock', lambda *_: None)
    monkeypatch.setattr(sync, 'should_skip_background_account_mutation', lambda *_: False)
    monkeypatch.setattr(sync.conversations_db, 'get_conversation', lambda *_: row)
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', lambda u, c, data: row.update(data) or True)
    monkeypatch.setattr(sync, 'get_playback_artifact_signed_url', lambda *_: None)
    monkeypatch.setattr(sync, 'get_conversation_playback_signed_url', lambda *a, **kw: None)
    file_build = Mock(return_value=b'MP3')
    conversation_build = Mock(return_value=(b'MP3', [dict(file_id='legacy-file', len=1.0, wall_offset=0.0)]))
    monkeypatch.setattr(sync.sync_playback, 'build_playback_artifact', file_build)
    monkeypatch.setattr(sync.sync_playback, 'build_conversation_playback_artifact', conversation_build)
    upload = Mock()
    monkeypatch.setattr(sync, 'upload_playback_artifact', upload)
    monkeypatch.setattr(sync.playback_build, 'get_conversation_playback_manifest', lambda *_: None)
    monkeypatch.setattr(sync.playback_build, 'build_conversation_playback_artifact', conversation_build)
    monkeypatch.setattr(sync.playback_build, 'upload_conversation_playback_artifact', upload)
    cloud_tasks.enqueue_audio_merge_job(payload)
    eager_name = next(iter(queued))
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'true')
    delivered, _ = queued.pop(eager_name)
    response = await sync.run_audio_merge_job(SimpleNamespace(json=AsyncMock(return_value=delivered)), 0)
    assert response.status_code == 200 and b'deferred_until_playback' in response.body
    assert row.get('playback_eager_epoch')  # Recovery survives the acknowledgement and its tombstone.
    assert not queued  # No recurring queue delivery while enabled.
    stamp.assert_called_once()
    file_build.assert_not_called()
    conversation_build.assert_not_called()
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    cloud_tasks.enqueue_audio_merge_job(payload)  # AlreadyExists cannot recreate the old eager task.
    assert not queued
    playback = sync.sync_playback
    monkeypatch.setattr(playback, 'get_playback_artifact_signed_url', lambda *_: None)
    monkeypatch.setattr(playback, 'get_merged_audio_signed_url', lambda *_: None)
    monkeypatch.setattr(playback, 'is_playback_unavailable', lambda *_: False)
    monkeypatch.setattr(playback, 'get_conversation_playback_signed_url', lambda *a, **kw: None)
    monkeypatch.setattr(playback, 'get_conversation_playback_unavailable_fingerprint', lambda *_: None)
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: True)
    monkeypatch.setattr(playback, 'download_playback_artifact', lambda *_: None)

    def request_playback():
        if surface == 'precache':
            return sync.precache_conversation_audio_endpoint('c', 'u')
        if surface == 'download':
            return sync.download_audio_file_endpoint('c', 'legacy-file', SimpleNamespace(headers={}), 'wav', 'u')
        return playback._get_audio_urls_via_artifacts('u', 'c', files, row)

    request_playback()
    fresh_name = cloud_tasks._audio_merge_task_id({**payload, 'playback_epoch': row['playback_eager_epoch']})
    assert fresh_name != eager_name and fresh_name in queued
    count = len(queued)
    request_playback()
    assert len(queued) == count  # Concurrent readers share the persisted recovery namespace.
    delivered, _ = queued.pop(fresh_name)
    response = await sync.run_audio_merge_job(SimpleNamespace(json=AsyncMock(return_value=delivered)), 0)
    assert response.status_code == 200 and b'done' in response.body
    (conversation_build if schema == 2 else file_build).assert_called_once()
    upload.assert_called_once()
    if schema == 2:
        assert row['conversation_audio']['audio_files_fingerprint'] == storage.compute_audio_files_fingerprint(
            files, origin=row['started_at'], source_identity=True
        )


@pytest.mark.asyncio
async def test_eager_deferral_stamp_failure_keeps_original_task_retryable(monkeypatch, sync_router_module):
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'true')
    stamp = Mock(side_effect=RuntimeError('synthetic write failure'))
    monkeypatch.setattr(sync_router_module.conversations_db, 'mark_playback_deferred', stamp, raising=False)
    request = SimpleNamespace(json=AsyncMock(return_value=dict(schema_version=2, uid='u', conversation_id='c')))
    response = await sync_router_module.run_audio_merge_job(request, 0)
    assert response.status_code == 503
    stamp.assert_called_once()


def test_flag_off_reader_reuses_matching_demand_stamp(monkeypatch):
    from utils.sync import playback

    files = [dict(id='unchanged-id', chunk_timestamps=[1000.0], source_fingerprint='source')]
    row = dict(started_at=1000.0, audio_files=files)
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'true')
    fingerprint = storage.compute_audio_files_fingerprint(files, origin=1000.0)
    row['conversation_audio'] = dict(audio_files_fingerprint=fingerprint, spans=[], duration=1, captured_duration=1)
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    signed = Mock(return_value='demand-artifact')
    enqueue = Mock()
    monkeypatch.setattr(playback, 'get_conversation_playback_signed_url', signed)
    monkeypatch.setattr(playback, 'get_conversation_playback_unavailable_fingerprint', lambda *_: None)
    monkeypatch.setattr(playback, 'enqueue_conversation_artifact_build', enqueue)
    assert playback._conversation_audio_urls_entry('u', 'c', files, row)['status'] == 'cached'
    signed.assert_called_once_with('u', 'c', fingerprint=fingerprint)
    enqueue.assert_not_called()
    signed.return_value = None
    assert playback._conversation_audio_urls_entry('u', 'c', files, row)['status'] == 'pending'
    enqueue.assert_called_once_with(
        'u', 'c', storage.compute_audio_files_fingerprint(files), caller='sync_urls', playback_epoch=fingerprint
    )


@pytest.mark.parametrize('outcome', ['written', 'missing', 'failed'])
def test_playback_recovery_marker_is_update_only_without_a_read(monkeypatch, outcome):
    from google.api_core.exceptions import NotFound

    client, ref = Mock(), Mock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value = ref
    monkeypatch.setattr(conversations, 'db', client)
    ref.get.side_effect = AssertionError('must not add a Firestore read')
    if outcome == 'missing':
        ref.update.side_effect = NotFound('gone')
    elif outcome == 'failed':
        ref.update.side_effect = RuntimeError('write failed')
    if outcome == 'failed':
        with pytest.raises(RuntimeError):
            conversations.mark_playback_deferred('u', 'c', 'opaque-epoch')
    else:
        assert conversations.mark_playback_deferred('u', 'c', 'opaque-epoch') is (outcome == 'written')
    ref.update.assert_called_once_with({'playback_eager_epoch': 'opaque-epoch'})
    ref.get.assert_not_called()
    ref.set.assert_not_called()


@pytest.mark.asyncio
async def test_demand_worker_drains_after_flag_rollback_and_reuses_same_artifact(monkeypatch, sync_router_module):
    sync = sync_router_module

    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    row = {
        'started_at': 1000.0,
        'audio_files': [{'id': 'stable', 'chunk_timestamps': [1000.0], 'source_fingerprint': 'source'}],
    }
    digest = storage.compute_audio_files_fingerprint(row['audio_files'], origin=1000.0, source_identity=True)
    payload = dict(uid='u', conversation_id='c', fingerprint=digest, on_demand=True, requested_at=1)
    monkeypatch.setattr(sync, 'try_acquire_job_run_lock', lambda *_: 'lock')
    monkeypatch.setattr(sync, 'release_job_run_lock', lambda *_: None)
    monkeypatch.setattr(sync, 'should_skip_background_account_mutation', lambda *_: False)
    monkeypatch.setattr(sync.conversations_db, 'get_conversation', lambda *_: row)
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', lambda u, c, data: row.update(data) or True)
    build = Mock(return_value=(b'MP3', [{'file_id': 'stable', 'len': 2.0, 'wall_offset': 0.0}]))
    upload = Mock()
    monkeypatch.setattr(sync.sync_playback, 'build_conversation_playback_artifact', build)
    monkeypatch.setattr(sync.playback_build, 'get_conversation_playback_manifest', lambda *_: None)
    monkeypatch.setattr(sync.playback_build, 'build_conversation_playback_artifact', build)
    monkeypatch.setattr(sync.playback_build, 'upload_conversation_playback_artifact', upload)
    monkeypatch.setattr(sync, 'get_conversation_playback_signed_url', lambda *a, **kw: 'cached')
    assert (await sync._run_conversation_merge_job(payload, 0)).status_code == 200
    build.assert_called_once_with('u', 'c', row['audio_files'], 1000.0, strict_sources=True)
    assert upload.call_args.args[3] == digest
    assert upload.call_args.kwargs == {'spans': row['conversation_audio']['spans']}
    assert row['conversation_audio']['audio_files_fingerprint'] == digest
    again = await sync._run_conversation_merge_job(payload, 0)
    assert b'exists' in again.body
    build.assert_called_once()


def test_client_aliases_resolve_to_current_source_without_reusing_old_artifact(sync_router_module, monkeypatch):
    from utils.other.playback_identity import retain_aliases

    previous = [{'id': 'old', 'chunk_timestamps': [1000], 'legacy_ids': ['older']}]
    current = [{'id': 'current', 'chunk_timestamps': [1000, 1005], 'source_fingerprint': 'changed'}]
    result = retain_aliases(current, previous)
    assert result[0]['legacy_ids'] == ['older', 'old']
    assert 'legacy_ids' not in current[0]  # No mutation of the caller's manifest.
    sync = sync_router_module
    monkeypatch.setattr(sync.conversations_db, 'get_conversation', lambda *_: {'audio_files': result})
    download = Mock(return_value='response')
    monkeypatch.setattr(sync.sync_playback, 'download_audio_file_response', download)
    request = SimpleNamespace(headers={})
    assert sync.download_audio_file_endpoint('c', 'older', request, 'wav', 'u') == 'response'
    assert download.call_args.args[2] == 'current'


def test_inline_requests_share_one_build_with_only_playback_flag(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from utils.other import audio_singleflight

    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'true')
    monkeypatch.setattr(audio_singleflight, 'admitted', lambda *_: False)
    entered, finish, joined = Event(), Event(), Event()
    counter = Mock()
    monkeypatch.setattr(audio_singleflight.REBUILDS_COALESCED, 'inc', joined.set)

    @audio_singleflight.coalesce_rebuild
    def build(uid, conversation_id, source):
        counter()
        entered.set()
        assert finish.wait(2)
        return source

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(build, 'u', 'c', 'same-source')
        assert entered.wait(2)
        second = pool.submit(build, 'u', 'c', 'same-source')
        assert joined.wait(2)
        finish.set()
        assert first.result() == second.result() == 'same-source'
    counter.assert_called_once()
