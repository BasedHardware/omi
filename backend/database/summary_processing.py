"""First-summary worker fence using the conversation snapshot already loaded.

One conditional write, zero extra reads. A short outbox lease is safe only
because a replaced/expired owner cannot persist through the lifecycle writer.
"""

import time
from typing import Any

from google.api_core.exceptions import FailedPrecondition, NotFound
from google.cloud import firestore

from utils.conversations.summary_delivery import PROCESS_CONTEXT


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
