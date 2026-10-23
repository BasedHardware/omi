"""Detached, operation-local redirect snapshot; never a mutation authority."""

from dataclasses import dataclass
from typing import Any

from database.conversation_revisions import firestore_revision_datetime


@dataclass(frozen=True)
class SyncConversationSnapshot:
    conversation_id: str
    document: Any

    def to_dict(self) -> dict:
        # Firestore DocumentSnapshot owns immutable stored data; to_dict returns
        # a deep copy so hydration cannot change the captured snapshot.
        data = self.document.to_dict()
        revision = firestore_revision_datetime(getattr(self.document, 'update_time', None))
        if revision is not None:
            data['updated_at'] = revision
        return data


def resolve_snapshot(
    uid: str, conversation_id: str, *, firestore_client: Any, max_hops: int = 16
) -> SyncConversationSnapshot | None:
    """Check every deletion marker and owner/path before returning the survivor.

    A new invocation always reads fresh documents. Nothing is shared with a
    transaction, a later callback, or another operation.
    """
    user = firestore_client.collection('users').document(uid)
    seen: set[str] = set()
    current_id = conversation_id
    for _ in range(max_hops):
        if current_id in seen or not current_id or '/' in current_id or len(current_id.encode()) > 256:
            return None
        seen.add(current_id)
        if user.collection('deleted_conversations').document(current_id).get().exists:
            return None
        document = user.collection('conversations').document(current_id).get()
        row = document.to_dict()
        if not row or row.get('owner_uid', uid) != uid or row.get('id', current_id) != current_id:
            return None
        if not row.get('deleted'):
            return SyncConversationSnapshot(current_id, document)
        successor = row.get('sync_merged_into')
        if not isinstance(successor, str) or not successor:
            return None
        current_id = successor
    return None
