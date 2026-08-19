"""Shared persisted-conversation finalizer for pusher and Cloud Tasks workers.

This is intentionally not callable from the listen WebSocket as a local
fallback.  Callers must first own a durable finalization job lease.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Callable

from database import conversations as conversations_db
from database.redis_db import get_cached_user_geolocation
from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from models.geolocation import Geolocation
from utils.app_integrations import trigger_external_integrations
from utils.conversations.enrichment_plan import (
    PLAN_VERSION,
    REQUIRED_EFFECT_KEYS,
    cleanup_required_enrichment,
    required_enrichment_effects,
)
from utils.conversations.factory import deserialize_conversation
from utils.conversations.location import async_resolve_geolocation
from utils.conversations.meeting_treatment import is_meeting_treatment_eligible
from utils.conversations.process_conversation import extract_memories, process_conversation
from utils.conversations import lifecycle as lifecycle_service
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.log_sanitizer import sanitize_pii
from utils.task_intelligence.proactive_engine import persist_capture_arrival_intent, recommended_meeting_action_items

logger = logging.getLogger(__name__)


class ConversationFinalizationError(RuntimeError):
    """A retryable persisted-conversation finalization failure."""


class ConversationFinalizationDisposition(str, Enum):
    completed = 'completed'
    fenced = 'fenced'


def _raise_if_finalization_lease_lost(lease_lost: asyncio.Event) -> None:
    if lease_lost.is_set():
        raise ConversationFinalizationError('finalization_lease_lost')


async def _run_finalization_lease_heartbeat(
    finalization_job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    stop_event: asyncio.Event,
    lease_lost: asyncio.Event,
) -> None:
    interval = lifecycle_service.finalization_job_lease_renewal_interval()
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        try:
            renewed = await run_blocking(
                db_executor,
                lifecycle_service.renew_finalization_job_lease,
                finalization_job_id,
                dispatch_generation,
                lease_epoch,
            )
        except Exception:
            logger.error('persisted conversation finalization lease renewal failed failure=renewal_error')
            lease_lost.set()
            return
        if not renewed:
            logger.warning('persisted conversation finalization lease renewal failed failure=ownership_lost')
            lease_lost.set()
            return


async def _run_postprocess_mutation(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Keep a cancelled worker alive until its thread mutation has stopped."""
    mutation_task = asyncio.create_task(run_blocking(postprocess_executor, function, *args, **kwargs))
    try:
        return await asyncio.shield(mutation_task)
    except asyncio.CancelledError as cancellation:
        mutation_error_observed = False
        while not mutation_task.done():
            try:
                await asyncio.shield(mutation_task)
            except asyncio.CancelledError:
                continue
            except Exception:
                mutation_error_observed = True
                logger.error('cancelled conversation finalization mutation failed failure=mutation_error')
                break
        if mutation_task.done() and not mutation_task.cancelled() and not mutation_error_observed:
            try:
                mutation_task.result()
            except Exception:
                logger.error('cancelled conversation finalization mutation failed failure=mutation_error')
        raise cancellation


async def _cleanup_deleted_conversation_enrichment(
    uid: str,
    conversation_id: str,
    *,
    finalization_vector_generation_id: str,
    transcript_vector_count: int,
    require_vector_store: bool,
) -> None:
    try:
        await _run_postprocess_mutation(
            cleanup_required_enrichment,
            uid,
            conversation_id,
            finalization_vector_generation_id=finalization_vector_generation_id,
            transcript_vector_count=transcript_vector_count,
            require_vector_store=require_vector_store,
        )
    except Exception as error:
        raise ConversationFinalizationError('required_enrichment_cleanup_failed') from error


async def _run_required_enrichment(
    uid: str,
    conversation: Conversation,
    *,
    finalization_job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    completed_effects: set[str],
    checkpoint: bool,
    lease_lost: asyncio.Event,
    finalization_vector_generation_id: str | None,
    transcript_vector_count: int | None = None,
) -> bool:
    effects = required_enrichment_effects(
        uid,
        conversation,
        finalization_vector_generation_id=finalization_vector_generation_id,
        require_vector_store=checkpoint,
        transcript_vector_count=transcript_vector_count,
    )
    if tuple(effect.key for effect in effects) != REQUIRED_EFFECT_KEYS:
        raise ConversationFinalizationError('invalid_enrichment_effect_plan')
    raw_transcript_vector_count = next(
        (getattr(effect, 'resource_count', 0) for effect in effects if effect.key == 'transcript_vectors'),
        0,
    )
    cleanup_transcript_vector_count = (
        raw_transcript_vector_count
        if isinstance(raw_transcript_vector_count, int) and not isinstance(raw_transcript_vector_count, bool)
        else 0
    )

    async def cleanup_source_change() -> None:
        if finalization_vector_generation_id is not None:
            await _cleanup_deleted_conversation_enrichment(
                uid,
                conversation.id,
                finalization_vector_generation_id=finalization_vector_generation_id,
                transcript_vector_count=cleanup_transcript_vector_count,
                require_vector_store=checkpoint,
            )

    for effect in effects:
        if effect.key in completed_effects:
            continue
        _raise_if_finalization_lease_lost(lease_lost)
        if checkpoint and effect.key == 'transcript_vectors':
            prepared = await run_blocking(
                db_executor,
                lifecycle_service.prepare_finalization_effect,
                finalization_job_id,
                dispatch_generation,
                lease_epoch,
                effect.key,
                effect.resource_count,
            )
            if prepared in {'conversation_missing', 'conversation_replaced'}:
                await cleanup_source_change()
                return False
            if prepared != 'completed':
                raise ConversationFinalizationError('effect_preparation_conflict')

        async def read_boundary(*, persist_effect: bool) -> str:
            return await run_blocking(
                db_executor,
                lifecycle_service.complete_finalization_effect,
                finalization_job_id,
                dispatch_generation,
                lease_epoch,
                effect.key,
                persist_effect=persist_effect,
            )

        try:
            await _run_postprocess_mutation(effect.execute)
        except asyncio.CancelledError:
            boundary = await read_boundary(persist_effect=False)
            if boundary in {'conversation_missing', 'conversation_replaced'}:
                await cleanup_source_change()
            raise
        except Exception:
            boundary = await read_boundary(persist_effect=False)
            if boundary in {'conversation_missing', 'conversation_replaced'}:
                await cleanup_source_change()
                return False
            raise
        boundary = await read_boundary(persist_effect=checkpoint and not lease_lost.is_set())
        if boundary in {'conversation_missing', 'conversation_replaced'}:
            await cleanup_source_change()
            return False
        if boundary != 'completed':
            raise ConversationFinalizationError('effect_checkpoint_conflict')
        _raise_if_finalization_lease_lost(lease_lost)
        if checkpoint:
            completed_effects.add(effect.key)
    return True


async def _finish_missing_conversation_cleanup(
    uid: str,
    conversation_id: str,
    *,
    plan_version: int,
    finalization_job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    preserve_completed_fanout: bool,
    finalization_vector_generation_id: str,
    transcript_vector_count: int,
) -> ConversationFinalizationDisposition:
    await _cleanup_deleted_conversation_enrichment(
        uid,
        conversation_id,
        finalization_vector_generation_id=finalization_vector_generation_id,
        transcript_vector_count=transcript_vector_count,
        require_vector_store=plan_version == PLAN_VERSION,
    )
    if preserve_completed_fanout:
        return ConversationFinalizationDisposition.completed
    fenced = await run_blocking(
        db_executor,
        lifecycle_service.complete_finalization_enrichment_cleanup,
        finalization_job_id,
        dispatch_generation,
        lease_epoch,
    )
    if not fenced:
        raise ConversationFinalizationError('enrichment_cleanup_fence_conflict')
    return ConversationFinalizationDisposition.fenced


async def finalize_persisted_conversation(
    uid: str,
    conversation_id: str,
    language: str | None = None,
    *,
    finalization_job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    force_process: bool = False,
) -> ConversationFinalizationDisposition:
    """Finalize persisted data once the caller has acquired the job lease.

    The pusher WebSocket request already installs request-scoped BYOK context
    before calling this helper.  Cloud Tasks never does, so it cannot silently
    substitute platform credentials for a BYOK job.
    """
    conversation_data = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
    if not conversation_data:
        # A prior delivery can have durably completed fanout just before the
        # worker crashes.  Preserve that acknowledgement even if the row is
        # deleted before replay, so the caller can close its current lease.
        fanout = await run_blocking(
            db_executor,
            lifecycle_service.claim_finalization_fanout,
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
        )
        if fanout['status'] == 'completed':
            return ConversationFinalizationDisposition.completed
        if fanout['status'] in {'cleanup_required', 'completed_cleanup_required'}:
            generation_id = fanout.get('finalization_vector_generation_id')
            if not isinstance(generation_id, str) or not generation_id:
                raise ConversationFinalizationError('missing_enrichment_cleanup_generation')
            return await _finish_missing_conversation_cleanup(
                uid,
                conversation_id,
                plan_version=int(fanout.get('plan_version', 1)),
                finalization_job_id=finalization_job_id,
                dispatch_generation=dispatch_generation,
                lease_epoch=lease_epoch,
                preserve_completed_fanout=fanout['status'] == 'completed_cleanup_required',
                finalization_vector_generation_id=generation_id,
                transcript_vector_count=int(fanout.get('transcript_vector_count') or 0),
            )
        if fanout['status'] != 'fenced':
            raise ConversationFinalizationError('missing_conversation_fanout_claim_conflict')
        # A deleted conversation is a successful no-fanout outcome. Retrying
        # its lease would only risk resurrecting a stale processor result.
        logger.info(
            'persisted conversation finalization fenced because row is missing uid=%s conversation=%s',
            uid,
            conversation_id,
        )
        return ConversationFinalizationDisposition.fenced

    raw_finalization_job_id = conversation_data.get('finalization_job_id')
    expected_finalization_identity = (
        conversation_data.get('finalization_incarnation_id'),
        finalization_job_id,
        conversation_data.get('finalization_revision'),
    )
    conversation = deserialize_conversation(conversation_data)
    if conversation.status != ConversationStatus.completed and raw_finalization_job_id not in {
        None,
        finalization_job_id,
    }:
        return ConversationFinalizationDisposition.fenced
    if conversation.status != ConversationStatus.completed and conversation.status != ConversationStatus.processing:
        admitted = await run_blocking(db_executor, lifecycle_service.ensure_processing, uid, conversation.id)
        if not admitted:
            return ConversationFinalizationDisposition.fenced
        conversation.status = ConversationStatus.processing

    heartbeat_stop = asyncio.Event()
    lease_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _run_finalization_lease_heartbeat(
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
            stop_event=heartbeat_stop,
            lease_lost=lease_lost,
        ),
        name='conversation-finalization-lease-heartbeat',
    )
    fanout_claimed = True
    try:
        geolocation = await run_blocking(db_executor, get_cached_user_geolocation, uid)
        if geolocation:
            geolocation = Geolocation(**geolocation)
            # Keep the cached coordinates when the geocode lookup misses instead of dropping them.
            conversation.geolocation = await async_resolve_geolocation(geolocation)

        # The post-processing bulkhead preserves request context (including
        # validated live BYOK keys) while isolating this expensive sync path
        # from WebSocket and Cloud Tasks event loops.
        resolved_language = language or getattr(conversation, 'language', None) or 'en'
        persistence: dict[str, bool] = {'owned': True}
        derived_effects: list[Callable[[], None]] = []
        should_run_best_effort_bundle = not lifecycle_service.finalization_derived_effects_completed(
            conversation_data, expected_finalization_identity
        )
        if should_run_best_effort_bundle:
            conversation = await _run_postprocess_mutation(
                process_conversation,
                uid,
                resolved_language,
                conversation,
                force_process=force_process,
                defer_derived_effects=True,
                defer_required_enrichment=True,
                expected_finalization_identity=expected_finalization_identity,
                persistence_observer=lambda owned: persistence.__setitem__('owned', owned),
                derived_effects_observer=derived_effects.append,
                replay_derived_effects=conversation.status == ConversationStatus.completed,
            )
        # If lifecycle persistence lost to discard/terminal state, no canonical
        # memory or derived side effect may happen.  process_conversation
        # reports this through the observer and returns without side effects;
        # the finalizer must honour that result before touching memories.
        if not persistence['owned']:
            logger.info(
                'persisted conversation finalization fenced: lifecycle persistence lost uid=%s conversation=%s',
                uid,
                conversation_id,
            )
            return ConversationFinalizationDisposition.fenced

        _raise_if_finalization_lease_lost(lease_lost)
        # Ownership fence before any canonical side effect.  The lifecycle
        # transaction re-reads the durable conversation together with the job
        # lease, so a discard or superseding generation cannot slip between a
        # stale pre-read and the derived-effect bundle.  This fence must
        # precede every derived effect (calendar, usage/app, vector,
        # action/goal, audio, webhook, memory) so a losing finalizer produces
        # zero canonical side effects (#10468 r5).
        fanout = await run_blocking(
            db_executor,
            lifecycle_service.claim_finalization_fanout,
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
        )
        if fanout['status'] == 'completed':
            return ConversationFinalizationDisposition.completed
        plan_version = int(fanout.get('plan_version', 1))
        if fanout['status'] in {'cleanup_required', 'completed_cleanup_required'}:
            generation_id = fanout.get('finalization_vector_generation_id')
            if not isinstance(generation_id, str) or not generation_id:
                raise ConversationFinalizationError('missing_enrichment_cleanup_generation')
            return await _finish_missing_conversation_cleanup(
                uid,
                conversation_id,
                plan_version=plan_version,
                finalization_job_id=finalization_job_id,
                dispatch_generation=dispatch_generation,
                lease_epoch=lease_epoch,
                preserve_completed_fanout=fanout['status'] == 'completed_cleanup_required',
                finalization_vector_generation_id=generation_id,
                transcript_vector_count=int(fanout.get('transcript_vector_count') or 0),
            )
        if fanout['status'] == 'fenced':
            logger.info(
                'persisted conversation finalization fenced before derived effects uid=%s conversation=%s',
                uid,
                conversation_id,
            )
            return ConversationFinalizationDisposition.fenced
        if fanout['status'] != 'claimed':
            raise ConversationFinalizationError('fanout_lease_conflict')
        if plan_version not in {1, PLAN_VERSION}:
            raise ConversationFinalizationError('unsupported_enrichment_effect_plan')
        generation_id = fanout.get('finalization_vector_generation_id')
        if plan_version == PLAN_VERSION and not isinstance(generation_id, str):
            raise ConversationFinalizationError('missing_enrichment_effect_generation')
        effect_generation_id = generation_id if plan_version == PLAN_VERSION else None
        refreshed_data = await run_blocking(
            db_executor,
            conversations_db.get_conversation,
            uid,
            conversation_id,
        )
        if not refreshed_data:
            if isinstance(effect_generation_id, str):
                return await _finish_missing_conversation_cleanup(
                    uid,
                    conversation_id,
                    plan_version=plan_version,
                    finalization_job_id=finalization_job_id,
                    dispatch_generation=dispatch_generation,
                    lease_epoch=lease_epoch,
                    preserve_completed_fanout=False,
                    finalization_vector_generation_id=effect_generation_id,
                    transcript_vector_count=int(fanout.get('transcript_vector_count') or 0),
                )
            return ConversationFinalizationDisposition.fenced
        resolved_geolocation = conversation.geolocation
        conversation = deserialize_conversation(refreshed_data)
        if resolved_geolocation is not None and conversation.geolocation is None:
            conversation.geolocation = resolved_geolocation

        # Best-effort effects retain their existing bundle. Required enrichment
        # is awaited separately and v2 jobs checkpoint each completed effect.
        _raise_if_finalization_lease_lost(lease_lost)
        if derived_effects:
            await _run_postprocess_mutation(derived_effects[0])
        elif should_run_best_effort_bundle and not conversation.discarded:
            await _run_postprocess_mutation(extract_memories, uid, conversation)
        _raise_if_finalization_lease_lost(lease_lost)
        if should_run_best_effort_bundle:
            checkpointed = await run_blocking(
                db_executor,
                lifecycle_service.checkpoint_finalization_derived_effects,
                uid,
                conversation_id,
                expected_finalization_identity,
            )
            if not checkpointed:
                raise ConversationFinalizationError('derived_effect_checkpoint_fenced')
        _raise_if_finalization_lease_lost(lease_lost)
        conversation_exists = await _run_required_enrichment(
            uid,
            conversation,
            finalization_job_id=finalization_job_id,
            dispatch_generation=dispatch_generation,
            lease_epoch=lease_epoch,
            completed_effects=(set(fanout.get('completed_effects') or ()) if plan_version == PLAN_VERSION else set()),
            checkpoint=plan_version == PLAN_VERSION,
            lease_lost=lease_lost,
            finalization_vector_generation_id=effect_generation_id,
            transcript_vector_count=(fanout.get('transcript_vector_count') if plan_version == PLAN_VERSION else None),
        )
        if not conversation_exists:
            fenced = await run_blocking(
                db_executor,
                lifecycle_service.complete_finalization_enrichment_cleanup,
                finalization_job_id,
                dispatch_generation,
                lease_epoch,
            )
            if not fenced:
                raise ConversationFinalizationError('enrichment_cleanup_fence_conflict')
            return ConversationFinalizationDisposition.fenced
        _raise_if_finalization_lease_lost(lease_lost)
        # Vector providers are outside Firestore, so the source can be deleted
        # after the last effect checkpoint. Reclaim the same fenced fanout
        # immediately before external delivery to close that boundary.
        post_effect_fanout = await run_blocking(
            db_executor,
            lifecycle_service.claim_finalization_fanout,
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
        )
        if post_effect_fanout['status'] == 'completed':
            return ConversationFinalizationDisposition.completed
        if post_effect_fanout['status'] in {'cleanup_required', 'completed_cleanup_required'}:
            cleanup_generation_id = post_effect_fanout.get('finalization_vector_generation_id')
            if not isinstance(cleanup_generation_id, str) or not cleanup_generation_id:
                raise ConversationFinalizationError('missing_enrichment_cleanup_generation')
            return await _finish_missing_conversation_cleanup(
                uid,
                conversation_id,
                plan_version=int(post_effect_fanout.get('plan_version', 1)),
                finalization_job_id=finalization_job_id,
                dispatch_generation=dispatch_generation,
                lease_epoch=lease_epoch,
                preserve_completed_fanout=post_effect_fanout['status'] == 'completed_cleanup_required',
                finalization_vector_generation_id=cleanup_generation_id,
                transcript_vector_count=int(post_effect_fanout.get('transcript_vector_count') or 0),
            )
        if post_effect_fanout['status'] == 'fenced':
            return ConversationFinalizationDisposition.fenced
        if post_effect_fanout['status'] != 'claimed':
            raise ConversationFinalizationError('post_enrichment_fanout_lease_conflict')
        await trigger_external_integrations(
            uid,
            conversation,
            idempotency_key=post_effect_fanout['fanout_key'],
            require_delivery=True,
        )
        _raise_if_finalization_lease_lost(lease_lost)
        # Publish the content-free capture-arrival intent before marking the
        # durable fanout projection completed. Desktop waits on that projection
        # before waking Chat; ordering the marker first closes the small window
        # where a completed projection existed without a notes-ready intent.
        source = getattr(conversation, 'source', None)
        source_value = getattr(source, 'value', source)
        meeting_treatment_eligible = is_meeting_treatment_eligible(conversation)
        if (source_value == 'omi' and not getattr(conversation, 'discarded', False)) or meeting_treatment_eligible:
            try:
                structured = getattr(conversation, 'structured', None)
                summary = getattr(structured, 'title', '') or getattr(structured, 'overview', '') or ''
                if meeting_treatment_eligible:
                    persist_capture_arrival_intent(
                        uid,
                        conversation_id=conversation_id,
                        summary=summary,
                        is_desktop_meeting=True,
                        recommended_action_items=recommended_meeting_action_items(structured),
                    )
                else:
                    persist_capture_arrival_intent(uid, conversation_id=conversation_id, summary=summary)
            except Exception as error:
                logger.warning(
                    'chat-first capture arrival intent failed during finalization uid=%s error=%s',
                    sanitize_pii(uid),
                    type(error).__name__,
                )
        fanout_completed = await run_blocking(
            db_executor,
            lifecycle_service.complete_finalization_fanout,
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
            meeting_treatment_eligible=meeting_treatment_eligible,
        )
        if not fanout_completed:
            raise ConversationFinalizationError('fanout_completion_conflict')
        return ConversationFinalizationDisposition.completed
    except Exception as error:
        # Provider and validation exceptions can contain transcript excerpts.
        # The job stores and logs only a bounded failure code.
        logger.error(
            'persisted conversation finalization failed uid=%s conversation=%s failure=processing_failed',
            uid,
            conversation_id,
        )
        raise ConversationFinalizationError('processing_failed') from error
    finally:
        heartbeat_stop.set()
        await heartbeat_task
        if fanout_claimed:
            try:
                await run_blocking(
                    db_executor,
                    lifecycle_service.release_finalization_fanout,
                    finalization_job_id,
                    dispatch_generation,
                    lease_epoch,
                )
            except Exception:
                logger.error('persisted conversation finalization fanout drain release failed')
