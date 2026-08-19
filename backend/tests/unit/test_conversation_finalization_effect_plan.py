import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.conversation_enums import ConversationStatus
from utils.conversations import finalizer
from utils.conversations.enrichment_plan import REQUIRED_EFFECT_KEYS, RequiredEnrichmentEffect
from utils.executors import submit_with_context


@pytest.fixture(autouse=True)
def _release_fanout(monkeypatch):
    release = MagicMock(return_value=True)
    monkeypatch.setattr(finalizer.lifecycle_service, 'release_finalization_fanout', release)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'checkpoint_finalization_derived_effects',
        lambda *_: True,
    )
    return release


def _effect_plan(functions) -> tuple[RequiredEnrichmentEffect, ...]:
    return tuple(
        RequiredEnrichmentEffect(key, function) for key, function in zip(REQUIRED_EFFECT_KEYS, functions, strict=True)
    )


def _configure_completed_v2(monkeypatch, effects, *, completed_effects=()):
    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.completed,
        discarded=False,
        language='en',
        geolocation=None,
    )
    checkpoints: list[str] = []
    completed = MagicMock(return_value=True)
    external = AsyncMock()

    monkeypatch.setattr(
        finalizer.conversations_db,
        'get_conversation',
        lambda *_: {
            'id': conversation.id,
            'finalization_derived_effects_identity': [None, 'job-1', None],
        },
    )
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: conversation)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda _uid: None)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'conversation:conversation-1:finalization:1',
            'plan_version': 2,
            'completed_effects': tuple(completed_effects),
            'finalization_incarnation_id': 'incarnation-1',
            'finalization_vector_generation_id': 'generation-job-1',
            'transcript_vector_count': 0,
        },
    )
    monkeypatch.setattr(finalizer, 'required_enrichment_effects', lambda *_, **__: effects)
    monkeypatch.setattr(finalizer, 'extract_memories', MagicMock(), raising=False)

    def checkpoint(_job, _generation, _epoch, effect, *, persist_effect=True):
        if persist_effect:
            checkpoints.append(effect)
        return 'completed'

    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'prepare_finalization_effect',
        lambda *_: 'completed',
    )
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'complete_finalization_effect',
        checkpoint,
    )
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_fanout', completed)
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', external)
    return checkpoints, completed, external


async def _finalize():
    return await finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=3,
        lease_epoch=7,
    )


@pytest.mark.asyncio
async def test_finalization_waits_for_required_leaf_before_external_fanout(monkeypatch):
    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.processing,
        discarded=False,
        language='en',
        geolocation=None,
    )
    started = threading.Event()
    release = threading.Event()
    derived_bundle_awaited = asyncio.Event()
    derived_bundle_ref = {}
    external_started = threading.Event()
    execution: list[str] = []
    real_run_blocking = finalizer.run_blocking

    def blocked_vector() -> None:
        execution.append('structured_vector:start')
        started.set()
        assert release.wait(timeout=5), 'test did not release the required effect'
        execution.append('structured_vector:end')

    def effect(name: str):
        return lambda: execution.append(name)

    def process(_uid, _language, current, **kwargs):
        defer_required_enrichment = kwargs.get('defer_required_enrichment', False)

        def derived_bundle() -> None:
            if not defer_required_enrichment:
                submit_with_context(finalizer.postprocess_executor, blocked_vector)

        derived_bundle_ref['execute'] = derived_bundle
        kwargs['persistence_observer'](True)
        kwargs['derived_effects_observer'](derived_bundle)
        current.status = ConversationStatus.completed
        return current

    async def observe_derived_bundle(executor, function, *args, **kwargs):
        result = await real_run_blocking(executor, function, *args, **kwargs)
        if function is derived_bundle_ref.get('execute'):
            derived_bundle_awaited.set()
        return result

    effects = _effect_plan(
        (
            blocked_vector,
            effect('transcript_vectors'),
        )
    )
    checkpoints: list[str] = []
    completed = MagicMock(return_value=True)

    async def external(*_args, **_kwargs) -> None:
        external_started.set()

    monkeypatch.setattr(finalizer.conversations_db, 'get_conversation', lambda *_: {'id': conversation.id})
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: conversation)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda _uid: None)
    monkeypatch.setattr(finalizer, 'run_blocking', observe_derived_bundle)
    monkeypatch.setattr(finalizer, 'process_conversation', process)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'conversation:conversation-1:finalization:1',
            'plan_version': 2,
            'completed_effects': (),
            'finalization_incarnation_id': 'incarnation-1',
            'finalization_vector_generation_id': 'generation-job-1',
            'transcript_vector_count': 0,
        },
    )
    monkeypatch.setattr(finalizer, 'required_enrichment_effects', lambda *_, **__: effects, raising=False)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'prepare_finalization_effect',
        lambda *_: 'completed',
    )
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'complete_finalization_effect',
        lambda _job, _generation, _epoch, effect_key, *, persist_effect=True: (
            checkpoints.append(effect_key) if persist_effect else None
        )
        or 'completed',
    )
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_fanout', completed)
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', external)
    task = asyncio.create_task(_finalize())
    assert await asyncio.to_thread(started.wait, 5), 'required effect never reached the real executor'
    await asyncio.wait_for(derived_bundle_awaited.wait(), timeout=5)
    fanout_before_release = external_started.is_set()
    release.set()
    assert await task == finalizer.ConversationFinalizationDisposition.completed
    assert not fanout_before_release, 'external fanout ran before required structured vector finished'
    assert checkpoints == list(REQUIRED_EFFECT_KEYS)
    assert execution == [
        'structured_vector:start',
        'structured_vector:end',
        'transcript_vectors',
    ]
    completed.assert_called_once_with('job-1', 3, 7, meeting_treatment_eligible=False)


@pytest.mark.asyncio
async def test_blocked_required_effect_renews_job_lease(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    renewed = threading.Event()

    def blocked_vector() -> None:
        started.set()
        assert release.wait(timeout=5), 'test did not release the required effect'

    effects = _effect_plan((blocked_vector, lambda: None))
    _, completed, external = _configure_completed_v2(monkeypatch, effects)

    def renew(*_args) -> bool:
        if started.is_set():
            renewed.set()
        return True

    monkeypatch.setattr(finalizer.lifecycle_service, 'finalization_job_lease_renewal_interval', lambda: 0.01)
    monkeypatch.setattr(finalizer.lifecycle_service, 'renew_finalization_job_lease', renew)

    task = asyncio.create_task(_finalize())
    assert await asyncio.to_thread(started.wait, 5), 'required effect never reached the real executor'
    assert await asyncio.to_thread(renewed.wait, 5), 'lease heartbeat did not run while the effect was blocked'
    release.set()

    assert await task == finalizer.ConversationFinalizationDisposition.completed
    external.assert_awaited_once()
    completed.assert_called_once()


@pytest.mark.asyncio
async def test_cancellation_waits_for_blocked_vector_and_keeps_lease_heartbeat_alive(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    renewed = threading.Event()
    observe_post_cancel_renewal = threading.Event()
    renewed_after_cancel = threading.Event()

    def blocked_vector() -> None:
        started.set()
        assert release.wait(timeout=5), 'test did not release the required effect'

    effects = _effect_plan((blocked_vector, lambda: None))
    checkpoints, completed, external = _configure_completed_v2(monkeypatch, effects)

    def renew(*_args) -> bool:
        renewed.set()
        if observe_post_cancel_renewal.is_set():
            renewed_after_cancel.set()
        return True

    monkeypatch.setattr(finalizer.lifecycle_service, 'finalization_job_lease_renewal_interval', lambda: 0.01)
    monkeypatch.setattr(finalizer.lifecycle_service, 'renew_finalization_job_lease', renew)

    task = asyncio.create_task(_finalize())
    assert await asyncio.to_thread(started.wait, 5), 'required effect never reached the real executor'
    assert await asyncio.to_thread(renewed.wait, 5), 'lease heartbeat did not run while the effect was blocked'

    try:
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), 'finalizer stopped before its executor leaf returned'
        observe_post_cancel_renewal.set()
        assert await asyncio.to_thread(
            renewed_after_cancel.wait, 5
        ), 'lease heartbeat stopped before the cancelled executor leaf returned'
    finally:
        release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert checkpoints == []
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('renewal_failure', ['ownership_lost', 'renewal_error'])
async def test_lost_lease_during_required_effect_prevents_checkpoint_and_fanout(monkeypatch, renewal_failure):
    started = threading.Event()
    release = threading.Event()
    renewal_attempted = threading.Event()

    def blocked_vector() -> None:
        started.set()
        assert release.wait(timeout=5), 'test did not release the required effect'

    effects = _effect_plan((blocked_vector, lambda: None))
    checkpoints, completed, external = _configure_completed_v2(monkeypatch, effects)

    def reject_renewal(*_args) -> bool:
        if not started.is_set():
            return True
        renewal_attempted.set()
        if renewal_failure == 'renewal_error':
            raise RuntimeError('lease store unavailable')
        return False

    monkeypatch.setattr(finalizer.lifecycle_service, 'finalization_job_lease_renewal_interval', lambda: 0.01)
    monkeypatch.setattr(finalizer.lifecycle_service, 'renew_finalization_job_lease', reject_renewal)

    task = asyncio.create_task(_finalize())
    assert await asyncio.to_thread(started.wait, 5), 'required effect never reached the real executor'
    assert await asyncio.to_thread(renewal_attempted.wait, 5), 'lease heartbeat did not attempt renewal'
    release.set()

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await task
    assert checkpoints == []
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_lost_lease_releases_fanout_only_after_blocked_derived_bundle_returns(
    monkeypatch,
    _release_fanout,
):
    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.processing,
        discarded=False,
        language='en',
        geolocation=None,
    )
    started = threading.Event()
    release = threading.Event()
    renewal_attempted = threading.Event()

    def blocked_derived() -> None:
        started.set()
        assert release.wait(timeout=5), 'test did not release the derived bundle'

    def process(_uid, _language, current, **kwargs):
        kwargs['persistence_observer'](True)
        kwargs['derived_effects_observer'](blocked_derived)
        current.status = ConversationStatus.completed
        return current

    def reject_renewal(*_args) -> bool:
        if started.is_set():
            renewal_attempted.set()
            return False
        return True

    monkeypatch.setattr(
        finalizer.conversations_db,
        'get_conversation',
        lambda *_: {
            'id': conversation.id,
            'finalization_incarnation_id': 'incarnation-1',
            'finalization_job_id': 'job-1',
            'finalization_revision': 1,
        },
    )
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: conversation)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda _uid: None)
    monkeypatch.setattr(finalizer, 'process_conversation', process)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'fanout-1',
            'plan_version': 2,
            'completed_effects': (),
            'finalization_incarnation_id': 'incarnation-1',
            'finalization_vector_generation_id': 'generation-job-1',
            'transcript_vector_count': 0,
        },
    )
    monkeypatch.setattr(finalizer.lifecycle_service, 'finalization_job_lease_renewal_interval', lambda: 0.01)
    monkeypatch.setattr(finalizer.lifecycle_service, 'renew_finalization_job_lease', reject_renewal)
    monkeypatch.setattr(finalizer, 'required_enrichment_effects', MagicMock())
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', AsyncMock())

    task = asyncio.create_task(_finalize())
    assert await asyncio.to_thread(started.wait, 5), 'derived bundle did not start'
    assert await asyncio.to_thread(renewal_attempted.wait, 5), 'lease loss was not observed'
    _release_fanout.assert_not_called()
    release.set()

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await task
    _release_fanout.assert_called_once_with('job-1', 3, 7)
    finalizer.required_enrichment_effects.assert_not_called()
    finalizer.trigger_external_integrations.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_required_effect_stops_fanout_and_preserves_prior_checkpoint(monkeypatch):
    execution: list[str] = []

    def fail_transcript_vectors() -> None:
        execution.append('transcript_vectors')
        raise RuntimeError('provider unavailable')

    effects = _effect_plan(
        (
            lambda: execution.append('structured_vector'),
            fail_transcript_vectors,
        )
    )
    checkpoints, completed, external = _configure_completed_v2(monkeypatch, effects)

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await _finalize()

    assert execution == ['structured_vector', 'transcript_vectors']
    assert checkpoints == ['structured_vector']
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_retry_skips_checkpointed_effects_and_finishes_missing_suffix(monkeypatch):
    execution: list[str] = []

    def already_completed() -> None:
        raise AssertionError('checkpointed effect executed again')

    effects = _effect_plan(
        (
            already_completed,
            lambda: execution.append('transcript_vectors'),
        )
    )
    checkpoints, completed, external = _configure_completed_v2(
        monkeypatch,
        effects,
        completed_effects=('structured_vector',),
    )

    assert await _finalize() == finalizer.ConversationFinalizationDisposition.completed
    assert execution == ['transcript_vectors']
    assert checkpoints == ['transcript_vectors']
    external.assert_awaited_once()
    completed.assert_called_once()


@pytest.mark.asyncio
async def test_checkpoint_conflict_prevents_later_effects_and_terminal_completion(monkeypatch):
    execution: list[str] = []
    effects = _effect_plan(
        (
            lambda: execution.append('structured_vector'),
            lambda: execution.append('transcript_vectors'),
        )
    )
    _, completed, external = _configure_completed_v2(monkeypatch, effects)
    checkpoint = MagicMock(return_value='conflict')
    cleanup = MagicMock()
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_effect', checkpoint)
    monkeypatch.setattr(finalizer, 'cleanup_required_enrichment', cleanup)

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await _finalize()

    assert execution == ['structured_vector']
    checkpoint.assert_called_once_with('job-1', 3, 7, 'structured_vector', persist_effect=True)
    cleanup.assert_not_called()
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_delete_after_last_vector_checkpoint_is_fenced_before_external_fanout(monkeypatch):
    execution: list[str] = []
    effects = _effect_plan(
        (
            lambda: execution.append('structured_vector'),
            lambda: execution.append('transcript_vectors'),
        )
    )
    _, completed, external = _configure_completed_v2(monkeypatch, effects)
    claimed = {
        'status': 'claimed',
        'fanout_key': 'fanout-1',
        'plan_version': 2,
        'completed_effects': (),
        'finalization_incarnation_id': 'incarnation-1',
        'finalization_vector_generation_id': 'generation-job-1',
        'transcript_vector_count': 2,
    }
    cleanup_required = claimed | {
        'status': 'cleanup_required',
        'completed_effects': REQUIRED_EFFECT_KEYS,
    }
    claims = iter((claimed, cleanup_required))
    cleanup = MagicMock()
    fence = MagicMock(return_value=True)
    monkeypatch.setattr(finalizer.lifecycle_service, 'claim_finalization_fanout', lambda *_: next(claims))
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_enrichment_cleanup', fence)
    monkeypatch.setattr(finalizer, 'cleanup_required_enrichment', cleanup)

    assert await _finalize() == finalizer.ConversationFinalizationDisposition.fenced
    assert execution == list(REQUIRED_EFFECT_KEYS)
    cleanup.assert_called_once_with(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='generation-job-1',
        transcript_vector_count=2,
        require_vector_store=True,
    )
    fence.assert_called_once_with('job-1', 3, 7)
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_delete_after_claim_compensates_late_vector_before_fencing(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    conversation_missing = threading.Event()
    execution: list[str] = []
    transcript = MagicMock()

    def structured_vector() -> None:
        started.set()
        assert release.wait(timeout=5), 'test did not release the required effect'
        execution.append('structured_upsert')

    effects = _effect_plan((structured_vector, transcript))
    _, completed, external = _configure_completed_v2(monkeypatch, effects)

    def boundary(*_args, persist_effect=True):
        del persist_effect
        return 'conversation_missing' if conversation_missing.is_set() else 'completed'

    cleanup = MagicMock(side_effect=lambda *_args, **_kwargs: execution.append('compensate_both_vectors'))
    fence = MagicMock(return_value=True)
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_effect', boundary)
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_enrichment_cleanup', fence)
    monkeypatch.setattr(finalizer, 'cleanup_required_enrichment', cleanup)

    task = asyncio.create_task(_finalize())
    assert await asyncio.to_thread(started.wait, 5), 'required effect never reached the real executor'
    conversation_missing.set()
    execution.append('delete_cleanup_finished')
    release.set()

    assert await task == finalizer.ConversationFinalizationDisposition.fenced
    assert execution == ['delete_cleanup_finished', 'structured_upsert', 'compensate_both_vectors']
    cleanup.assert_called_once_with(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='generation-job-1',
        transcript_vector_count=0,
        require_vector_store=True,
    )
    transcript.assert_not_called()
    fence.assert_called_once_with('job-1', 3, 7)
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_partial_transcript_failure_after_delete_compensates_prior_checkpoint(monkeypatch):
    conversation_missing = threading.Event()
    execution: list[str] = []

    def transcript_vector() -> None:
        execution.append('transcript_partial_upsert')
        conversation_missing.set()
        raise RuntimeError('provider failed after partial write')

    effects = _effect_plan((lambda: execution.append('structured_upsert'), transcript_vector))
    checkpoints, completed, external = _configure_completed_v2(monkeypatch, effects)

    def boundary(_job, _generation, _epoch, effect, *, persist_effect=True):
        if conversation_missing.is_set():
            return 'conversation_missing'
        if persist_effect:
            checkpoints.append(effect)
        return 'completed'

    cleanup = MagicMock(side_effect=lambda *_args, **_kwargs: execution.append('compensate_both_vectors'))
    fence = MagicMock(return_value=True)
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_effect', boundary)
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_enrichment_cleanup', fence)
    monkeypatch.setattr(finalizer, 'cleanup_required_enrichment', cleanup)

    assert await _finalize() == finalizer.ConversationFinalizationDisposition.fenced
    assert checkpoints == ['structured_vector']
    assert execution == ['structured_upsert', 'transcript_partial_upsert', 'compensate_both_vectors']
    cleanup.assert_called_once_with(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='generation-job-1',
        transcript_vector_count=0,
        require_vector_store=True,
    )
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_failure_stays_retryable_until_cleanup_and_fence_succeed(monkeypatch):
    structured = MagicMock()
    transcript = MagicMock()
    effects = _effect_plan((structured, transcript))
    _, completed, external = _configure_completed_v2(monkeypatch, effects)
    cleanup = MagicMock(side_effect=[RuntimeError('vector store unavailable'), None])
    fence = MagicMock(return_value=True)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'complete_finalization_effect',
        lambda *_args, **_kwargs: 'conversation_missing',
    )
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_enrichment_cleanup', fence)
    monkeypatch.setattr(finalizer, 'cleanup_required_enrichment', cleanup)

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await _finalize()
    fence.assert_not_called()

    assert await _finalize() == finalizer.ConversationFinalizationDisposition.fenced
    assert structured.call_count == 2
    transcript.assert_not_called()
    assert cleanup.call_count == 2
    fence.assert_called_once_with('job-1', 3, 7)
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_late_vector_is_compensated_before_cancellation_surfaces(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    conversation_missing = threading.Event()

    def blocked_vector() -> None:
        started.set()
        assert release.wait(timeout=5), 'test did not release the required effect'

    effects = _effect_plan((blocked_vector, MagicMock()))
    _, completed, external = _configure_completed_v2(monkeypatch, effects)
    cleanup = MagicMock()
    fence = MagicMock()

    def boundary(*_args, persist_effect=True):
        assert persist_effect is False
        return 'conversation_missing' if conversation_missing.is_set() else 'completed'

    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_effect', boundary)
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_enrichment_cleanup', fence)
    monkeypatch.setattr(finalizer, 'cleanup_required_enrichment', cleanup)

    task = asyncio.create_task(_finalize())
    assert await asyncio.to_thread(started.wait, 5), 'required effect never reached the real executor'
    task.cancel()
    conversation_missing.set()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    cleanup.assert_called_once_with(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='generation-job-1',
        transcript_vector_count=0,
        require_vector_store=True,
    )
    fence.assert_not_called()
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_processing_path_defers_vector_effects_without_deferring_memory(monkeypatch):
    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.processing,
        discarded=False,
        language='en',
        geolocation=None,
    )
    process_kwargs = {}
    derived_calls: list[str] = []
    vector_store_requirements: list[bool] = []

    def process(_uid, _language, current, **kwargs):
        process_kwargs.update(kwargs)
        kwargs['derived_effects_observer'](lambda: derived_calls.append('best_effort'))
        current.status = ConversationStatus.completed
        return current

    def required_effects(_uid, _conversation, *, require_vector_store, **_kwargs):
        vector_store_requirements.append(require_vector_store)
        return _effect_plan((lambda: None, lambda: None))

    monkeypatch.setattr(
        finalizer.conversations_db,
        'get_conversation',
        lambda *_: {
            'id': conversation.id,
            'finalization_incarnation_id': 'incarnation-1',
            'finalization_job_id': 'job-1',
            'finalization_revision': 4,
        },
    )
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: conversation)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda _uid: None)
    monkeypatch.setattr(finalizer, 'process_conversation', process)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'fanout-1',
            'plan_version': 2,
            'completed_effects': (),
            'finalization_incarnation_id': 'incarnation-1',
            'finalization_vector_generation_id': 'generation-job-1',
            'transcript_vector_count': 0,
        },
    )
    monkeypatch.setattr(finalizer, 'required_enrichment_effects', required_effects)
    monkeypatch.setattr(finalizer.lifecycle_service, 'prepare_finalization_effect', lambda *_: 'completed')
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_effect', lambda *_, **__: 'completed')
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_fanout', lambda *_, **__: True)
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', AsyncMock())

    assert await _finalize() == finalizer.ConversationFinalizationDisposition.completed
    assert 'defer_memory_extraction' not in process_kwargs
    assert process_kwargs['defer_derived_effects'] is True
    assert process_kwargs['defer_required_enrichment'] is True
    assert process_kwargs['expected_finalization_identity'] == ('incarnation-1', 'job-1', 4)
    assert derived_calls == ['best_effort']
    assert vector_store_requirements == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('plan_version', 'require_vector_store'),
    [
        pytest.param(2, True, id='active-v2'),
        pytest.param(1, False, id='standby-v1'),
    ],
)
async def test_plan_version_controls_vector_store_requirement(monkeypatch, plan_version, require_vector_store):
    execution: list[str] = []
    effects = _effect_plan(
        (
            lambda: execution.append('structured_vector'),
            lambda: execution.append('transcript_vectors'),
        )
    )
    checkpoints, completed, external = _configure_completed_v2(monkeypatch, effects)
    plan_arguments: list[tuple[bool, str | None, int | None]] = []

    def required_effects(
        _uid,
        _conversation,
        *,
        require_vector_store,
        finalization_vector_generation_id,
        transcript_vector_count,
    ):
        plan_arguments.append((require_vector_store, finalization_vector_generation_id, transcript_vector_count))
        return effects

    monkeypatch.setattr(finalizer, 'required_enrichment_effects', required_effects)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'fanout-1',
            'plan_version': plan_version,
            'completed_effects': (),
            'finalization_incarnation_id': 'incarnation-1' if plan_version == 2 else None,
            'finalization_vector_generation_id': 'generation-job-1' if plan_version == 2 else None,
            'transcript_vector_count': 0 if plan_version == 2 else None,
        },
    )

    assert await _finalize() == finalizer.ConversationFinalizationDisposition.completed
    assert plan_arguments == [
        (
            require_vector_store,
            'generation-job-1' if plan_version == 2 else None,
            0 if plan_version == 2 else None,
        )
    ]
    assert execution == list(REQUIRED_EFFECT_KEYS)
    assert checkpoints == (list(REQUIRED_EFFECT_KEYS) if plan_version == 2 else [])
    external.assert_awaited_once()
    completed.assert_called_once()


@pytest.mark.asyncio
async def test_v1_retry_reruns_full_required_plan_after_partial_failure(monkeypatch):
    execution: list[str] = []
    transcript_attempts = 0

    def transcript_vectors() -> None:
        nonlocal transcript_attempts
        transcript_attempts += 1
        execution.append('transcript_vectors')
        if transcript_attempts == 1:
            raise RuntimeError('provider unavailable')

    effects = _effect_plan(
        (
            lambda: execution.append('structured_vector'),
            transcript_vectors,
        )
    )
    checkpoints, completed, external = _configure_completed_v2(monkeypatch, effects)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'legacy-fanout',
            'plan_version': 1,
            'completed_effects': (),
        },
    )

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await _finalize()
    assert await _finalize() == finalizer.ConversationFinalizationDisposition.completed
    assert execution == [
        'structured_vector',
        'transcript_vectors',
        'structured_vector',
        'transcript_vectors',
    ]
    assert checkpoints == []
    external.assert_awaited_once()
    completed.assert_called_once()


@pytest.mark.asyncio
async def test_completed_v1_acknowledgement_skips_unsafe_shared_id_vector_replay(monkeypatch):
    effects = _effect_plan((lambda: None, lambda: None))
    checkpoints, completed, external = _configure_completed_v2(monkeypatch, effects)
    required_effects = MagicMock(side_effect=AssertionError('completed v1 fanout must not replay shared vector IDs'))
    process = MagicMock(side_effect=AssertionError('completed acknowledgement must not reprocess'))
    monkeypatch.setattr(finalizer, 'required_enrichment_effects', required_effects)
    monkeypatch.setattr(finalizer, 'process_conversation', process)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'completed',
            'fanout_key': 'legacy-fanout',
            'plan_version': 1,
            'completed_effects': (),
        },
    )

    assert await _finalize() == finalizer.ConversationFinalizationDisposition.completed
    assert checkpoints == []
    required_effects.assert_not_called()
    process.assert_not_called()
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_removed_v1_replay_status_fails_closed_without_mutating_shared_ids(monkeypatch):
    transcript = MagicMock()
    effects = _effect_plan((lambda: None, transcript))
    _, completed, external = _configure_completed_v2(monkeypatch, effects)
    cleanup = MagicMock()
    fence = MagicMock()
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'effects_replay_required',
            'fanout_key': 'legacy-fanout',
            'plan_version': 1,
            'completed_effects': (),
        },
    )
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'complete_finalization_effect',
        lambda *_args, **_kwargs: 'conversation_missing',
    )
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_enrichment_cleanup', fence)
    monkeypatch.setattr(finalizer, 'cleanup_required_enrichment', cleanup)

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await _finalize()
    cleanup.assert_not_called()
    transcript.assert_not_called()
    fence.assert_not_called()
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_missing_completed_v2_job_cleans_vectors_without_replaying_fanout(monkeypatch):
    cleanup = MagicMock()
    external = AsyncMock()
    monkeypatch.setattr(finalizer.conversations_db, 'get_conversation', lambda *_: None)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'completed_cleanup_required',
            'fanout_key': 'fanout-1',
            'plan_version': 2,
            'completed_effects': REQUIRED_EFFECT_KEYS,
            'finalization_incarnation_id': 'incarnation-1',
            'finalization_vector_generation_id': 'generation-job-1',
            'transcript_vector_count': 4,
        },
    )
    monkeypatch.setattr(finalizer, 'cleanup_required_enrichment', cleanup)
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', external)
    monkeypatch.setattr(
        finalizer,
        'required_enrichment_effects',
        MagicMock(side_effect=AssertionError('completed cleanup must not replay vectors')),
    )

    assert await _finalize() == finalizer.ConversationFinalizationDisposition.completed
    cleanup.assert_called_once_with(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='generation-job-1',
        transcript_vector_count=4,
        require_vector_store=True,
    )
    external.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'runtime_keys',
    (
        ('transcript_vectors', 'structured_vector'),
        ('structured_vector', 'structured_vector'),
        ('structured_vector',),
    ),
)
async def test_malformed_runtime_plan_fails_before_any_vector_or_fanout(monkeypatch, runtime_keys):
    leaves = [MagicMock() for _ in runtime_keys]
    effects = tuple(RequiredEnrichmentEffect(key, leaf) for key, leaf in zip(runtime_keys, leaves, strict=True))
    _, completed, external = _configure_completed_v2(monkeypatch, effects)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'legacy-fanout',
            'plan_version': 1,
            'completed_effects': (),
        },
    )

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await _finalize()

    assert all(leaf.call_count == 0 for leaf in leaves)
    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_plan_version_fails_closed_before_any_effect_or_fanout(monkeypatch):
    effects = _effect_plan(tuple(lambda: None for _ in REQUIRED_EFFECT_KEYS))
    _, completed, external = _configure_completed_v2(monkeypatch, effects)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'future-fanout',
            'plan_version': 3,
            'completed_effects': (),
        },
    )

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await _finalize()

    external.assert_not_awaited()
    completed.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_plan_version_rejects_processing_bundle_before_any_derived_effect(monkeypatch):
    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.processing,
        discarded=False,
        language='en',
        geolocation=None,
    )
    derived = MagicMock()
    vector_leaves = (MagicMock(), MagicMock())
    external = AsyncMock()

    def process(_uid, _language, current, **kwargs):
        kwargs['persistence_observer'](True)
        kwargs['derived_effects_observer'](derived)
        current.status = ConversationStatus.completed
        return current

    monkeypatch.setattr(finalizer.conversations_db, 'get_conversation', lambda *_: {'id': conversation.id})
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: conversation)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda _uid: None)
    monkeypatch.setattr(finalizer, 'process_conversation', process)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {
            'status': 'claimed',
            'fanout_key': 'future-fanout',
            'plan_version': 3,
            'completed_effects': (),
        },
    )
    monkeypatch.setattr(finalizer, 'required_enrichment_effects', lambda *_, **__: _effect_plan(vector_leaves))
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_effect', MagicMock())
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_fanout', MagicMock())
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', external)

    with pytest.raises(finalizer.ConversationFinalizationError, match='processing_failed'):
        await _finalize()

    derived.assert_not_called()
    assert all(leaf.call_count == 0 for leaf in vector_leaves)
    external.assert_not_awaited()
