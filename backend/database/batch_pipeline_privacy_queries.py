"""Single-field, bounded query builders for batch privacy and retention."""

from typing import Any
from google.cloud.firestore_v1 import FieldFilter


def owner_documents(client: Any, namespace: str, table: str, key: str, *, after: Any = None) -> list:
    query = client.collection(f'{namespace}_{table}').where(filter=FieldFilter('owner_key', '==', key))
    if after is not None:
        query = query.start_after(after)
    return list(query.limit(100).stream())


def artifacts_by_owner_id(client: Any, namespace: str, uid: str, *, after: Any = None) -> list:
    """Privacy fallback for receipts whose denormalized owner key is corrupt."""
    query = client.collection(f'{namespace}_artifacts').where(filter=FieldFilter('owner_id', '==', uid))
    if after is not None:
        query = query.start_after(after)
    return list(query.limit(100).stream())


def predecessor_documents(client: Any, namespace: str, segment_id: str, transaction: Any) -> list:
    # Popped jobs retain old next pointers, so only ready jobs can be predecessors.
    return list(
        client.collection(f'{namespace}_jobs')
        .where(filter=FieldFilter('next', '==', segment_id))
        .where(filter=FieldFilter('state', '==', 'ready'))
        .limit(1)
        .stream(transaction=transaction)
    )


def segment_artifacts(client: Any, namespace: str, segment_id: str, transaction: Any) -> list:
    return list(
        client.collection(f'{namespace}_artifacts')
        .where(filter=FieldFilter('segment_id', '==', segment_id))
        .limit(256)
        .stream(transaction=transaction)
    )


def due_artifacts(client: Any, namespace: str, now: Any, limit: int = 100) -> list:
    return list(
        client.collection(f'{namespace}_artifacts')
        .where(filter=FieldFilter('cleanup_after', '<=', now))
        .limit(max(1, min(100, limit)))
        .stream()
    )
