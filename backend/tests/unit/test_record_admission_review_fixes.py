"""Review regressions: zero dark-path IO, refreshed ownership, field-only writes."""

import asyncio

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.batch_pipeline import RecordOwnerContention
from config.policy import BatchUnitPolicy
from database.batch_pipeline_intake import admit
from database.batch_pipeline_store import FirestoreTransaction
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline import live, live_upload, serving
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.conversations import finalizer, transcription_shadow as shadow
from utils.conversations.processing_trigger import ProcessingTrigger


@pytest.fixture(autouse=True)
def explicit_stage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')


def forbidden(*args, **kwargs):
    raise AssertionError('dark unowned path performed record ownership IO')


@pytest.mark.parametrize('cid,session', [('record', None), (None, 'session')])
@pytest.mark.parametrize('snapshot', [None, {'record_lane_owner': None}])
async def test_dark_named_sync_does_not_construct_store_read_or_claim(monkeypatch, cid, session, snapshot):
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    monkeypatch.setattr(live_upload, 'FirestoreStore', forbidden)
    monkeypatch.setattr(live_upload, 'claim_record_lane_owner', forbidden)
    assert (
        await live_upload.registered_record_response(
            uid='synthetic',
            conversation_id=cid,
            recording_session_id=session,
            content_id='wal',
            paths=[],
            source='omi',
            client_device_id=None,
            loaded_conversation=snapshot,
        )
        is None
    )


async def test_owned_byok_refusal_is_terminal_without_source_reads(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: SimpleNamespace())
    response = await live_upload.registered_record_response(
        uid='synthetic',
        conversation_id='record',
        content_id='wal',
        paths=[],
        source='omi',
        client_device_id=None,
        byok_enabled=True,
        loaded_conversation={'record_lane_owner': 'batch_live_v1'},
    )
    assert response.status_code == 409
    assert 'retry-after' not in response.headers


@pytest.mark.parametrize('enabled', [False, True])
async def test_serving_tick_drains_admitted_recordings_after_admission_rollback(monkeypatch, enabled):
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', str(enabled).lower())
    service = SimpleNamespace(store=object())
    monkeypatch.setattr(serving, 'serving_for_stage', lambda *_: service)
    monkeypatch.setattr(serving, 'start_background_task', lambda coro, **kwargs: coro)
    drain = AsyncMock()
    monkeypatch.setattr(serving, 'drain_recordings', drain)
    stop, coro = serving.start_serving_from_env()
    reconcile = AsyncMock(side_effect=lambda **kwargs: stop.set())
    service.reconcile_async = reconcile
    await asyncio.wait_for(coro, timeout=1)
    reconcile.assert_awaited_once_with(recover_quarantine=True, periodic=True)
    assert drain.await_count == 1  # Discovery must retain already-admitted work after rollback.


def test_dark_legacy_shadow_uses_its_existing_read_without_claim_or_reload(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    read = Mock(return_value={'id': 'record'})
    monkeypatch.setattr(shadow.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(shadow.conversations_db, 'claim_record_lane_owner', forbidden)
    monkeypatch.setattr(shadow, 'deserialize_conversation', lambda raw: SimpleNamespace(audio_files=[object()]))
    monkeypatch.setattr(shadow, '_enabled', lambda *_: True)
    monkeypatch.setattr(shadow, '_reserve_budget', lambda *_: 'duplicate')
    shadow._run_shadow('synthetic', 'record')
    assert read.call_count == 1


@pytest.mark.parametrize('winner', [None, 'legacy_final_pass_v1', 'batch_live_v1', 'batch_sync_v1'])
def test_shadow_reloads_failed_cas_and_retries_only_when_needed(monkeypatch, winner):
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    refreshed = {'id': 'record', 'record_lane_owner': winner, 'updated_at': 2}
    read = Mock(return_value=refreshed)
    claim = Mock(side_effect=[None, 3])
    monkeypatch.setattr(shadow.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(shadow.conversations_db, 'claim_record_lane_owner', claim)
    result = shadow._claim_shadow_owner('synthetic', 'record', {'id': 'record', 'updated_at': 1})
    assert read.call_count == 1
    if winner in {'batch_live_v1', 'batch_sync_v1'}:
        assert result is None and claim.call_count == 1
    else:
        assert result['record_lane_owner'] == 'legacy_final_pass_v1'
        assert claim.call_count == (2 if winner is None else 1)
        assert result['updated_at'] == (3 if winner is None else 2)
        if winner is None:
            assert claim.call_args.args[-1] == 2


def test_shadow_contention_is_bounded_and_explicitly_retryable(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    read, claim = Mock(return_value={'updated_at': 2}), Mock(return_value=None)
    monkeypatch.setattr(shadow.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(shadow.conversations_db, 'claim_record_lane_owner', claim)
    with pytest.raises(RecordOwnerContention):
        shadow._claim_shadow_owner('synthetic', 'record', {'updated_at': 1})
    assert read.call_count == claim.call_count == 3


@pytest.mark.parametrize('already_owned', [False, True])
def test_admission_only_patches_missing_owner_and_never_sets_conversation(monkeypatch, already_owned):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    store = MemoryStore()
    original = {
        'id': 'record',
        'transcript_segments': 'opaque-canonical-payload',
        'manual_speaker_assignments': {'v': 1},
    }
    if already_owned:
        original['record_lane_owner'] = 'batch_sync_v1'
    store.rows['conversations', 'synthetic/record'] = original.copy()
    patches, puts = [], []
    original_put, original_patch = MemoryTransaction.put, MemoryTransaction.patch

    def put(self, table, key, value):
        assert table != 'conversations'
        puts.append(table)
        original_put(self, table, key, value)

    def patch(self, table, key, fields):
        patches.append((table, key, fields))
        original_patch(self, table, key, fields)

    monkeypatch.setattr(MemoryTransaction, 'put', put)
    monkeypatch.setattr(MemoryTransaction, 'patch', patch)
    work = replace(item('unit', owner='synthetic'), privacy_generation=0)
    binding = ProjectionBinding(
        'synthetic', 'bp_record', 'content', ('unit',), target_conversation_id='record', record_origin=True
    )
    assert admit(store, [work], binding, 0, namespace='batch_pipeline_test_review')['outcome'] == 'batch'
    assert patches == (
        [] if already_owned else [('conversations', 'synthetic/record', {'record_lane_owner': 'batch_sync_v1'})]
    )
    assert store.rows['conversations', 'synthetic/record'] == {**original, 'record_lane_owner': 'batch_sync_v1'}


def test_firestore_flush_uses_update_for_owner_and_preserves_canonical_payload():
    client = StrictFirestore()
    path = ('users', 'synthetic', 'conversations', 'record')
    client.rows[path] = {'transcript_segments': 'opaque-canonical-payload', 'manual_edit': 'preserved'}
    tx = client.transaction()
    view = FirestoreTransaction(client, 'batch_pipeline_test_review', tx)
    assert view.get('conversations', 'synthetic/record')['manual_edit'] == 'preserved'
    view.patch('conversations', 'synthetic/record', {'record_lane_owner': 'batch_sync_v1'})
    view.flush()
    assert tx.updates == [(path, {'record_lane_owner': 'batch_sync_v1'})]
    assert client.rows[path]['transcript_segments'] == 'opaque-canonical-payload'
    with pytest.raises(ValueError, match='never a document set'):
        view.put('conversations', 'synthetic/record', {})


@pytest.mark.parametrize('busy', [False, True])
async def test_finalizer_reloads_contention_inside_attempt_and_defers_without_budget(monkeypatch, busy):
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    rows = [
        {'id': 'record', 'status': 'processing', 'updated_at': n, 'private_cloud_sync_enabled': True, 'language': 'en'}
        for n in range(1, 5)
    ]
    read = Mock(side_effect=rows)
    claim = Mock(return_value=None) if busy else Mock(side_effect=[None, 9])
    defer = Mock(return_value=True)
    monkeypatch.setattr(finalizer.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(live, 'claim_record_lane_owner', claim)
    monkeypatch.setattr(finalizer.finalization_jobs_db, 'mark_finalization_retryable', defer)
    monkeypatch.setattr(
        finalizer, 'deserialize_conversation', lambda row: SimpleNamespace(id='record', status='processing')
    )
    disposition, row, model = await finalizer._load_admitted_conversation(
        'synthetic', 'record', 'job', 2, 4, ProcessingTrigger.CAPTURE_END
    )
    if busy:
        assert disposition == finalizer.ConversationFinalizationDisposition.deferred
        assert row is model is None
        defer.assert_called_once_with('job', 2, 4, 'record_owner_contention', count_attempt=False)
        assert read.call_count == 4 and claim.call_count == 3
    else:
        assert disposition is None and row['updated_at'] == 9
        assert model.record_lane_owner == 'batch_live_v1'
        assert read.call_count == claim.call_count == 2
        defer.assert_not_called()


@pytest.mark.parametrize(
    'conversation_language,user_language,source,live_record,expected',
    [
        # Blank conversation language falls back to the user's, as the escape does.
        ('', 'en', 'desktop', True, True),
        (None, 'de-DE', 'desktop', True, True),
        ('en', None, 'desktop', True, True),
        ('', '', 'desktop', True, None),  # no language at all keeps the legacy route
        ('', 'vi', 'desktop', True, None),
        ('vi', 'en', 'desktop', True, None),  # a set conversation language wins over the user's
        ('', 'en', 'omi', True, False),  # only desktop uploads are record-origin
        ('', 'en', 'desktop', False, False),  # and only with the live record lane on
    ],
)
async def test_desktop_record_origin_uses_the_escape_language(
    monkeypatch, conversation_language, user_language, source, live_record, expected
):
    from utils.batch_pipeline import intake
    from utils.batch_pipeline.artifacts import ProtectionContext
    from utils.batch_pipeline.audio import audio_unit

    bindings = []
    store = MemoryStore()
    store.namespace = 'batch_pipeline_dev'

    def authorize(store_, seed, snapshots):
        snapshots['user'] = {'language': user_language} if user_language else {}
        snapshots['conversations'] = {'record': {'id': 'record', 'language': conversation_language}}
        return ProtectionContext('standard', 0)

    def capture_admit(store_, items, binding, now, **kwargs):
        bindings.append(binding)
        return {'outcome': 'in_progress', 'job_id': 'job'}

    def decode_units(paths, max_seconds):
        yield audio_unit(100, b'\x00\x00' * 1600)

    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(
        intake, 'provider_config', lambda: SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=600)
    )
    monkeypatch.setattr(intake, 'decode_units', decode_units)
    monkeypatch.setattr(intake, 'artifacts_for', lambda store_: SimpleNamespace(stage_audio=lambda w, b: 'uri'))
    monkeypatch.setattr(intake, 'admit', capture_admit)
    outcome = await intake.accept_upload(
        uid='synthetic-owner',
        job_id='job',
        content_id='content',
        paths=['a.bin'],
        lane='fresh',
        recording_age_seconds=60,
        source=source,
        should_lock=False,
        conversation_id='record',
        client_device_id='mac-1',
        client_platform='macos',
        policy=BatchUnitPolicy(
            batch_enabled=True, live_record_enabled=live_record
        ),  # integration intake uses dataclasses.replace (contract (c))
    )
    if expected is None:
        assert outcome is None and not bindings
    else:
        assert outcome is not None and len(bindings) == 1 and bindings[0].record_origin is expected
