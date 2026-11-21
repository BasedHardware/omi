"""Conversation deletions in ``(deleted_at ASC, __name__ ASC)`` order, for agents that keep copies.

Every user deletion already writes a content-free tombstone to
``users/{uid}/deleted_conversations`` (``database.conversation_tombstones``) with
a real ``deleted_at``. Nothing read them by time, so an agent syncing Omi into
its own store could never learn what to drop. This is the same keyset contract
as the action-item feed (``database.action_item_sync``): ``limit + 1``
lookahead, resume at the last emitted row.

Only ``deleted_at`` is read; the id is the document name. Tombstones without a
timestamp ``deleted_at`` (absent or null) cannot be ordered and do not appear:
the range filter is always applied, and Firestore range filters match only
values of the filter's type.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import get_firestore_client
from .conversation_tombstones import COLLECTION

# Lower bound when no watermark is given; excludes explicit-null deleted_at rows.
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def get_deleted_conversations_page(
    uid: str,
    *,
    deleted_since: Any = None,
    after: Optional[Tuple[Any, Any]] = None,
    limit: int,
    firestore_client: Any = None,
) -> Tuple[List[Dict[str, Any]], Optional[Tuple[Any, str]]]:
    """Return ``([{id, deleted_at}], resume)``; ``resume`` is set only when another row exists."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(COLLECTION)
    lower = deleted_since if deleted_since is not None else _EPOCH
    query = (
        collection.where(filter=FieldFilter('deleted_at', '>=', lower))
        .order_by('deleted_at', direction=firestore.Query.ASCENDING)
        .order_by('__name__', direction=firestore.Query.ASCENDING)
    )
    if after is not None:
        after_dt, after_id = after
        if after_dt is None:
            raise ValueError('deletion feed timestamp is invalid')
        if not isinstance(after_id, str) or not after_id.strip() or '/' in after_id:
            raise ValueError('deletion feed doc id is invalid')
        query = query.start_after({'deleted_at': after_dt, '__name__': collection.document(after_id)})
    docs = list(query.select(['deleted_at']).limit(limit + 1).stream())
    rows: List[Dict[str, Any]] = []
    last: Optional[Tuple[Any, str]] = None
    for doc in docs[:limit]:
        deleted_at = (doc.to_dict() or {}).get('deleted_at')
        rows.append({'id': doc.id, 'deleted_at': deleted_at})
        last = (deleted_at, doc.id)
    return rows, last if len(docs) > limit else None
