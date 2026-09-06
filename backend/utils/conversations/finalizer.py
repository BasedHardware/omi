"""Shared persisted-conversation finalizer for pusher and Cloud Tasks workers.

This is intentionally not callable from the listen WebSocket as a local
fallback.  Callers must first own a durable finalization job lease.
"""

from __future__ import annotations

import logging
from enum import Enum

from database import conversations as conversations_db
from database.firestore_read_metrics import FirestoreReadSite
from database.redis_db import get_cached_user_geolocation
from models.conversation_enums import ConversationStatus
from models.geolocation import Geolocation
from utils.app_integrations import trigger_external_integrations
from utils.conversations.factory import deserialize_conversation
from utils.conversations.location import async_resolve_geolocation
from utils.conversations.meeting_receipt import record_and_persist_finalized_meeting_receipt
from utils.conversations.process_conversation import (
    DerivedEffectsDisposition,
    TERMINAL_NO_DERIVED_EFFECTS_FIELD,
    extract_memories,
    process_conversation,
)
from utils.conversations import lifecycle as lifecycle_service
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.jit_rollout import JITDecisionStage
from utils.log_sanitizer import sanitize_pii
from utils.observability.finalization import classify_finalization_failure, record_finalization_failure
from utils.task_intelligence.proactive_engine import persist_capture_arrival_intent
from services.conversation_keyframes import ensure_conversation_keyframe_job, reconcile_conversation_keyframe_jobs
from utils.retrieval.frame_request_authority import resolve_frame_request_authority
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


class ConversationFinalizationError(RuntimeError):
    """A retryable persisted-conversation finalization failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ConversationFinalizationDisposition(str, Enum):
    completed = 'completed'
    fenced = 'fenced'


async def finalize_persisted_conversation(
    uid: str,
    conversation_id: str,
    language: str | None = None,
    *,
    finalization_job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    force_process: bool = False,
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
    conversation_data = await run_blocking(
        db_executor,
        conversations_db.get_conversation,
        uid,
        conversation_id,
        read_site=FirestoreReadSite.FINALIZER_JOB_REPLAY,
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
            return ConversationFinalizationDisposition.completed
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

    conversation = deserialize_conversation(conversation_data)
    if conversation.status != ConversationStatus.completed and conversation.status != ConversationStatus.processing:
        admitted = await run_blocking(db_executor, lifecycle_service.ensure_processing, uid, conversation.id)
        if not admitted:
            return ConversationFinalizationDisposition.fenced
        conversation.status = ConversationStatus.processing

    try:
        # A location persisted with the recording session or WAL is the
        # canonical start-time snapshot. Redis remains only a compatibility
        # fallback for clients released before that contract.
        persisted_geolocation = getattr(conversation, 'geolocation', None)
        if isinstance(persisted_geolocation, Geolocation):
            conversation.geolocation = await async_resolve_geolocation(persisted_geolocation)
        else:
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
                geolocation = Geolocation(**geolocation)
                conversation.geolocation = await async_resolve_geolocation(geolocation)

        # The post-processing bulkhead preserves request context (including
        # validated live BYOK keys) while isolating this expensive sync path
        # from WebSocket and Cloud Tasks event loops.
        resolved_language = language or getattr(conversation, 'language', None) or 'en'
        persistence: dict[str, bool] = {'owned': True}
        derived_effects: list = []
        derived_disposition: list[DerivedEffectsDisposition] = [DerivedEffectsDisposition.RUN]
        if conversation.status != ConversationStatus.completed:
            conversation = await run_blocking(
                postprocess_executor,
                process_conversation,
                uid,
                resolved_language,
                conversation,
                force_process=force_process,
                defer_derived_effects=True,
                persistence_observer=lambda owned: persistence.__setitem__('owned', owned),
                derived_effects_observer=derived_effects.append,
                derived_effects_disposition_observer=lambda d: derived_disposition.__setitem__(0, d),
            )
        elif conversation_data.get(TERMINAL_NO_DERIVED_EFFECTS_FIELD):
            # The coordinator already persisted a free-tier terminal minimum.
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
        # usage/app, vector, action/goal, audio artifact/enqueue, webhook, and
        # memory extraction — only behind the winning claim.  A processing
        # conversation hands the bundle back from process_conversation; an
        # already-completed replay re-extracts memories behind the proven claim
        # unless the durable terminal marker is set (free-tier minimum).
        # TERMINAL_NO_DERIVED_EFFECTS suppresses only that intelligence bundle,
        # the empty-bundle memory fallback, and third-party app webhooks. Capture
        # receipt, keyframes, and arrival intent are not derived intelligence
        # (§1.7) and must still run so a free-tier desktop meeting wakes Chat.
        skip_derived_effects = derived_disposition[0] == DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS
        if skip_derived_effects:
            logger.info(
                'persisted conversation finalization terminal with no derived effects uid=%s conversation=%s',
                uid,
                conversation_id,
            )
        elif derived_effects:
            await run_blocking(postprocess_executor, derived_effects[0])
        elif not getattr(conversation, 'discarded', False):
            # A finalization job owns a durable lease. Keep canonical memory
            # extraction inside that lease so a temporary fail-closed gate
            # leaves the job retryable instead of dropping the source.
            await run_blocking(postprocess_executor, extract_memories, uid, conversation)
        if not skip_derived_effects:
            await trigger_external_integrations(
                uid,
                conversation,
                idempotency_key=fanout['fanout_key'],
                require_delivery=True,
                last_delivery_attempt=final_attempt,
            )
        # Publish the content-free capture-arrival intent before marking the
        # durable fanout projection completed. Desktop waits on that projection
        # before waking Chat; ordering the marker first closes the small window
        # where a completed projection existed without a notes-ready intent.
        await run_blocking(
            db_executor,
            record_and_persist_finalized_meeting_receipt,
            uid,
            conversation,
            finalization_job_id=finalization_job_id,
        )
        # This is a metadata-only durable outbox write. Pixels remain local and
        # an offline desktop can satisfy it on a later screen-sync recovery.
        if not getattr(conversation, 'discarded', False):
            decision = await resolve_frame_request_authority(
                uid,
                stage=JITDecisionStage.INGRESS,
                force_refresh=True,
            )
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
        source = getattr(conversation, 'source', None)
        source_value = getattr(source, 'value', source)
        if source_value == 'omi' and not getattr(conversation, 'discarded', False):
            try:
                structured = getattr(conversation, 'structured', None)
                summary = getattr(structured, 'title', '') or getattr(structured, 'overview', '') or ''
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
        )
        if not fanout_completed:
            raise ConversationFinalizationError('fanout_completion_conflict')
        return ConversationFinalizationDisposition.completed
    except Exception as error:
        # Provider and validation exceptions can contain transcript excerpts.
        # Collapse them onto a closed operational vocabulary before emitting a
        # metric or log; never include the exception message or user identity.
        reason = classify_finalization_failure(error)
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
            'persisted conversation finalization failed failure=processing_failed reason=%s',
            reason.value,
        )
        raise ConversationFinalizationError('processing_failed') from error
