"""First-summary worker fence using the conversation snapshot already loaded.

One conditional claim write, zero extra reads. The request heartbeats its
outbox lease; only a replacement owner fences the lifecycle writer.
"""

import time
from typing import Any

from google.api_core.exceptions import FailedPrecondition, NotFound
from google.cloud import firestore

from utils.conversations.summary_delivery import PROCESS_CONTEXT

MAX_EMPTY_FAILURES = 3
EMPTY_BLOCKED_REASON = 'empty_output_exhausted'


def claim_from_snapshot(client: Any, uid: str, conversation_id: str, row: dict[str, Any]) -> bool:
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


def record_empty_failure(client: Any, collection: str, document_id: str, owner: str, token: str) -> bool:
    """Cap empty-output retries and remove terminal debt atomically.

    Never touch structured content, including a summary committed before a
    lost acknowledgement. All reads precede writes, and both owner and task
    token must still match before this attempt can record a failure.
    """
    outbox = client.collection(collection).document(document_id)

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        old = outbox.get(transaction=transaction).to_dict() or {}
        if old.get('owner') != owner or old.get('task_token') != token or old.get('dormant'):
            return False
        failures = min(MAX_EMPTY_FAILURES, old.get('summary_empty_failures', 0) + 1)
        blocked = failures >= MAX_EMPTY_FAILURES
        updates: dict[str, Any] = {'summary_empty_failures': failures}
        if blocked:
            reference = (
                client.collection('users')
                .document(old['uid'])
                .collection('conversations')
                .document(old['conversation_id'])
            )
            conversation = reference.get(transaction=transaction).to_dict() or {}
            enriched = bool(conversation.get('summary_output_present') or conversation.get('summary_completed_at'))
            if not enriched and conversation.get('summary_processing_owner') != owner:
                return False
            if not enriched:
                transaction.update(
                    reference,
                    {
                        'summary_empty_failures': failures,
                        'summary_blocked_reason': EMPTY_BLOCKED_REASON,
                        'summary_due_at': None,
                    },
                )
            updates.update(
                dormant=True,
                due_at=None,
                lease_until=0,
                summary_seen=enriched,
                summary_blocked_reason=None if enriched else EMPTY_BLOCKED_REASON,
            )
        transaction.update(outbox, updates)
        return blocked

    return commit(client.transaction())
