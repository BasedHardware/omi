"""Account-deletion state transitions and deletion-scoped resource reads."""

from datetime import datetime, timezone

from google.cloud.firestore_v1 import transactional


@transactional
def mark_wipe_completed(transaction, doc_ref) -> bool:
    transaction.set(
        doc_ref,
        {'wipe_status': 'completed', 'wipe_completed_at': datetime.now(timezone.utc)},
        merge=True,
    )
    return True
