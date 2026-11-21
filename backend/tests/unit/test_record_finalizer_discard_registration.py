"""Intentional relevance discards retain the finalizer's existing terminal fence."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.policy import BatchUnitPolicy
from config.record_audio import record_identity
from database import batch_pipeline_privacy, batch_pipeline_store
from database import conversation_finalization_jobs as jobs_db
from database import conversations as conversations_db
from database.batch_pipeline_store import FirestoreStore
from models.conversation_enums import ConversationStatus
from routers import conversation_finalization as finalization_router
from utils.batch_pipeline import live
from utils.conversations import finalizer
from utils.conversations import demand_processing
from utils.conversations import lifecycle
from utils.conversations.processing_trigger import ProcessingTrigger
from tests.unit.test_conversation_smart_merge_finalizer import harness, _Conversation, _JOB, _finalize
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.mark.asyncio
@pytest.mark.parametrize('initial_discarded,processed_discarded', [(False, True), (True, False)])
async def test_processing_registration_uses_persisted_discard_result(
    harness, monkeypatch, initial_discarded, processed_discarded
):
    calls, row = harness
    row.update(record_lane_owner='batch_live_v1', status='processing', discarded=initial_discarded)
    durable = dict(row)
    conversation = _Conversation()
    conversation.status = ConversationStatus.processing
    conversation.discarded = initial_discarded
    conversation.model_dump = lambda: {
        'id': 'n',
        'status': conversation.status,
        'discarded': conversation.discarded,
    }

    def deserialize(data):
        if isinstance(data, dict):
            conversation.status = data.get('status', conversation.status)
            conversation.discarded = data.get('discarded', conversation.discarded)
        return conversation

    monkeypatch.setattr(finalizer, 'deserialize_conversation', deserialize)
    before = finalizer.RECORD_REGISTER_REFUSED._value.get()
    original = finalizer.run_blocking

    async def no_wait(*args, **kwargs):
        return 'not_applicable'

    async def absorbed(*args, **kwargs):
        return True

    async def run(executor, function, *args, **kwargs):
        if function is finalizer.process_with_episode_budget:
            conversation.status = ConversationStatus.completed
            conversation.discarded = processed_discarded
            durable.update(status='completed', discarded=processed_discarded)
            kwargs['persistence_observer'](True)
            return conversation
        if function is finalizer.register_recording:
            calls.append(function)
            assert args[1]['discarded'] is processed_discarded
            # The real registrar refuses intentional discard before opening a store.
            if processed_discarded:
                return function(*args, **kwargs)
            return True
        if function is finalizer.lifecycle_service.claim_finalization_fanout:
            calls.append(function)
            admitted = jobs_db._conversation_admits_fanout(durable, _JOB, 'job')  # pyright: ignore[reportPrivateUsage]
            return {'status': 'claimed' if admitted else 'fenced', 'fanout_key': 'key'}
        return await original(executor, function, *args, **kwargs)

    monkeypatch.setattr(finalizer, 'await_meeting_evidence', no_wait)
    monkeypatch.setattr(finalizer, 'warm_rollout_cohorts', no_wait)
    monkeypatch.setattr(finalizer, '_maybe_start_shadow', lambda *_: None)
    monkeypatch.setattr(finalizer, 'smart_merge_step', absorbed)
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', no_wait)
    monkeypatch.setattr(finalizer, 'schedule_person_voice_learning_retry', lambda *_: None)
    monkeypatch.setattr(finalizer, 'run_blocking', run)
    expected = (
        finalizer.ConversationFinalizationDisposition.fenced
        if processed_discarded
        else finalizer.ConversationFinalizationDisposition.completed
    )
    assert await _finalize() is expected
    assert durable['discarded'] is processed_discarded  # Persistence, not the stale initial read, is authoritative.
    assert finalizer.lifecycle_service.claim_finalization_fanout in calls
    assert (finalizer.register_recording in calls) is not processed_discarded
    assert (finalizer.lifecycle_service.complete_finalization_fanout in calls) is not processed_discarded
    assert finalizer.link_duplicate_captures not in calls
    assert finalizer.RECORD_REGISTER_REFUSED._value.get() == before


@pytest.mark.asyncio
@pytest.mark.parametrize('has_audio', [False, True])
async def test_discarded_server_batch_fast_path_terminalizes_once_without_registration(
    harness, monkeypatch, caplog, has_audio
):
    calls, row = harness
    row.update(
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        discarded=True,
        has_content=has_audio,
        server_batch_audio_start=0,
        server_batch_audio_end=10,
        server_batch_audio_closed=True,
        audio_files=['retained-audio'],
    )
    retained = dict(row)
    conversation = _Conversation()
    conversation.discarded = True
    conversation.transcript_segments = []
    conversation.photos = []
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _: conversation)

    async def inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    client = StrictFirestore()
    job_path = (jobs_db.FINALIZATION_JOBS_COLLECTION, 'job')
    client.rows[job_path] = {**_JOB, 'fanout_status': 'pending'}
    job = client.rows[job_path]
    monkeypatch.setattr(jobs_db, 'get_firestore_client', lambda: client)
    original_run = finalizer.run_blocking

    async def run(executor, function, *args, **kwargs):
        if function is finalizer.lifecycle_service.complete_discarded_server_batch_fanout:
            return function(*args, **kwargs)
        return await original_run(executor, function, *args, **kwargs)

    monkeypatch.setattr(finalizer, 'run_blocking', run)

    def claim(*args, **kwargs):
        if job['status'] == 'completed':
            return {'status': 'completed'}
        return {'status': 'claimed', 'lease_epoch': 1, 'attempt_count': 0}

    terminal = MagicMock()
    client_terminal = MagicMock()
    retry = AsyncMock()
    monkeypatch.setattr(finalization_router, 'run_blocking', inline)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda _: 'lock')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda *_: None)
    monkeypatch.setattr(finalization_router, 'account_deletion_blocks_user_work', lambda _: False)
    monkeypatch.setattr(finalization_router, 'should_skip_background_account_mutation', lambda _: False)
    monkeypatch.setattr(demand_processing, 'admit', lambda *args, **kwargs: True)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', claim)
    monkeypatch.setattr(jobs_db, 'get_finalization_job', lambda _: job)
    monkeypatch.setattr(finalization_router, 'record_capture_finalization_terminal', terminal)
    monkeypatch.setattr(finalization_router, 'record_conversation_finalization_client_terminal', client_terminal)
    monkeypatch.setattr(finalization_router, '_retry_or_dead_letter', retry)
    request = SimpleNamespace(json=AsyncMock(return_value={'job_id': 'job', 'dispatch_generation': 1}))

    with caplog.at_level('INFO', logger=finalizer.logger.name):
        first = await finalization_router.run_listen_finalization_job(request, task_retry_count=0)
        replay = await finalization_router.run_listen_finalization_job(request, task_retry_count=0)

    assert first.status_code == replay.status_code == 200
    assert json.loads(first.body) == {'status': 'done'}
    assert json.loads(replay.body) == {'status': 'acked', 'job_status': 'completed'}
    assert client.rows[job_path]['status'] == 'completed'
    assert client.rows[job_path]['fanout_status'] == 'completed'
    assert client.rows[job_path]['terminal_outcome'] == 'success'
    terminal.assert_called_once_with('success', None)
    client_terminal.assert_called_once_with('success', job)
    retry.assert_not_called()
    assert calls.count(finalizer.conversations_db.get_conversation) == 1
    assert finalizer.register_recording not in calls
    assert finalizer.lifecycle_service.delete_empty_recording_conversation not in calls
    assert finalizer.lifecycle_service.complete_server_batch_capture not in calls
    assert finalizer.process_with_episode_budget not in calls
    assert row == retained
    assert [record.getMessage() for record in caplog.records if 'outcome=discarded' in record.getMessage()] == [
        'event=server_batch_finalization outcome=discarded'
    ]


@pytest.mark.asyncio
async def test_discarded_fast_path_retries_when_fanout_completion_is_refused(harness, monkeypatch):
    calls, row = harness
    row.update(record_lane_owner='batch_live_v1', server_batch_only=True, discarded=True)
    conversation = _Conversation()
    conversation.discarded = True
    conversation.transcript_segments = []
    conversation.photos = []
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _: conversation)
    original = finalizer.run_blocking

    async def run(executor, function, *args, **kwargs):
        if function is finalizer.lifecycle_service.complete_discarded_server_batch_fanout:
            return False
        return await original(executor, function, *args, **kwargs)

    monkeypatch.setattr(finalizer, 'run_blocking', run)
    with pytest.raises(finalizer.ConversationFinalizationError, match='fanout_completion_conflict'):
        await _finalize()
    assert finalizer.register_recording not in calls


@pytest.mark.asyncio
async def test_silent_discard_keeps_processing_fence_without_registration(harness, monkeypatch):
    calls, row = harness
    row.update(record_lane_owner='batch_live_v1', discarded=True)
    original = finalizer.run_blocking

    async def run(executor, function, *args, **kwargs):
        if function is finalizer.register_recording:
            calls.append(function)
            return function(*args, **kwargs)
        return await original(executor, function, *args, **kwargs)

    monkeypatch.setattr(finalizer, 'run_blocking', run)
    assert await _finalize(ProcessingTrigger.SILENT_BACKFILL) is finalizer.ConversationFinalizationDisposition.fenced
    assert finalizer.register_recording not in calls
    assert finalizer.process_with_episode_budget not in calls
    assert finalizer.lifecycle_service.claim_finalization_fanout not in calls


@pytest.mark.asyncio
async def test_concurrent_restore_before_fanout_retries_and_retains_obligation(harness, monkeypatch):
    """When a capture is processed as discarded, a concurrent restore before fanout
    must not admit kept fanout without registering the recording. It must retry with
    lease conflict, and on retry register the audio obligation."""
    calls, row = harness
    row.update(record_lane_owner='batch_live_v1', status='processing', discarded=False)
    durable = dict(row)
    conversation = _Conversation()
    conversation.status = ConversationStatus.processing
    conversation.discarded = False
    conversation.model_dump = lambda: {
        'id': 'n',
        'status': conversation.status,
        'discarded': conversation.discarded,
    }

    def deserialize(data):
        if isinstance(data, dict):
            conversation.status = data.get('status', conversation.status)
            conversation.discarded = data.get('discarded', conversation.discarded)
        return conversation

    monkeypatch.setattr(finalizer, 'deserialize_conversation', deserialize)
    original = finalizer.run_blocking

    async def no_wait(*args, **kwargs):
        return 'not_applicable'

    async def absorbed(*args, **kwargs):
        return True

    attempt = 0

    async def run(executor, function, *args, **kwargs):
        nonlocal attempt
        if function is finalizer.process_with_episode_budget:
            conversation.status = ConversationStatus.completed
            if attempt == 0:
                conversation.discarded = True
                durable.update(status='completed', discarded=True)
            else:
                conversation.discarded = False
                durable.update(status='completed', discarded=False, sync_relevance_user_kept=True)
            kwargs['persistence_observer'](True)
            return conversation
        if function is finalizer.register_recording:
            calls.append(function)
            return True
        if function is finalizer.lifecycle_service.claim_finalization_fanout:
            calls.append(function)
            if attempt == 0:
                # User restores the row before fanout transaction commits!
                durable['discarded'] = False
            expected_discarded = kwargs.get('expected_discarded', False)
            if expected_discarded and not durable.get('discarded'):
                return {'status': 'lease_conflict', 'fanout_key': 'key'}
            admitted = jobs_db._conversation_admits_fanout(durable, _JOB, 'job')
            return {'status': 'claimed' if admitted else 'fenced', 'fanout_key': 'key'}
        if function is finalizer.link_duplicate_captures:
            calls.append(function)
            return None
        if function is finalizer.refresh_primary_notes:
            return None
        if function is finalizer.conversations_db.get_conversation:
            return durable
        if function is finalizer.extract_memories:
            return None
        if function is finalizer.record_finalized_meeting_receipt:
            return None
        if function is finalizer.resolve_frame_request_authority:
            return None
        if function is finalizer.ensure_conversation_keyframe_job:
            return False
        if function is finalizer.complete_explicit:
            return None
        if function is finalizer._episode_after_finalization:
            return None
        if function is finalizer.lifecycle_service.complete_finalization_fanout:
            calls.append(function)
            return True
        return await original(executor, function, *args, **kwargs)

    monkeypatch.setattr(finalizer, 'await_meeting_evidence', no_wait)
    monkeypatch.setattr(finalizer, 'warm_rollout_cohorts', no_wait)
    monkeypatch.setattr(finalizer, '_maybe_start_shadow', lambda *_: None)
    monkeypatch.setattr(finalizer, 'smart_merge_step', absorbed)
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', no_wait)
    monkeypatch.setattr(finalizer, 'schedule_person_voice_learning_retry', lambda *_: None)
    monkeypatch.setattr(finalizer, 'run_blocking', run)

    # Attempt 0: processed as discarded, user restores before fanout claim -> fanout_lease_conflict raised!
    with pytest.raises(finalizer.ConversationFinalizationError) as exc_info:
        await _finalize()
    assert str(exc_info.value) == 'processing_failed'
    assert str(exc_info.value.__cause__) == 'fanout_lease_conflict'
    assert finalizer.register_recording not in calls

    # Attempt 1 (retry): loads durable restored row (discarded=False)
    attempt = 1
    row['discarded'] = False
    row['sync_relevance_user_kept'] = True
    assert await _finalize() is finalizer.ConversationFinalizationDisposition.completed
    assert finalizer.register_recording in calls
    assert finalizer.lifecycle_service.complete_finalization_fanout in calls


@pytest.mark.asyncio
async def test_restore_after_fanout_claim_before_close_completes_with_one_obligation(harness, monkeypatch):
    calls, row = harness
    row.update(record_lane_owner='batch_live_v1', private_cloud_sync_enabled=True)
    client = StrictFirestore()
    row_path = ('users', 'u', 'conversations', 'n')
    job_path = (jobs_db.FINALIZATION_JOBS_COLLECTION, 'job')
    _, segment = record_identity('u', 'n')
    obligation_path = ('batch_pipeline_dev_jobs', segment)
    client.rows[row_path] = dict(row)
    client.rows[job_path] = {**_JOB, 'fanout_status': 'pending'}
    client.rows[('users', 'u')] = {'private_cloud_sync_enabled': True}
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    monkeypatch.setattr(jobs_db, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(conversations_db, 'db', client)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(batch_pipeline_privacy, 'lever_enabled', lambda *_: False)
    monkeypatch.setattr(batch_pipeline_store, 'contention_retry_enabled', lambda: False)
    monkeypatch.setattr(live, 'resolve_batch_policy', lambda *_: BatchUnitPolicy())
    monkeypatch.setattr(lifecycle, 'FirestoreStore', lambda namespace: store)
    original_run = finalizer.run_blocking
    original_register = live.register_recording
    original_restore = conversations_db.restore_conversation_from_discarded
    order = []

    def register(uid, current, **kwargs):
        assert kwargs['restoring'] is True
        assert current == client.rows[row_path]
        assert current['discarded'] is True
        assert original_register(uid, current, **kwargs) is True
        assert obligation_path in client.rows
        order.append('register')
        return True

    def restore(uid, conversation_id):
        assert order == ['claim', 'register']
        assert client.rows[row_path]['discarded'] is True
        assert obligation_path in client.rows
        result = original_restore(uid, conversation_id)
        assert client.rows[row_path]['discarded'] is False
        order.append('metadata')
        return result

    async def run(executor, function, *args, **kwargs):
        if function is finalizer.register_recording:
            calls.append(function)
            return function(*args, store=store, **kwargs)
        if function is lifecycle.claim_finalization_fanout:
            result = function(*args, **kwargs)
            assert result['status'] == 'claimed'
            order.append('claim')
            # The claim read a kept row. A concurrent relevance discard and
            # explicit restore now land while its fanout lease is still open.
            client.rows[row_path]['discarded'] = True
            assert lifecycle.restore_discarded('u', 'n') is True
            return result
        if function is lifecycle.complete_finalization_fanout:
            assert order == ['claim', 'register', 'metadata']
            assert function(*args, **kwargs) is True
            order.append('close')
            return True
        return await original_run(executor, function, *args, **kwargs)

    async def absorbed(*args, **kwargs):
        return True

    monkeypatch.setattr(live, 'register_recording', register)
    monkeypatch.setattr(conversations_db, 'restore_conversation_from_discarded', restore)
    monkeypatch.setattr(finalizer, 'smart_merge_step', absorbed)
    monkeypatch.setattr(finalizer, 'run_blocking', run)
    assert await _finalize() is finalizer.ConversationFinalizationDisposition.completed
    # Exercise the handler's terminal-success write after the real fanout close.
    assert jobs_db.mark_finalization_completed('job', 1, 1) is True
    assert order == ['claim', 'register', 'metadata', 'close']
    assert client.rows[job_path]['status'] == 'completed'
    assert client.rows[job_path]['fanout_status'] == 'completed'
    assert client.rows[job_path]['terminal_outcome'] == 'success'
    assert client.rows[row_path]['discarded'] is False
    assert client.rows[obligation_path]['state'] == 'record_pending'
    assert sum(path[0] == 'batch_pipeline_dev_jobs' for path in client.rows) == 1
