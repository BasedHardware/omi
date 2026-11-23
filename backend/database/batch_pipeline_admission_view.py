"""Read current batch admission evidence for the authenticated conversation APIs."""

from typing import Any

from database.batch_pipeline_store import FirestoreStore
from database.firestore_retry import FIRESTORE_NO_RETRY


def read_jobs(
    store: FirestoreStore, uid: str, conversation_ids: list[str], *, limit: int, timeout: float
) -> list[dict[str, Any]]:
    """Query the primary's owner-scoped evidence; the sampled mirror cannot prove the current state."""
    docs = (
        store.client.collection(f'{store.namespace}_jobs')
        .where('owner_id', '==', uid)
        .where('conversation_id', 'in', conversation_ids)
        .select(
            (
                'owner_id',
                'conversation_id',
                'state',
                'compute_decision',
                'recovery_state',
                'available_at',
                'lease_until',
                'ready_at',
            )
        )
        .limit(limit)
        .stream(timeout=timeout, retry=FIRESTORE_NO_RETRY)
    )
    return [doc.to_dict() for doc in docs]
