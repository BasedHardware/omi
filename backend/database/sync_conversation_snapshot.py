"""Detached, operation-local redirect snapshot; never a mutation authority."""

from dataclasses import dataclass
from typing import Any, Callable

from config import sync_operation_snapshot
from database.conversation_revisions import firestore_revision_datetime
from database.sync_snapshot_resolve_cache import memoize_resolve


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


@memoize_resolve
def resolve_snapshot(
    uid: str, conversation_id: str, *, client_factory: Callable[[], Any], max_hops: int = 16
) -> SyncConversationSnapshot | None:
    """Check every deletion marker and owner/path before returning the survivor.

    A new sync-job invocation always reads fresh documents. With the read
    lever enabled, discovery results may repeat within that job only. Mutation
    transactions and later deliveries must still establish fresh authority.
    """
    user = None
    seen: set[str] = set()
    current_id = conversation_id
    for _ in range(max_hops):
        if current_id in seen or not current_id or '/' in current_id or len(current_id.encode()) > 256:
            return None
        seen.add(current_id)
        if user is None:
            user = client_factory().collection('users').document(uid)
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


def read_redirected(
    uid: str,
    conversation_id: str,
    *,
    client_factory: Callable[[], Any],
    hydrate: Callable[..., dict | None],
    read_current: Callable[..., dict | None],
    read_site: Any,
) -> dict | None:
    """Hydrate one resolved owner read, retaining the path id for legacy rows."""
    client = None

    def operation_client():
        nonlocal client
        if client is None:
            client = client_factory()
        return client

    resolved = resolve_snapshot(uid, conversation_id, client_factory=operation_client)
    if resolved is None:
        return None
    if sync_operation_snapshot.enabled():
        sync_operation_snapshot.avoided('redirect_hydration')
        data = hydrate(uid, resolved.to_dict(), firestore_client=operation_client(), read_site=read_site)
    else:
        data = read_current(uid, resolved.conversation_id, firestore_client=operation_client(), read_site=read_site)
    if data is not None:
        # Add the path id only AFTER ordinary photo/codec hydration, preserving
        # legacy photo behavior while allowing internal reprocessing to route.
        data.setdefault('id', resolved.conversation_id)
    return data
