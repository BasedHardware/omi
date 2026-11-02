"""Indexed, bounded summary-debt window; cursor never needs a document read."""

from typing import Any
from google.cloud import firestore
from database._client import get_firestore_client


def due_conversations(
    *, now: float, limit: int = 100, after: dict[str, Any] | None = None, firestore_client: Any = None
) -> list[Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection_group('conversations')
        .where(filter=firestore.FieldFilter('summary_due_at', '<=', now))
        .order_by('summary_due_at')
        .order_by('__name__')
    )
    if after and after.get('path') and isinstance(after.get('due'), (float, int)):
        query = query.start_after({'summary_due_at': after['due'], '__name__': client.document(after['path'])})
    return list(query.limit(max(1, min(100, limit))).stream())
