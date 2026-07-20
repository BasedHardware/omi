"""The exclusive owner of conversation lifecycle mutations.

Drivers submit typed intents here; this module owns lifecycle state changes and
the durable finalization handoff. Database helpers remain storage primitives,
including the atomic outbox transaction, but no router or processor may mutate
lifecycle fields directly.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Mapping

from database import conversation_finalization_jobs as jobs_db
from database import conversations as conversations_db
from database import recording_sessions as recording_sessions_db
from database.firestore_transaction_retry import FirestoreContentionExhausted
from models.conversation_enums import ConversationStatus
from utils.cloud_tasks import (
    enqueue_listen_finalization_job,
    is_listen_finalization_dispatch_configured,
    is_listen_finalization_dispatch_enabled,
)
from utils.conversations.finalization_decision import (
    FinalizationDecisionState,
    FinalizationEvent,
    LifecyclePhase,
    decide_finalization,
)
from utils.observability.fallback import record_fallback
from utils.observability.journeys import record_journey_accepted

logger = logging.getLogger(__name__)

_STATUS_TRANSITIONS = {
    ConversationStatus.in_progress.value: {
        ConversationStatus.processing.value,
        ConversationStatus.merging.value,
        ConversationStatus.failed.value,
    },
    ConversationStatus.processing.value: {
        ConversationStatus.completed.value,
        ConversationStatus.failed.value,
    },
    ConversationStatus.merging.value: {ConversationStatus.completed.value, ConversationStatus.failed.value},
    # Merge admission rejects every status except completed (validate_merge_compatibility), so
    # completed is the only status that can reach begin_merge. Without this edge every accepted
    # merge raises LifecycleTransitionError. The merging -> completed edge above is its rollback.
    ConversationStatus.completed.value: {ConversationStatus.merging.value},
}


class LifecycleTransitionError(ValueError):
    """Raised when an intent would reopen or otherwise violate a terminal lifecycle."""


class FinalizationDispatchUnavailable(RuntimeError):
    """A caller cannot be admitted to the durable finalization path safely."""


RECORDING_SESSION_MODES = frozenset({'shadow', 'dual_write', 'enforce'})
_TERMINAL_RECORDING_SESSION_PHASES = frozenset({'completed', 'failed', 'discarded'})


def recording_session_mode() -> str:
    """Return the bounded recording-session rollout mode, defaulting to dual write."""
    configured = os.getenv('RECORDING_SESSION_MODE', 'dual_write').strip().lower()
    return configured if configured in RECORDING_SESSION_MODES else 'dual_write'


def _status_value(status: ConversationStatus | str | None) -> str:
    if isinstance(status, ConversationStatus):
        return status.value
    if isinstance(status, str):
        return status
    raise LifecycleTransitionError('conversation status is required')


def _require_status(data: Mapping[str, Any], *allowed: ConversationStatus) -> None:
    status = _status_value(data.get('status'))
    if status not in {candidate.value for candidate in allowed}:
        raise LifecycleTransitionError(f'lifecycle persistence rejects status={status}')


def create_in_progress_conversation(uid: str, conversation_data: dict[str, Any], *, idempotent: bool = False) -> bool:
    """Create the one durable in-progress resource for a recording generation."""
    _require_status(conversation_data, ConversationStatus.in_progress)
    if idempotent:
        return conversations_db.create_conversation_if_absent_with_lifecycle(uid, conversation_data)
    conversations_db.upsert_conversation_with_lifecycle(uid, conversation_data)
    return True


def create_processing_conversation(uid: str, conversation_data: dict[str, Any], *, idempotent: bool = False) -> bool:
    """Create a server/import/merge conversation already admitted to processing."""
    _require_status(conversation_data, ConversationStatus.processing)
    if idempotent:
        return conversations_db.create_conversation_if_absent_with_lifecycle(uid, conversation_data)
    conversations_db.upsert_conversation_with_lifecycle(uid, conversation_data)
    return True


def create_completed_conversation(uid: str, conversation_data: dict[str, Any], *, idempotent: bool = False) -> bool:
    """Create a fully processed conversation without granting processors recreate authority."""
    _require_status(conversation_data, ConversationStatus.completed)
    if idempotent:
        return conversations_db.create_conversation_if_absent_with_lifecycle(uid, conversation_data)
    conversations_db.upsert_conversation_with_lifecycle(uid, conversation_data)
    return True


def persist_processed_conversation(uid: str, conversation_data: dict[str, Any]) -> bool:
    """Persist a processing result and report whether its generation was still current.

    ``False`` fences a stale or discarded processor.  Callers must stop before
    emitting derived side effects such as webhooks or integration fanout.
    """
    _require_status(
        conversation_data,
        ConversationStatus.processing,
        ConversationStatus.completed,
        ConversationStatus.failed,
    )
    status = _status_value(conversation_data['status'])
    expected = (
        {ConversationStatus.in_progress.value, ConversationStatus.processing.value}
        if status == ConversationStatus.processing.value
        else {
            ConversationStatus.processing.value,
            ConversationStatus.merging.value,
            # Reprocess overwrites an already-completed conversation's
            # generated content; the lifecycle guard must not fence it out.
            ConversationStatus.completed.value,
        }
    )
    return conversations_db.persist_processing_result_with_lifecycle(
        uid,
        conversation_data,
        expected_statuses=expected,
    )


def persist_imported_conversation(uid: str, conversation_data: dict[str, Any]) -> None:
    """Persist an externally completed immutable import through the lifecycle owner."""
    _require_status(conversation_data, ConversationStatus.completed)
    conversations_db.upsert_conversation_with_lifecycle(uid, conversation_data)


def transition(
    uid: str,
    conversation_id: str,
    target: ConversationStatus,
    *,
    expected: ConversationStatus | None = None,
    extra_updates: dict[str, Any] | None = None,
) -> bool:
    """Apply one typed status transition, failing closed on stale or invalid state."""
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise LifecycleTransitionError(f'conversation {conversation_id} does not exist')
    if conversation.get('discarded'):
        return False
    current = _status_value(conversation.get('status'))
    if expected is not None and current != expected.value:
        return False
    if target.value not in _STATUS_TRANSITIONS.get(current, set()):
        raise LifecycleTransitionError(f'invalid lifecycle transition {current}->{target.value}')
    if expected is not None:
        return conversations_db.claim_conversation_status(
            uid,
            conversation_id,
            expected,
            target,
            extra_updates=extra_updates,
        )
    conversations_db.transition_conversation_status(uid, conversation_id, target)
    return True


def admit_processing(uid: str, conversation_id: str, *, extra_updates: dict[str, Any] | None = None) -> bool:
    """The single compare-and-swap admission point for finalization processing."""
    return transition(
        uid,
        conversation_id,
        ConversationStatus.processing,
        expected=ConversationStatus.in_progress,
        extra_updates=extra_updates,
    )


def ensure_processing(uid: str, conversation_id: str) -> bool:
    """Make a claimed finalizer's expected state explicit without reopening terminals."""
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise LifecycleTransitionError(f'conversation {conversation_id} does not exist')
    status = _status_value(conversation.get('status'))
    if status == ConversationStatus.processing.value:
        return True
    if status in {ConversationStatus.completed.value, ConversationStatus.failed.value}:
        return False
    return admit_processing(uid, conversation_id)


def complete(uid: str, conversation_id: str) -> bool:
    """Close an admitted processing or merge generation exactly once."""
    if conversations_db.claim_conversation_status(
        uid,
        conversation_id,
        ConversationStatus.processing,
        ConversationStatus.completed,
    ):
        return True
    return conversations_db.claim_conversation_status(
        uid,
        conversation_id,
        ConversationStatus.merging,
        ConversationStatus.completed,
    )


def rollback_processing_admission(uid: str, conversation_id: str) -> bool:
    """Return a failed synchronous finalization's admission to in_progress.

    The HTTP finalize endpoints admit processing and then run the processor
    inside the request itself, with no durable job for the reconciler to
    replay. If that processor raises, the admission must be undone — otherwise
    the conversation is stranded on ``processing`` forever and every client
    shows a stuck "Processing" card. The compare-and-swap only rolls back a
    generation that is still processing, so a concurrent completion, discard,
    or newer generation always wins.
    """
    return conversations_db.claim_conversation_status(
        uid,
        conversation_id,
        ConversationStatus.processing,
        ConversationStatus.in_progress,
    )


@contextmanager
def processing_admission_guard(uid: str, conversation_id: str):
    """Guard an inline (in-request) processing run against stranding its admission.

    Wrap the synchronous ``process_conversation`` call with this; if it raises,
    the lifecycle owner rolls the admission back to ``in_progress`` and re-raises.
    A rollback error (e.g. the conversation was deleted mid-processing) is
    logged instead of replacing the original processing exception.
    """
    try:
        yield
    except Exception:
        try:
            rolled_back = rollback_processing_admission(uid, conversation_id)
        except Exception:
            logger.exception('processing admission rollback failed uid=%s conversation=%s', uid, conversation_id)
            rolled_back = False
        logger.exception(
            'synchronous conversation processing failed uid=%s conversation=%s rolled_back=%s',
            uid,
            conversation_id,
            rolled_back,
        )
        raise


def fail_and_discard_processing(uid: str, conversation_id: str) -> bool:
    """Atomically close a still-current failed finalization generation.

    A worker can exhaust its durable delivery budget while its conversation is
    processing. The compare-and-swap fences a stale worker from hiding a newer
    or already-completed generation.
    """
    return conversations_db.claim_conversation_status(
        uid,
        conversation_id,
        ConversationStatus.processing,
        ConversationStatus.failed,
        extra_updates={'discarded': True},
    )


def begin_merge(uid: str, conversation_id: str) -> bool:
    return transition(uid, conversation_id, ConversationStatus.merging)


def discard(uid: str, conversation_id: str) -> None:
    """Discard is terminal and deliberately cannot be undone by a generic write."""
    conversations_db.set_conversation_as_discarded(uid, conversation_id)


def restore_discarded(uid: str, conversation_id: str) -> None:
    """An explicit user intent may restore visibility without changing status."""
    conversations_db.restore_conversation_from_discarded(uid, conversation_id)


def open_recording_session(
    uid: str,
    recording_session_id: str,
    proposed_conversation_id: str,
    *,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Open or resume a durable session through the single lifecycle owner.

    Shadow mode observes binding conflicts while preserving the legacy proposed
    route. Enforce mode fails closed to the canonical durable conversation.
    """
    try:
        binding = recording_sessions_db.create_or_get_recording_session(
            uid,
            recording_session_id,
            proposed_conversation_id,
            firestore_client=firestore_client,
        )
    except Exception:
        if recording_session_mode() == 'enforce':
            raise
        record_fallback(
            component='other',
            from_mode='recording_session',
            to_mode='legacy_pointer',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        logger.exception(
            'recording session persistence failed; retaining shadow legacy route uid=%s session=%s',
            uid,
            recording_session_id,
        )
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': proposed_conversation_id,
            'lifecycle_version': None,
            'lifecycle_phase': None,
            'lifecycle_sequence': None,
            'mapping_conflict': False,
        }
    if binding['mapping_conflict']:
        record_fallback(
            component='other',
            from_mode='legacy_pointer',
            to_mode='recording_session',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        logger.warning(
            'recording session binding conflict uid=%s session=%s proposed=%s canonical=%s',
            uid,
            recording_session_id,
            proposed_conversation_id,
            binding['conversation_id'],
        )
        if recording_session_mode() in {'shadow', 'dual_write'}:
            # Compatibility routing must not borrow the canonical session's
            # ordered envelope for a different legacy conversation. The
            # client receives the pre-envelope route until enforce cutover.
            return dict(binding) | {
                'conversation_id': proposed_conversation_id,
                'lifecycle_version': None,
                'lifecycle_phase': None,
                'lifecycle_sequence': None,
            }
    return dict(binding)


def record_recording_session_event(
    uid: str,
    recording_session_id: str,
    conversation_id: str,
    phase: recording_sessions_db.RecordingPhase,
    *,
    firestore_client: Any = None,
) -> dict[str, Any] | None:
    """Persist and return an ordered client envelope, discarding stale callbacks."""
    try:
        event = recording_sessions_db.record_lifecycle_event(
            uid,
            recording_session_id,
            conversation_id,
            phase,
            firestore_client=firestore_client,
        )
    except Exception:
        if recording_session_mode() == 'enforce':
            raise
        record_fallback(
            component='other',
            from_mode='recording_session',
            to_mode='legacy_pointer',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        logger.exception(
            'recording session event persistence failed; emitting shadow legacy event uid=%s session=%s',
            uid,
            recording_session_id,
        )
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': conversation_id,
            'lifecycle_version': None,
            'lifecycle_phase': None,
            'lifecycle_sequence': None,
        }
    if event['accepted']:
        return dict(event)
    record_fallback(
        component='other',
        from_mode='recording_session',
        to_mode='event_discarded',
        reason='other',
        outcome='degraded',
        log=logger,
    )
    logger.warning(
        'recording session event discarded uid=%s session=%s conversation=%s reason=%s',
        uid,
        recording_session_id,
        conversation_id,
        event['discard_reason'],
    )
    if recording_session_mode() in {'shadow', 'dual_write'}:
        # Dual-write continues the legacy route on an identity mismatch. The
        # canonical session has correctly rejected this event, but suppressing
        # the legacy envelope would strand the current desktop completion flow.
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': conversation_id,
            'lifecycle_version': None,
            'lifecycle_phase': None,
            'lifecycle_sequence': None,
        }
    return None


def tombstone_recording_session(
    uid: str,
    recording_session_id: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
) -> dict[str, Any] | None:
    """Terminally close an empty listen generation before its row is deleted."""
    return record_recording_session_event(
        uid,
        recording_session_id,
        conversation_id,
        'discarded',
        firestore_client=firestore_client,
    )


def delete_empty_recording_conversation(
    uid: str,
    conversation_id: str,
    recording_session_id: str | None,
) -> bool:
    """Delete only a still-empty listen generation and tombstone it atomically."""
    deleted = recording_sessions_db.tombstone_and_delete_empty_conversation(
        uid,
        conversation_id,
        recording_session_id,
    )
    if deleted:
        # Parent deletion is transactionally fenced with content writes; photos
        # are a subcollection and need their physical cleanup afterwards.
        conversations_db.delete_conversation_photos(uid, conversation_id)
    return deleted


def open_live_recording_session(
    uid: str,
    recording_session_id: str,
    proposed_conversation_id: str,
    *,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Open a live binding or require a fresh generation for a missing old row.

    A recording-session document can outlive a deliberately deleted empty
    conversation. Such a binding is a tombstone, never an authority to create
    the old conversation ID again.
    """
    existing = recording_sessions_db.get_recording_session(
        uid,
        recording_session_id,
        firestore_client=firestore_client,
    )
    binding = open_recording_session(
        uid,
        recording_session_id,
        proposed_conversation_id,
        firestore_client=firestore_client,
    )
    if existing is None:
        return dict(binding) | {'requires_rollover': False}

    conversation = conversations_db.get_conversation(uid, existing['conversation_id'])
    if conversation is not None:
        return dict(binding) | {'requires_rollover': False}

    if existing['lifecycle_phase'] not in _TERMINAL_RECORDING_SESSION_PHASES:
        tombstone_recording_session(
            uid,
            recording_session_id,
            existing['conversation_id'],
            firestore_client=firestore_client,
        )
    return dict(binding) | {'requires_rollover': True}


def _finalization_decision_state(conversation: Mapping[str, Any], conversation_id: str) -> FinalizationDecisionState:
    if conversation.get('discarded'):
        return FinalizationDecisionState(phase=LifecyclePhase.DISCARDED, terminal_outcome=LifecyclePhase.DISCARDED)
    status = str(conversation.get('status') or ConversationStatus.in_progress.value)
    revision = int(conversation.get('finalization_revision') or 0) + 1
    fanout_key = f'conversation:{conversation_id}:finalization:{revision}'
    if status == ConversationStatus.completed.value:
        return FinalizationDecisionState(phase=LifecyclePhase.COMPLETED, terminal_outcome=LifecyclePhase.COMPLETED)
    if status == ConversationStatus.failed.value:
        return FinalizationDecisionState(phase=LifecyclePhase.FAILED, terminal_outcome=LifecyclePhase.FAILED)
    if status == ConversationStatus.processing.value:
        return FinalizationDecisionState(
            phase=LifecyclePhase.PROCESSING,
            emitted_fanout_keys=frozenset({fanout_key}),
        )
    return FinalizationDecisionState()


def _finalization_admission(
    conversation: Mapping[str, Any],
    conversation_id: str,
) -> jobs_db.FinalizationAdmission:
    """Run the pure reducer against the transaction's authoritative snapshot."""
    revision = int(conversation.get('finalization_revision') or 0) + 1
    fanout_key = f'conversation:{conversation_id}:finalization:{revision}'
    decision = decide_finalization(
        _finalization_decision_state(conversation, conversation_id),
        FinalizationEvent.FINALIZE,
        conversation_id=conversation_id,
        fanout_key=fanout_key,
    )
    return {
        'accepted': decision.fanout_key is not None,
        'terminal': decision.reason == 'terminal',
        'reason': decision.reason,
        'fanout_key': decision.fanout_key,
    }


def claim_finalization_fanout(
    job_id: str, dispatch_generation: int, lease_epoch: int
) -> jobs_db.FinalizationFanoutClaim:
    """Claim the durable external-integration fanout through the lifecycle owner."""
    return jobs_db.claim_finalization_fanout(job_id, dispatch_generation, lease_epoch)


def complete_finalization_fanout(job_id: str, dispatch_generation: int, lease_epoch: int) -> bool:
    """Persist completion only after the idempotency-keyed fanout succeeds."""
    return jobs_db.mark_finalization_fanout_completed(job_id, dispatch_generation, lease_epoch)


def complete_fenced_finalization(job_id: str, dispatch_generation: int, lease_epoch: int) -> bool:
    """Close a current finalization lease when durable state fenced its fanout."""
    return jobs_db.mark_finalization_fenced(job_id, dispatch_generation, lease_epoch)


def request_finalization(
    uid: str,
    conversation_id: str,
    *,
    has_byok_keys: bool,
    force_process: bool = False,
    extra_updates: Mapping[str, Any] | None = None,
    require_cloud_tasks: bool = False,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Atomically admit finalization and choose its sole durable handoff route."""
    if require_cloud_tasks and not is_listen_finalization_dispatch_configured():
        # A REST request has no pusher session to execute an inline handoff.
        # Reject before mutating the conversation instead of persisting work
        # that this deployment cannot recover or dispatch.
        raise FinalizationDispatchUnavailable('durable conversation finalization worker is not configured')

    try:
        intent = jobs_db.create_or_get_finalization_intent(
            uid,
            conversation_id,
            requires_byok=has_byok_keys,
            finalization_admission=lambda conversation: _finalization_admission(conversation, conversation_id),
            force_process=force_process,
            extra_updates=extra_updates,
            firestore_client=firestore_client,
        )
    except FirestoreContentionExhausted as error:
        # An exhausted contention budget is a clean retry boundary: no outbox
        # mutation committed, so callers must not fall back to inline work.
        raise FinalizationDispatchUnavailable('durable finalization admission is temporarily contended') from error
    # The outbox transaction is the authoritative acceptance boundary. Count
    # only newly-created jobs so an idempotent re-dispatch cannot inflate traffic.
    if intent.get('created'):
        record_journey_accepted('capture_finalization')
    status = intent['status']
    if intent['job_id'] is None or status in {'missing', 'no_content', 'deferred', 'completed', 'dead_letter'}:
        return dict(intent) | {'route': 'noop'}

    if intent['requires_byok']:
        if not has_byok_keys:
            record_fallback(
                component='pusher',
                from_mode='cloud_tasks',
                to_mode='blocked_byok',
                reason='byok',
                outcome='degraded',
                log=logger,
            )
            return dict(intent) | {'route': 'blocked_byok'}
        resumed = jobs_db.resume_blocked_byok_job_for_live_session(intent['job_id'], firestore_client=firestore_client)
        return dict(resumed) | {'route': 'pusher'}

    if not is_listen_finalization_dispatch_enabled():
        return dict(intent) | {'route': 'pusher'}

    try:
        enqueue_listen_finalization_job(intent['job_id'], int(intent['dispatch_generation'] or 1))
    except Exception:
        record_fallback(
            component='pusher',
            from_mode='cloud_tasks',
            to_mode='durable_queued',
            reason='enqueue_failed',
            outcome='degraded',
            log=logger,
        )
        logger.exception('listen finalization enqueue failed job=%s', intent['job_id'])
        return dict(intent) | {'route': 'queued'}
    return dict(intent) | {'route': 'cloud_tasks'}


def get_finalization_status(uid: str, conversation_id: str) -> dict[str, Any] | None:
    """Return the authoritative, privacy-safe state for this conversation's job."""
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        return None
    job_id = conversation.get('finalization_job_id')
    if not isinstance(job_id, str) or not job_id:
        return None
    job = jobs_db.get_finalization_job(job_id)
    if not job or job.get('uid') != uid or job.get('conversation_id') != conversation_id:
        return None

    status = str(job.get('status') or 'unknown')
    return {
        'job_id': job_id,
        'status': status,
        'terminal': status in jobs_db.TERMINAL_JOB_STATUSES,
        # A queued job may be safely replayed by the reconciler; a leased job
        # is actively owned until its fenced lease expires.
        'retryable': status == 'queued',
        'attempt_count': int(job.get('attempt_count') or 0),
        'task_retry_count': int(job.get('task_retry_count') or 0),
    }
