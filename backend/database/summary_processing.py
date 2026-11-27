"""First-summary worker fence using the conversation snapshot already loaded.

One conditional claim write, zero extra reads. The request heartbeats its
outbox lease; only a replacement owner fences the lifecycle writer.
"""

import logging
import time
from enum import Enum
from typing import Any

from google.api_core.exceptions import FailedPrecondition, NotFound
from google.cloud import firestore

from database._client import firestore_failure_reason, is_retryable_firestore_transaction_error, run_transactional
from models.finalization_owner import python_owns_finalization
from utils.conversations.summary_delivery import (
    PROCESS_CONTEXT,
    MAX_EMPTY_REARMS,
    EMPTY_BLOCKED_REASON,
    EMPTY_LIFETIME_BLOCKED_REASON,
)

MAX_EMPTY_FAILURES = 3

logger = logging.getLogger(__name__)


class EmptyFailureOutcome(Enum):
    RETRY = 'retry'
    BLOCKED = 'blocked'
    OWNER_MISMATCH = 'owner_mismatch'
    STALE = 'stale'
    # The row's content version moved on while this attempt ran, so its empty
    # output is not evidence about the current content. No strike is charged;
    # the caller re-arms the row for the newer version.
    SUPERSEDED = 'superseded'
    # The strike write itself could not land (expired transaction id or exhausted
    # contention). Nothing was recorded, so the caller must re-arm the row for a
    # bounded retry instead of failing the request.
    UNAVAILABLE = 'unavailable'


def claim_from_snapshot(client: Any, uid: str, conversation_id: str, row: dict[str, Any]) -> bool:
    if not python_owns_finalization(row):
        return False
    context = PROCESS_CONTEXT.get()
    if context is None or row.get('summary_completed_at'):
        return True
    if context['lease_until'] <= time.time():
        return False
    revision = row.get('updated_at')
    if revision is None:
        return False
    reference = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    try:
        reference.update(
            {'summary_processing_owner': context['owner'], 'summary_processing_lease_until': context['lease_until']},
            option=firestore.LastUpdateOption(revision),
        )
    except (FailedPrecondition, NotFound):
        return False
    context['claimed'] = True
    return True


def record_empty_failure(
    client: Any,
    collection: str,
    document_id: str,
    owner: str,
    token: str,
    *,
    expected_version: int | None = None,
) -> EmptyFailureOutcome:
    """Cap empty-output retries and remove terminal debt atomically.

    Never touch structured content, including a summary committed before a
    lost acknowledgement. All reads precede writes, and both owner and task
    token must still match before this attempt can record a failure.

    ``expected_version`` fences the strike to the content the callback actually
    ran on: a sync append bumps ``version`` without rotating the task token, so
    without this fence an empty output from older content would spend a strike
    against newer content and could block a summary that would have succeeded.
    """
    outbox = client.collection(collection).document(document_id)

    @firestore.transactional
    def commit(transaction: Any) -> EmptyFailureOutcome:
        old = outbox.get(transaction=transaction).to_dict() or {}
        if old.get('owner') != owner or old.get('task_token') != token or old.get('dormant'):
            return EmptyFailureOutcome.STALE
        if expected_version is not None and old.get('version') != expected_version:
            return EmptyFailureOutcome.SUPERSEDED
        reference = (
            client.collection('users').document(old['uid']).collection('conversations').document(old['conversation_id'])
        )
        conversation = reference.get(transaction=transaction).to_dict() or {}
        if not python_owns_finalization(conversation):
            return EmptyFailureOutcome.OWNER_MISMATCH
        enriched = bool(conversation.get('summary_output_present') or conversation.get('summary_completed_at'))
        if not enriched and conversation.get('summary_processing_owner') != owner:
            # This worker still owns the outbox, but lost the content fence.
            # Record the custody race without charging either failure budget.
            transaction.update(outbox, {'summary_empty_outcome': EmptyFailureOutcome.OWNER_MISMATCH.value})
            return EmptyFailureOutcome.OWNER_MISMATCH
        failures = min(MAX_EMPTY_FAILURES, old.get('summary_empty_failures', 0) + 1)
        blocked = failures >= MAX_EMPTY_FAILURES
        updates: dict[str, Any] = {
            'summary_empty_failures': failures,
            'summary_empty_outcome': 'empty_output',
            'summary_empty_version': old.get('version'),
        }
        first_week = old.get('first_week_summary')
        conversation_updates: dict[str, Any] = {}
        if isinstance(first_week, dict):
            attempts = old.get('first_week_attempts')
            attempts = attempts if type(attempts) is int and attempts > 0 else 0
            updates.update(first_week_attempts=attempts + 1, first_week_last_class='attempt_failed')
            conversation_updates.update(
                first_week_summary=first_week,
                first_week_attempts=attempts + 1,
                first_week_last_class='attempt_failed',
            )
        if blocked:
            blocked_reason = (
                EMPTY_LIFETIME_BLOCKED_REASON
                if conversation.get('summary_empty_rearms', 0) >= MAX_EMPTY_REARMS
                else EMPTY_BLOCKED_REASON
            )
            if not enriched:
                conversation_updates.update(
                    {
                        'summary_empty_failures': failures,
                        'summary_blocked_reason': blocked_reason,
                        'summary_due_at': None,
                    },
                )
            updates.update(
                dormant=True,
                due_at=None,
                lease_until=0,
                summary_seen=enriched,
                summary_blocked_reason=None if enriched else blocked_reason,
            )
        if conversation_updates:
            transaction.update(reference, conversation_updates)
        transaction.update(outbox, updates)
        return EmptyFailureOutcome.BLOCKED if blocked else EmptyFailureOutcome.RETRY

    try:
        # ``_Transactional`` replays the same transaction id on contention, which cannot
        # work once Firestore has retired that id; ``run_transactional`` restarts with a
        # fresh one. A strike that still cannot land must not fail the request: the row
        # keeps its debt and the caller re-arms it for a bounded retry.
        return run_transactional(client, commit)
    except Exception as error:
        if not is_retryable_firestore_transaction_error(error):
            raise
        logger.warning('event=summary_empty_failure outcome=unavailable reason=%s', firestore_failure_reason(error))
        return EmptyFailureOutcome.UNAVAILABLE
