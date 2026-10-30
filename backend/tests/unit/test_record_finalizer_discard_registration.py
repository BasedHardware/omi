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
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _: conversation)
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
