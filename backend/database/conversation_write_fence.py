"""Account-deletion fences shared by conversation write transactions."""

from typing import Any

from google.cloud import firestore

_ACCOUNT_DELETION_WRITE_BLOCKING_STATUSES = frozenset(
    {'deleting_auth', 'pending', 'retrying', 'running', 'failed', 'completed'}
)


def account_deletion_blocks_writes(uid: str, transaction: Any, client: Any) -> bool:
    """Return whether durable account-deletion authority fences conversation writes."""
    deletion_ref = client.collection('account_deletions').document(uid)
    snapshot = deletion_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    return data.get('wipe_status') in _ACCOUNT_DELETION_WRITE_BLOCKING_STATUSES


def create_if_absent(uid: str, conversation_ref: Any, data: dict, client: Any) -> bool:
    transaction = client.transaction()

    @firestore.transactional
    def _create(transaction) -> bool:
        if account_deletion_blocks_writes(uid, transaction, client):
            return False
        if getattr(conversation_ref.get(transaction=transaction), 'exists', False):
            return False
        transaction.create(conversation_ref, data)
        return True

    return _create(transaction)
