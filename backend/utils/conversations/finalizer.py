"""Shared persisted-conversation finalizer for pusher and Cloud Tasks workers.

This is intentionally not callable from the listen WebSocket as a local
fallback.  Callers must first own a durable finalization job lease.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from enum import Enum

from fastapi import HTTPException
from config.batch_pipeline import RecordOwnerContention
from config.episodes import episodes_enabled_for
from config.rollout_cohorts import warm_rollout_cohorts

from database import conversations as conversations_db
from database import conversation_finalization_jobs as finalization_jobs_db
from database.firestore_read_metrics import FirestoreReadSite
from database.redis_db import get_cached_user_geolocation
from models.conversation_enums import ConversationStatus
from models.geolocation import Geolocation
from utils.app_integrations import trigger_external_integrations
from utils.conversations.factory import deserialize_conversation
from utils.conversations.call_metadata import apply_call_metadata
from utils.conversations.duplicate_capture import link_duplicate_captures
from utils.conversations.location import async_resolve_geolocation
from utils.conversations.episode_runtime import process_with_episode_budget
from utils.conversations.processing_trigger import is_recovery_trigger
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.smart_merge import smart_merge_step
from utils.conversations.smart_merge_policy import is_donor
from utils.conversations.meeting_evidence_admission import await_meeting_evidence
from utils.conversations.meeting_receipt import record_finalized_meeting_receipt
from utils.conversations.process_conversation import (
    DerivedEffectsDisposition,
    TERMINAL_NO_DERIVED_EFFECTS_FIELD,
    extract_memories,
    process_conversation,
    save_structured_vector,
)
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.lifecycle_clocks import overlap_snapshot
from utils.episodes.client_gate import client_seen as episode_client_seen
from utils.episodes.finalize import close_now as close_episode_now
from utils.conversations.summary_delivery import finalization_pending
from utils.executors import db_executor, lifecycle_executor, run_blocking
from utils.metrics import OMI_CONVERSATION_SUMMARY_VECTOR_UPSERTS_TOTAL
from utils.llm.gateway_error_contract import GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL
from utils.observability.finalization import (
    classify_finalization_failure,
    finalization_diagnostic_id,
    record_finalization_failure,
)
from utils.speaker_learning_jobs import schedule_person_voice_learning_retry
from services.conversation_keyframes import ensure_conversation_keyframe_job, reconcile_conversation_keyframe_jobs
from utils.retrieval.frame_request_authority import resolve_frame_request_authority
from utils.observability.fallback import record_fallback
from utils.batch_pipeline.live import register_recording, reserve_recording

logger = logging.getLogger(__name__)


def _maybe_start_shadow(uid: str, conversation) -> None:
    # Keep the optional provider/storage import chain off the canonical
    # finalizer path, including when this module is loaded by isolated tests.
    if os.getenv('TRANSCRIPTION_SHADOW_ENABLED', 'false').lower() != 'true':
        return
    if os.getenv('TRANSCRIPTION_SHADOW_KILL_SWITCH', 'false').lower() == 'true':
        return
    try:
        from utils.conversations.transcription_shadow import maybe_start_shadow

        maybe_start_shadow(uid, conversation)
    except Exception as error:
        logger.warning('event=transcription_shadow outcome=admission_failed exception_type=%s', type(error).__name__)


def _save_summary_vector_fail_soft(uid: str, conversation) -> None:
    """Provider errors are counted by the writer; never propagate to finalization."""
    if getattr(conversation, 'processing_deferred', False) is True:
        OMI_CONVERSATION_SUMMARY_VECTOR_UPSERTS_TOTAL.labels(outcome='skipped_processing_deferred').inc()
        return
    try:
        if save_structured_vector(uid, conversation) is False:
            # The writer counts a missing index as error. Keep that bounded outcome.
            logger.warning('summary_vector outcome=error exception_type=IndexUnavailable')
            record_fallback(
                component='conversation_finalization',
                from_mode='none',
                to_mode='none',
                reason='other',
                outcome='degraded',
                log=logger,
            )
    except Exception as error:
        logger.warning('summary_vector outcome=error exception_type=%s', type(error).__name__)
        record_fallback(
            component='conversation_finalization',
            from_mode='none',
            to_mode='none',
            reason='other',
            outcome='degraded',
            log=logger,
        )


EPISODE_FINALIZE_TIMEOUT_SECONDS = 30.0
EPISODE_CLOSE_TIMEOUT_SECONDS = 5.0


def record_episode_finalized(uid: str, conversation_id: str, row: Any, **kwargs: Any) -> str:
    """Deferred import: the episodes overlay (and its Firestore transaction helpers) loads only
    when a conversation actually finalizes, never at finalizer import."""
    from utils.episodes.service import on_conversation_finalized

    return on_conversation_finalized(uid, conversation_id, row, **kwargs)


async def _episode_after_finalization(
    uid: str,
    conversation_id: str,
    row: Any,
    trigger: ProcessingTrigger,
    *,
    absorbed_from: str | None = None,
) -> None:
    """Live episode bookkeeping after the job completed; never affects finalization.

    Runs after ``complete_finalization_fanout``, so a slow or failing episode
    update can neither delay nor fail the conversation (``utils/episodes``).
    """
    if not row:
        return
    try:
        await asyncio.wait_for(
            run_blocking(
                lifecycle_executor(uid, episode=True),
                record_episode_finalized,
                uid,
                conversation_id,
                row,
                trigger=trigger.value,
                absorbed_from=absorbed_from,
            ),
            timeout=EPISODE_FINALIZE_TIMEOUT_SECONDS,
        )
    except Exception as error:
        logger.warning('event=episode_finalize outcome=error exception_type=%s', type(error).__name__)


async def _episode_at_finalization_start(uid: str, conversation_id: str, row: Any, trigger: ProcessingTrigger) -> None:
    """Close the live episode when the finalize starts; bounded, and never affects finalization."""
    if not row or not episodes_enabled_for(uid):
        return
    try:
        await asyncio.wait_for(
            run_blocking(db_executor, close_episode_now, uid, conversation_id, trigger, row.get('source')),
            timeout=EPISODE_CLOSE_TIMEOUT_SECONDS,
        )
    except Exception as error:
        logger.warning('event=episode_finalize_close outcome=error exception_type=%s', type(error).__name__)


async def _episode_after_absorb(uid: str, donor_id: str, trigger: ProcessingTrigger) -> None:
    if not episodes_enabled_for(uid):
        return
    try:
        # No capable client, no episode to repoint: skip the donor read (utils/episodes/client_gate.py).
        if not await run_blocking(db_executor, episode_client_seen, uid):
            return
        donor = await run_blocking(db_executor, conversations_db.get_conversation, uid, donor_id)
        survivor_id = ((donor or {}).get('smart_merge') or {}).get('survivor_id')
        if not survivor_id:
            return
        await _episode_after_finalization(uid, str(survivor_id), donor, trigger, absorbed_from=donor_id)
    except Exception as error:
        logger.warning('event=episode_finalize outcome=error exception_type=%s', type(error).__name__)


class ConversationFinalizationError(RuntimeError):
    """A retryable persisted-conversation finalization failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ConversationFinalizationDisposition(str, Enum):
    completed = 'completed'
    fenced = 'fenced'
    deferred = 'deferred'


async def finalize_persisted_conversation(
    uid: str,
    conversation_id: str,
    language: str | None = None,
    *,
    finalization_job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    trigger: ProcessingTrigger = ProcessingTrigger.CAPTURE_END,
    final_attempt: bool = False,
) -> ConversationFinalizationDisposition:
    """Finalize persisted data once the caller has acquired the job lease.

    The pusher WebSocket request already installs request-scoped BYOK context
    before calling this helper.  Cloud Tasks never does, so it cannot silently
    substitute platform credentials for a BYOK job.

    `final_attempt` says the job has no retry left, so a failed external
    integration delivery is dropped rather than dead-lettering the whole
    conversation for a third-party endpoint that is down.
    """
    fenced, conversation_data, conversation = await _load_admitted_conversation(
        uid, conversation_id, finalization_job_id, dispatch_generation, lease_epoch, trigger
    )
    if fenced is not None:
        return fenced
    await _episode_at_finalization_start(uid, conversation_id, conversation_data, trigger)

    silent_backfill = trigger is ProcessingTrigger.SILENT_BACKFILL

    if not silent_backfill and conversation.status != ConversationStatus.completed:
        outcome = await await_meeting_evidence(uid, conversation_id, conversation_data, trigger=trigger)
        if outcome != 'not_applicable':
            # Transcript tail segments can land during the wait. Process the durable row as it
            # is now, never the pre-wait snapshot: stale segments would be summarized and could
            # overwrite the newer live transcript on persist.
            fenced, conversation_data, conversation = await _load_admitted_conversation(
                uid, conversation_id, finalization_job_id, dispatch_generation, lease_epoch, trigger
            )
            if fenced is not None:
                return fenced

    stage = 'geolocation'
    try:
        if is_donor(conversation_data) and not silent_backfill:
            # Resume precedes the fanout fence, but never the job ownership fence.
            # A worker can wake after expiry/reclaim or after the job terminalizes.
            stage = 'donor_resume_admission'
            job = await run_blocking(db_executor, finalization_jobs_db.get_finalization_job, finalization_job_id)
            if not job or (
                job.get('status') != 'leased'
                or job.get('dispatch_generation') != dispatch_generation
                or job.get('lease_epoch') != lease_epoch
                or job.get('uid') != uid
                or job.get('conversation_id') != conversation_id
                or conversation_data.get('finalization_job_id') != finalization_job_id
                or conversation_data.get('finalization_revision') != job.get('finalization_revision')
            ):
                return ConversationFinalizationDisposition.fenced
            if job.get('fanout_status') == 'completed':
                return ConversationFinalizationDisposition.completed
            # A retry of a committed smart-merge absorb whose cleanup or survivor
            # refresh failed. The donor is discarded, so the fanout claim fences it;
            # finish the absorb first. A failure raises and stays retryable. Only
            # the claim transaction closes a job whose earlier attempt leased fanout.
            stage = 'smart_merge'
            await smart_merge_step(uid, conversation_id, conversation_data, trigger=trigger, owner=finalization_job_id)
            stage = 'fanout_claim'
            fanout = await run_blocking(
                db_executor,
                lifecycle_service.claim_finalization_fanout,
                finalization_job_id,
                dispatch_generation,
                lease_epoch,
            )
            if fanout['status'] == 'claimed':
                # Not admitted for a discarded row; close as the absorbing attempt does.
                stage = 'fanout_completion'
                if not await run_blocking(
                    db_executor,
                    lifecycle_service.complete_finalization_fanout,
                    finalization_job_id,
                    dispatch_generation,
                    lease_epoch,
                ):
                    raise ConversationFinalizationError('fanout_completion_conflict')
                await _episode_after_absorb(uid, conversation_id, trigger)
                return ConversationFinalizationDisposition.completed
            if fanout['status'] in {'completed', 'fenced'}:
                return ConversationFinalizationDisposition(fanout['status'])
            raise ConversationFinalizationError('fanout_lease_conflict')

        # A location persisted with the recording session or WAL is the
        # canonical start-time snapshot. Redis remains only a compatibility
        # fallback for clients released before that contract.
        persisted_geolocation = getattr(conversation, 'geolocation', None)
        if isinstance(persisted_geolocation, Geolocation) and not silent_backfill:
            conversation.geolocation = await async_resolve_geolocation(persisted_geolocation)
        elif not silent_backfill:
            geolocation = await run_blocking(db_executor, get_cached_user_geolocation, uid)
            if geolocation:
                record_fallback(
                    component='conversation_finalization',
                    from_mode='conversation_snapshot',
                    to_mode='redis_user_cache',
                    reason='other',
                    outcome='degraded',
                    log=logger,
                )
                cached_geo = Geolocation.deserialize_safe(geolocation)
                if cached_geo:
                    conversation.geolocation = await async_resolve_geolocation(cached_geo)
                else:
                    logger.warning('Skipping malformed cached user geolocation for uid=%s', uid)

        # The post-processing bulkhead preserves request context (including
        # validated live BYOK keys) while isolating this expensive sync path
        # from WebSocket and Cloud Tasks event loops.
        conversation = await run_blocking(db_executor, apply_call_metadata, uid, conversation)
        resolved_language = language or getattr(conversation, 'language', None) or 'en'
        # Admission only schedules a bounded shadow job. It never awaits audio,
        # STT or metric persistence and cannot alter this processing input.
        stage = 'processing'
        if conversation.status != ConversationStatus.completed:
            await warm_rollout_cohorts(uid)
            if not silent_backfill:
                _maybe_start_shadow(uid, conversation)
        persistence: dict[str, bool] = {'owned': True}
        derived_effects: list = []
        derived_disposition: list[DerivedEffectsDisposition] = [DerivedEffectsDisposition.RUN]
        if conversation.status != ConversationStatus.completed or finalization_pending(
            conversation_data, uid, finalization_job_id
        ):
            conversation = await run_blocking(
                lifecycle_executor(uid),
                process_with_episode_budget,
                process_conversation,
                uid,
                resolved_language,
                conversation,
                trigger=trigger,
                user_kept=bool(conversation_data.get('sync_relevance_user_kept')),
                recovery_transcript_decoded=conversation_data.get('_recovery_transcript_decoded') is True,
                defer_derived_effects=True,
                persistence_observer=lambda owned: persistence.__setitem__('owned', owned),
                derived_effects_observer=derived_effects.append,
                derived_effects_disposition_observer=lambda d: derived_disposition.__setitem__(0, d),
            )
        elif conversation_data.get(TERMINAL_NO_DERIVED_EFFECTS_FIELD):
            # The coordinator persisted a no-effects result (including budget waiting).
            # That write is durable; this request-scoped default is not. A
            # completed replay skips process_conversation, so restore the
            # disposition from the unmodeled marker before the empty-bundle
            # memory-extraction fallback can run.
            derived_disposition[0] = DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS
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

        # Producer rollback never abandons an already reserved retained recording.
        # Persist its obligation before the finalization job can complete.
        if not silent_backfill and conversation_data.get('record_lane_owner') == 'batch_live_v1':
            await run_blocking(db_executor, register_recording, uid, {**conversation_data, **conversation.model_dump()})

        # Ownership fence before any canonical side effect.  The lifecycle
        # transaction re-reads the durable conversation together with the job
        # lease, so a discard or superseding generation cannot slip between a
        # stale pre-read and the derived-effect bundle.  This fence must
        # precede every derived effect (calendar, usage/app, vector,
        # action/goal, audio, webhook, memory) so a losing finalizer produces
        # zero canonical side effects (#10468 r5).
        stage = 'fanout_claim'
        fanout = await run_blocking(
            db_executor,
            lifecycle_service.claim_finalization_fanout,
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
        )
        if silent_backfill:
            if fanout['status'] == 'completed':
                return ConversationFinalizationDisposition.completed
            if fanout['status'] == 'fenced':
                return ConversationFinalizationDisposition.fenced
            if fanout['status'] != 'claimed':
                raise ConversationFinalizationError('fanout_lease_conflict')
            if not await run_blocking(
                db_executor,
                lifecycle_service.complete_finalization_fanout,
                finalization_job_id,
                dispatch_generation,
                lease_epoch,
            ):
                raise ConversationFinalizationError('fanout_completion_conflict')
            return ConversationFinalizationDisposition.completed
        if fanout['status'] == 'claimed':
            # Folding into the preceding conversation happens behind the claim and
            # before any derived effect of this one; a donor skips all of them.
            stage = 'smart_merge'
            if await smart_merge_step(
                uid, conversation_id, conversation_data, trigger=trigger, owner=finalization_job_id
            ):
                stage = 'fanout_completion'
                if not await run_blocking(
                    db_executor,
                    lifecycle_service.complete_finalization_fanout,
                    finalization_job_id,
                    dispatch_generation,
                    lease_epoch,
                ):
                    raise ConversationFinalizationError('fanout_completion_conflict')
                await _episode_after_absorb(uid, conversation_id, trigger)
                return ConversationFinalizationDisposition.completed
        stage = 'duplicate_capture'
        if fanout['status'] in {'claimed', 'completed'}:
            await run_blocking(
                db_executor, link_duplicate_captures, uid, overlap_snapshot(uid, conversation, conversation_data)
            )
        if fanout['status'] == 'completed':
            schedule_person_voice_learning_retry(uid, conversation_id)
            # Re-finalization of a row whose fanout already completed (e.g.
            # server_recovery picking up a row finalized elsewhere). The
            # summary-vector emission below the claim branch is unreachable on
            # this path, so run the same fail-soft freshness guard here; a
            # summary-vector failure never fails finalization (#21111 gap).
            try:
                latest_data = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
                latest = deserialize_conversation(latest_data) if latest_data else None
                if (
                    latest
                    and latest_data is not None
                    and not latest_data.get('deleted', False)
                    and not getattr(latest, 'discarded', False)
                    and getattr(latest, 'structured', None)
                    and latest.structured == getattr(conversation, 'structured', None)
                ):
                    await run_blocking(lifecycle_executor(uid), _save_summary_vector_fail_soft, uid, latest)
                else:
                    OMI_CONVERSATION_SUMMARY_VECTOR_UPSERTS_TOTAL.labels(outcome='skipped_no_structured').inc()
            except Exception as error:
                OMI_CONVERSATION_SUMMARY_VECTOR_UPSERTS_TOTAL.labels(outcome='error').inc()
                logger.warning('summary_vector outcome=error exception_type=%s', type(error).__name__)
            return ConversationFinalizationDisposition.completed
        if fanout['status'] == 'fenced':
            logger.info(
                'persisted conversation finalization fenced before memory extraction uid=%s conversation=%s',
                uid,
                conversation_id,
            )
            return ConversationFinalizationDisposition.fenced
        if fanout['status'] != 'claimed':
            raise ConversationFinalizationError('fanout_lease_conflict')

        # Ownership is now proven.  Emit every derived side effect — calendar,
        # usage/app, action/goal, audio artifact/enqueue, webhook, and
        # memory extraction — only behind the winning claim. Summary indexing
        # also runs here, independently of the intelligence bundle.  A processing
        # conversation hands the bundle back from process_conversation; an
        # already-completed replay re-extracts memories behind the proven claim
        # unless the durable terminal marker is set (free-tier minimum).
        # TERMINAL_NO_DERIVED_EFFECTS suppresses only that intelligence bundle,
        # the empty-bundle memory fallback, and third-party app webhooks. Capture
        # receipt, keyframes, and arrival intent are not derived intelligence
        # (§1.7) and must still run so a free-tier desktop meeting wakes Chat.
        skip_derived_effects = derived_disposition[0] == DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS
        stage = 'derived_effects'
        from utils.conversations.demand_processing import lazy_enrichment_enabled

        lazy_effects = lazy_enrichment_enabled(uid) and not skip_derived_effects and not conversation.discarded
        if lazy_effects:
            from utils.sync.reprocess import mark_effects

            await run_blocking(db_executor, mark_effects, uid, conversation_id, resolved_language)
        # Completed-row replays have no coordinator bundle. Summary indexing is
        # independent of folder/apps receipts and terminal intelligence
        # suppression, but must share the same winning fanout claim.
        # Await inside a fail-soft boundary rather than detach a provider pipeline:
        # the worker can exit after completion, so awaiting preserves write observability.
        # A summary-vector failure never fails finalization, including terminal rows.
        episode_row = None
        try:
            latest_data = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
            episode_row = latest_data
            latest = deserialize_conversation(latest_data) if latest_data else None
            if (
                latest
                and latest_data is not None
                and not latest_data.get('deleted')
                and not getattr(latest, 'discarded', False)
                and getattr(latest, 'structured', None)
            ):
                # The claim does not return its document. Re-read after claim/merge;
                # compare summary content as well as the durable merge revision so an
                # older snapshot cannot overwrite a refresh that won during admission.
                if latest.structured != conversation.structured or latest_data.get(
                    'smart_merge'
                ) != conversation_data.get('smart_merge'):
                    OMI_CONVERSATION_SUMMARY_VECTOR_UPSERTS_TOTAL.labels(outcome='skipped_stale').inc()
                elif not lazy_effects:
                    await run_blocking(lifecycle_executor(uid), _save_summary_vector_fail_soft, uid, latest)
        except Exception as error:
            OMI_CONVERSATION_SUMMARY_VECTOR_UPSERTS_TOTAL.labels(outcome='error').inc()
            logger.warning('summary_vector outcome=error exception_type=%s', type(error).__name__)
            record_fallback(
                component='conversation_finalization',
                from_mode='none',
                to_mode='none',
                reason='other',
                outcome='degraded',
                log=logger,
            )
        if skip_derived_effects:
            logger.info(
                'persisted conversation finalization terminal with suppressed intelligence uid=%s conversation=%s',
                uid,
                conversation_id,
            )
        elif derived_effects:
            await run_blocking(lifecycle_executor(uid), derived_effects[0])
        elif not lazy_effects and not getattr(conversation, 'discarded', False):
            # A finalization job owns a durable lease. Keep canonical memory
            # extraction inside that lease so a temporary fail-closed gate
            # leaves the job retryable instead of dropping the source.
            stage = 'memory_extraction'
            await run_blocking(lifecycle_executor(uid), extract_memories, uid, conversation)
        stage = 'integrations'
        if not skip_derived_effects:
            await trigger_external_integrations(
                uid,
                conversation,
                idempotency_key=fanout['fanout_key'],
                require_delivery=True,
                last_delivery_attempt=final_attempt,
            )
        # Record the meeting treatment verdict; automatic Chat intents are retired.
        stage = 'meeting_receipt'
        await run_blocking(
            db_executor,
            record_finalized_meeting_receipt,
            uid,
            conversation,
            finalization_job_id=finalization_job_id,
        )
        # This is a metadata-only durable outbox write. Pixels remain local and
        # an offline desktop can satisfy it on a later screen-sync recovery.
        stage = 'keyframes'
        if not getattr(conversation, 'discarded', False):
            decision = await resolve_frame_request_authority(uid)
            if decision.enabled and decision.account_generation is not None:
                keyframe_eligible = await run_blocking(
                    db_executor,
                    ensure_conversation_keyframe_job,
                    uid,
                    conversation,
                )
                device_id = str(getattr(conversation, 'client_device_id', None) or '').strip()
                if keyframe_eligible and device_id:
                    await run_blocking(
                        db_executor,
                        reconcile_conversation_keyframe_jobs,
                        uid,
                        device_id=device_id,
                        account_generation=decision.account_generation,
                    )
        stage = 'fanout_completion'
        fanout_completed = await run_blocking(
            db_executor,
            lifecycle_service.complete_finalization_fanout,
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
        )
        if not fanout_completed:
            raise ConversationFinalizationError('fanout_completion_conflict')
        schedule_person_voice_learning_retry(uid, conversation_id)
        await _episode_after_finalization(uid, conversation_id, episode_row, trigger)
        return ConversationFinalizationDisposition.completed
    except Exception as error:
        # Provider and validation exceptions can contain transcript excerpts.
        # Collapse them onto a closed operational vocabulary before emitting a
        # metric or log; never include the exception message or user identity.
        # _get_structured wraps provider/parser errors in a safe HTTPException.
        # Its cause retains the original class, but neither message nor
        # traceback is safe to emit because either can contain transcript text.
        source_error = (
            error.__cause__
            if isinstance(error, HTTPException)
            and error.status_code == 500
            and error.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL
            and isinstance(error.__cause__, Exception)
            else error
        )
        reason = classify_finalization_failure(source_error)
        record_finalization_failure(reason)
        # WARNING, not ERROR: this fires on every failed attempt, including
        # attempts of conversations that later succeed on retry. The
        # authoritative terminality decision lives in the pusher-side handler
        # (utils/pusher_finalization.py), which escalates to ERROR exactly
        # when record_failure reports the attempt budget exhausted. Severity
        # is the fault-origin signal (FC-request-input-rejection-escapes-as-
        # server-fault); logging every retryable attempt at ERROR paged
        # operators for self-healing traffic (2026-09-06: 5-7/30min bursts
        # against ~210-255 healthy processing/30min).
        logger.warning(
            'persisted conversation finalization failed failure=processing_failed reason=%s '
            'stage=%s exception_type=%s job_hash=%s conversation_hash=%s dispatch_generation=%s',
            reason.value,
            stage,
            type(source_error).__name__,
            finalization_diagnostic_id(finalization_job_id),
            finalization_diagnostic_id(conversation_id),
            dispatch_generation,
        )
        raise ConversationFinalizationError('processing_failed') from error


async def _load_admitted_conversation(
    uid: str,
    conversation_id: str,
    finalization_job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    trigger: ProcessingTrigger,
) -> tuple[ConversationFinalizationDisposition | None, Any, Any]:
    """Read the durable conversation and admit it to processing.

    Returns ``(disposition, data, conversation)``; a non-None disposition ends
    finalization (a deleted row, or a row another owner moved on).
    """
    conversation_data = await run_blocking(
        db_executor,
        conversations_db.get_conversation,
        uid,
        conversation_id,
        read_site=FirestoreReadSite.FINALIZER_JOB_REPLAY,
        include_transcript_decode_status=is_recovery_trigger(trigger),
    )
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
            return ConversationFinalizationDisposition.completed, None, None
        if fanout['status'] != 'fenced':
            raise ConversationFinalizationError('missing_conversation_fanout_claim_conflict')
        # A deleted conversation is a successful no-fanout outcome. Retrying
        # its lease would only risk resurrecting a stale processor result.
        logger.info(
            'persisted conversation finalization fenced because row is missing uid=%s conversation=%s',
            uid,
            conversation_id,
        )
        return ConversationFinalizationDisposition.fenced, None, None

    if trigger is ProcessingTrigger.SILENT_BACKFILL and conversation_data.get('record_lane_owner'):
        return ConversationFinalizationDisposition.fenced, None, None
    for _ in range(3):
        try:
            owner = (
                None
                if trigger is ProcessingTrigger.SILENT_BACKFILL
                else await run_blocking(db_executor, reserve_recording, uid, conversation_data)
            )
            break
        except RecordOwnerContention:
            # Listen may append between the existing read and CAS. Refresh in
            # this attempt, rather than spending a processing-failure slot.
            conversation_data = await run_blocking(
                db_executor,
                conversations_db.get_conversation,
                uid,
                conversation_id,
                read_site=FirestoreReadSite.FINALIZER_JOB_REPLAY,
                include_transcript_decode_status=is_recovery_trigger(trigger),
            )
            if not conversation_data:
                return ConversationFinalizationDisposition.fenced, None, None
    else:
        deferred = await run_blocking(
            db_executor,
            finalization_jobs_db.mark_finalization_retryable,
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
            'record_owner_contention',
            count_attempt=False,
        )
        if not deferred:
            return ConversationFinalizationDisposition.fenced, None, None
        return ConversationFinalizationDisposition.deferred, None, None
    conversation = deserialize_conversation(conversation_data)
    if owner:
        conversation.record_lane_owner = owner
    if conversation.status != ConversationStatus.completed and conversation.status != ConversationStatus.processing:
        admitted = await run_blocking(db_executor, lifecycle_service.ensure_processing, uid, conversation.id)
        if not admitted:
            return ConversationFinalizationDisposition.fenced, None, None
        conversation.status = ConversationStatus.processing
    return None, conversation_data, conversation
