"""Permanent, content-free receipts for explicit user conversation deletion.

These receipts are separate from the conversation so physical content cleanup
cannot erase the decision. They have no TTL; recursive account deletion removes
them with the rest of users/{uid}. Temporary processor/merge cleanup never writes
a receipt.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client, run_transactional
from database.read_boundary import parse_snapshot_strict

CONVERSATION_DELETIONS_COLLECTION = 'conversation_deletions'
_SOURCE_BATCH_SIZE = 200  # At most one receipt and one source update per identity: <=400 writes.
_FANOUT_STATE_COLLECTION = 'conversation_deletion_state'
_FANOUT_STATE_DOC = 'fanout'


class ConversationDeletedError(LookupError):
    """An explicit user deletion permanently fences this conversation identity."""


class ConversationDeletionFanoutPendingError(RuntimeError):
    """Physical cleanup cannot erase ancestry needed to finish a user deletion."""


def deletion_receipt_ref(user_ref: Any, conversation_id: str) -> Any:
    receipt_id = hashlib.sha256(conversation_id.encode('utf-8')).hexdigest()
    return user_ref.collection(CONVERSATION_DELETIONS_COLLECTION).document(receipt_id)


def is_conversation_deleted(user_ref: Any, conversation_id: str, *, transaction: Any = None) -> bool:
    """Read the receipt within the caller's transaction when it will write content."""
    snapshot = deletion_receipt_ref(user_ref, conversation_id).get(transaction=transaction)
    if getattr(snapshot, 'exists', False):
        return True
    state = _fanout_state_data(_fanout_state_ref(user_ref).get(transaction=transaction))
    if _pending_fanouts(state) == 0:
        return False
    return _has_user_deleted_ancestor(user_ref, conversation_id, transaction=transaction)


def _fanout_state_ref(user_ref: Any) -> Any:
    return user_ref.collection(_FANOUT_STATE_COLLECTION).document(_FANOUT_STATE_DOC)


def _metadata_data(snapshot: Any) -> dict:
    if not getattr(snapshot, 'exists', False):
        return {}
    return parse_snapshot_strict(dict, snapshot)


def _fanout_state_data(snapshot: Any) -> dict:
    state = _metadata_data(snapshot)
    if snapshot.exists and 'pending_fanouts' not in state:
        raise RuntimeError('Conversation deletion state is unavailable')
    _pending_fanouts(state)
    return state


def _receipt_data(snapshot: Any) -> dict:
    receipt = _metadata_data(snapshot)
    if snapshot.exists:
        if (
            type(receipt.get('schema_version')) is not int
            or receipt.get('schema_version') != 1
            or not isinstance(receipt.get('deleted_at'), datetime)
        ):
            raise RuntimeError('Conversation deletion receipt is unavailable')
        for field in ('fanout_pending', 'fanout_complete'):
            if field in receipt and not isinstance(receipt[field], bool):
                raise RuntimeError('Conversation deletion receipt is unavailable')
    return receipt


def _pending_fanouts(state: dict) -> int:
    pending = state.get('pending_fanouts', 0)
    if not isinstance(pending, int) or isinstance(pending, bool) or pending < 0:
        raise RuntimeError('Conversation deletion state is unavailable')
    return pending


def _has_user_deleted_ancestor(user_ref: Any, conversation_id: str, *, transaction: Any = None) -> bool:
    # The single array filter uses existing automatic indexing. Do not limit
    # this query: an ordinary redirect donor may precede the user-deleted root.
    parents = (
        user_ref.collection('conversations')
        .where(filter=FieldFilter('sync_merged_from', 'array_contains', conversation_id))
        .select(['user_deleted'])
    )
    for snapshot in parents.stream(transaction=transaction):
        data = _metadata_data(snapshot)
        if 'user_deleted' in data and not isinstance(data['user_deleted'], bool):
            raise RuntimeError('Conversation deletion authority is unavailable')
        if data.get('user_deleted') is True:
            return True
    return False


def require_conversation_not_deleted(user_ref: Any, conversation_id: str, *, transaction: Any = None) -> None:
    if is_conversation_deleted(user_ref, conversation_id, transaction=transaction):
        raise ConversationDeletedError('Conversation was deleted')


def mark_conversation_deleted(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Fence a user-deleted row and its retained sync sources before content removal.

    A large ancestry first freezes its parent and activates a shared query
    fence. Bounded receipt batches then converge every source before the shared
    hint clears. A crash retains the parent/ancestry and active fence for retry.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection('conversations').document(conversation_id)

    @firestore.transactional
    def begin(transaction: Any) -> tuple[list[str], bool]:
        snapshot = conversation_ref.get(transaction=transaction, field_paths=['sync_merged_from'])
        current = _metadata_data(snapshot)
        sources = current.get('sync_merged_from') or []
        if not isinstance(sources, list) or not all(isinstance(source, str) and source for source in sources):
            raise ValueError('Conversation deletion requires valid sync ancestry')
        identities = sorted({conversation_id, *sources})
        root_ref = deletion_receipt_ref(user_ref, conversation_id)
        root_snapshot = root_ref.get(transaction=transaction)
        root = _receipt_data(root_snapshot)
        if root.get('fanout_complete'):
            return [], False
        if len(identities) <= _SOURCE_BATCH_SIZE and not root.get('fanout_pending'):
            return [], _stamp_source_receipts(transaction, user_ref, identities)
        if not snapshot.exists:
            raise ConversationDeletionFanoutPendingError('Pending conversation deletion lost its ancestry')
        state_ref = _fanout_state_ref(user_ref)
        state = _fanout_state_data(state_ref.get(transaction=transaction))
        pending = _pending_fanouts(state)
        added = not root_snapshot.exists
        if not root.get('fanout_pending'):
            if root_snapshot.exists:
                transaction.update(root_ref, {'fanout_pending': True})
            else:
                transaction.create(
                    root_ref,
                    {'schema_version': 1, 'deleted_at': datetime.now(timezone.utc), 'fanout_pending': True},
                )
            transaction.set(state_ref, {'pending_fanouts': pending + 1})
        transaction.update(conversation_ref, {'deleted': True, 'user_deleted': True})
        return identities, added

    identities, added = run_transactional(client, begin)
    for offset in range(0, len(identities), _SOURCE_BATCH_SIZE):
        _persist_source_receipt_batch(client, user_ref, identities[offset : offset + _SOURCE_BATCH_SIZE])
    if identities:
        _complete_fanout(client, user_ref, conversation_id)
    return added


def _stamp_source_receipts(transaction: Any, user_ref: Any, identities: list[str]) -> bool:
    receipt_refs = [deletion_receipt_ref(user_ref, identity) for identity in identities]
    receipt_snapshots = [ref.get(transaction=transaction) for ref in receipt_refs]
    source_refs = [user_ref.collection('conversations').document(identity) for identity in identities]
    source_snapshots = [
        ref.get(transaction=transaction, field_paths=['deleted', 'user_deleted']) for ref in source_refs
    ]
    added = False
    deleted_at = datetime.now(timezone.utc)
    for ref, snapshot in zip(receipt_refs, receipt_snapshots):
        if not snapshot.exists:
            transaction.create(ref, {'schema_version': 1, 'deleted_at': deleted_at})
            added = True
    for ref, snapshot in zip(source_refs, source_snapshots):
        current = _metadata_data(snapshot)
        if snapshot.exists and (current.get('deleted') is not True or current.get('user_deleted') is not True):
            transaction.update(ref, {'deleted': True, 'user_deleted': True})
    return added


def _persist_source_receipt_batch(client: Any, user_ref: Any, identities: list[str]) -> None:
    @firestore.transactional
    def stamp(transaction: Any) -> None:
        _stamp_source_receipts(transaction, user_ref, identities)

    run_transactional(client, stamp)


def _complete_fanout(client: Any, user_ref: Any, conversation_id: str) -> None:
    root_ref = deletion_receipt_ref(user_ref, conversation_id)
    state_ref = _fanout_state_ref(user_ref)

    @firestore.transactional
    def complete(transaction: Any) -> None:
        root = _receipt_data(root_ref.get(transaction=transaction))
        state = _fanout_state_data(state_ref.get(transaction=transaction))
        if not root.get('fanout_pending'):
            return
        pending = _pending_fanouts(state)
        if pending < 1:
            raise RuntimeError('Conversation deletion state is unavailable')
        transaction.update(root_ref, {'fanout_pending': False, 'fanout_complete': True})
        transaction.set(state_ref, {'pending_fanouts': pending - 1})

    run_transactional(client, complete)


def delete_conversation_parent(uid: str, conversation_id: str, *, firestore_client: Any = None) -> None:
    """Physical cleanup may not erase the anchor of an unfinished receipt fanout."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection('conversations').document(conversation_id)

    @firestore.transactional
    def remove(transaction: Any) -> None:
        root = _receipt_data(deletion_receipt_ref(user_ref, conversation_id).get(transaction=transaction))
        if root.get('fanout_pending'):
            raise ConversationDeletionFanoutPendingError('Conversation deletion receipts are still pending')
        transaction.delete(conversation_ref)

    run_transactional(client, remove)
