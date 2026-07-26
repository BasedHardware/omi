"""Durable checkpoint for the replayable conversation derived-effect bundle."""

from collections.abc import Mapping
from typing import Any

from google.cloud import firestore

from database._client import db
from database.conversation_write_fence import account_deletion_blocks_writes

_IDENTITY_FIELDS = ('finalization_incarnation_id', 'finalization_job_id', 'finalization_revision')
_CHECKPOINT_FIELD = 'finalization_derived_effects_identity'


def completed(
    conversation: Mapping[str, Any],
    expected_identity: tuple[str | None, str | None, int | None],
) -> bool:
    value = conversation.get(_CHECKPOINT_FIELD)
    return isinstance(value, (list, tuple)) and tuple(value) == expected_identity


def checkpoint(
    uid: str,
    conversation_id: str,
    expected_identity: tuple[str | None, str | None, int | None],
) -> bool:
    conversation_ref = db.collection('users').document(uid).collection('conversations').document(conversation_id)
    transaction = db.transaction()

    @firestore.transactional
    def _checkpoint(transaction) -> bool:
        if account_deletion_blocks_writes(uid, transaction, db):
            return False
        snapshot = conversation_ref.get(transaction=transaction)
        current = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if (
            not isinstance(current, Mapping)
            or current.get('vector_cleanup_pending')
            or tuple(current.get(field) for field in _IDENTITY_FIELDS) != expected_identity
        ):
            return False
        transaction.update(conversation_ref, {_CHECKPOINT_FIELD: list(expected_identity)})
        return True

    return _checkpoint(transaction)
