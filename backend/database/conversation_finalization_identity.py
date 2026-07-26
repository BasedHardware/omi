"""Atomic compatibility identity for reprocessing legacy conversations."""

from __future__ import annotations

from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.conversation_finalization_effects import stamp_finalization_incarnation
from database.conversation_write_fence import account_deletion_blocks_writes

CONVERSATIONS_COLLECTION = 'conversations'


def ensure_conversation_finalization_identity(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
) -> tuple[str, str | None, int | None] | None:
    """Return a valid row identity, stamping a legacy conversation atomically.

    Rows created before ``finalization_incarnation_id`` was introduced may still
    carry a valid finalization job/revision binding. Reprocess callers need a
    durable incarnation before reading content for processing so a delete and
    same-ID recreation cannot accept the stale result.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection(CONVERSATIONS_COLLECTION).document(conversation_id)

    @firestore.transactional
    def _ensure(transaction) -> tuple[str, str | None, int | None] | None:
        if account_deletion_blocks_writes(uid, transaction, client):
            return None
        snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(snapshot, 'exists', False):
            return None

        current = snapshot.to_dict() or {}
        if current.get('deleted') or current.get('vector_cleanup_pending'):
            return None

        incarnation_id = current.get('finalization_incarnation_id')
        finalization_job_id = current.get('finalization_job_id')
        finalization_revision = current.get('finalization_revision')
        has_job_id = finalization_job_id is not None
        has_revision = finalization_revision is not None
        if has_job_id != has_revision:
            return None
        if has_job_id and (not isinstance(finalization_job_id, str) or not finalization_job_id):
            return None
        if has_revision and (
            not isinstance(finalization_revision, int)
            or isinstance(finalization_revision, bool)
            or finalization_revision < 1
        ):
            return None
        if incarnation_id is not None and (not isinstance(incarnation_id, str) or not incarnation_id):
            return None

        if incarnation_id is None:
            identity_update: dict[str, Any] = {}
            stamp_finalization_incarnation(identity_update, current)
            incarnation_id = identity_update['finalization_incarnation_id']
            transaction.update(conversation_ref, {'finalization_incarnation_id': incarnation_id})

        return incarnation_id, finalization_job_id, finalization_revision

    return run_transactional(client, _ensure)
