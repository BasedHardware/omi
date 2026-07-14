"""The exclusive owner of conversation lifecycle mutations.

Drivers submit typed intents here; this module owns lifecycle state changes and
the durable finalization handoff. Database helpers remain storage primitives,
including the atomic outbox transaction, but no router or processor may mutate
lifecycle fields directly.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from database import conversation_finalization_jobs as jobs_db
from database import conversations as conversations_db
from models.conversation_enums import ConversationStatus
from utils.cloud_tasks import enqueue_listen_finalization_job, is_listen_finalization_dispatch_enabled
from utils.observability.fallback import record_fallback

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
}


class LifecycleTransitionError(ValueError):
    """Raised when an intent would reopen or otherwise violate a terminal lifecycle."""


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
        return conversations_db._create_conversation_if_absent_with_lifecycle(uid, conversation_data)
    conversations_db._upsert_conversation_with_lifecycle(uid, conversation_data)
    return True


def create_processing_conversation(uid: str, conversation_data: dict[str, Any], *, idempotent: bool = False) -> bool:
    """Create a server/import/merge conversation already admitted to processing."""
    _require_status(conversation_data, ConversationStatus.processing)
    if idempotent:
        return conversations_db._create_conversation_if_absent_with_lifecycle(uid, conversation_data)
    conversations_db._upsert_conversation_with_lifecycle(uid, conversation_data)
    return True


def persist_processed_conversation(uid: str, conversation_data: dict[str, Any]) -> None:
    """Persist only a processing result; callers cannot use it to reopen a terminal row."""
    _require_status(
        conversation_data,
        ConversationStatus.processing,
        ConversationStatus.completed,
        ConversationStatus.failed,
    )
    conversations_db._upsert_conversation_with_lifecycle(uid, conversation_data)


def persist_imported_conversation(uid: str, conversation_data: dict[str, Any]) -> None:
    """Persist an externally completed immutable import through the lifecycle owner."""
    _require_status(conversation_data, ConversationStatus.completed)
    conversations_db._upsert_conversation_with_lifecycle(uid, conversation_data)


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
        return conversations_db._claim_conversation_status(
            uid,
            conversation_id,
            expected,
            target,
            extra_updates=extra_updates,
        )
    conversations_db._transition_conversation_status(uid, conversation_id, target)
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
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise LifecycleTransitionError(f'conversation {conversation_id} does not exist')
    status = _status_value(conversation.get('status'))
    if status == ConversationStatus.completed.value:
        return False
    return transition(uid, conversation_id, ConversationStatus.completed)


def begin_merge(uid: str, conversation_id: str) -> bool:
    return transition(uid, conversation_id, ConversationStatus.merging)


def discard(uid: str, conversation_id: str) -> None:
    """Discard is terminal and deliberately cannot be undone by a generic write."""
    conversations_db._set_conversation_as_discarded(uid, conversation_id)


def restore_discarded(uid: str, conversation_id: str) -> None:
    """An explicit user intent may restore visibility without changing status."""
    conversations_db.update_conversation(uid, conversation_id, {'discarded': False})


def request_finalization(
    uid: str,
    conversation_id: str,
    *,
    has_byok_keys: bool,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Atomically admit finalization and choose its sole durable handoff route."""
    intent = jobs_db.create_or_get_finalization_intent(
        uid,
        conversation_id,
        requires_byok=has_byok_keys,
        firestore_client=firestore_client,
    )
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
