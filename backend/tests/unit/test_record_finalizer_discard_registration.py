"""Intentional relevance discards retain the finalizer's existing terminal fence."""

import pytest

from database import conversation_finalization_jobs as jobs_db
from models.conversation_enums import ConversationStatus
from utils.conversations import finalizer
from utils.conversations.processing_trigger import ProcessingTrigger
from tests.unit.test_conversation_smart_merge_finalizer import harness, _Conversation, _JOB, _finalize


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
    assert row['discarded'] is initial_discarded  # Initial read stays stale after persistence.
    assert finalizer.lifecycle_service.claim_finalization_fanout in calls
    assert (finalizer.register_recording in calls) is not processed_discarded
    assert (finalizer.lifecycle_service.complete_finalization_fanout in calls) is not processed_discarded
    assert finalizer.link_duplicate_captures not in calls
    assert finalizer.RECORD_REGISTER_REFUSED._value.get() == before


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
        # print("RUN FUNCTION:", function)
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
