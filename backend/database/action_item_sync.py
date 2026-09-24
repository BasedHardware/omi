"""Incremental action-item feed ordered ``(updated_at ASC, __name__ ASC)``.

Kept out of ``database/action_items.py`` (line-count ratchet). Serves the
REST ``GET /v1/mcp/action-items?updated_since=`` sync feed and the matching
MCP tool path: a stable ascending keyset over persisted ``updated_at`` so a
client can pull only changes since its last watermark.

Deletes: action-item deletes are hard by default — a hard-deleted row leaves
no trace and is NOT emitted. Rows that do persist with ``deleted: true``
(soft tombstones written by retirement flows) are included so the client can
reconcile them; every emitted item carries its ``updated_at`` watermark.
"""

from typing import Any, Dict, List, Optional, Tuple

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import get_firestore_client
from .action_items import (
    ACTION_ITEMS_LIST_SELECT_FIELDS,
    prepare_action_item_for_read,
    typed_doc,
    action_items_collection,
)


def get_action_items_sync_page(
    uid: str,
    *,
    updated_since: Any = None,
    after: Optional[Tuple[Any, str]] = None,
    limit: int,
    firestore_client: Any = None,
) -> Tuple[List[Dict[str, Any]], Optional[Tuple[Any, str]]]:
    """Return one ``(updated_at ASC, __name__ ASC)`` page of action items.

    ``updated_since`` bounds the feed to rows updated on/after that instant;
    ``after`` is the ``(updated_at, doc id)`` resume position from the prior
    page. Fetches ``limit + 1`` so a resume position is only emitted when
    another row actually exists — it is the last emitted row's position, so
    the lookahead row is re-fetched rather than skipped. Documents missing
    ``updated_at`` cannot appear (the ordering field is absent), which is the
    intended contract: they predate the sync surface.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(action_items_collection)
    query = (
        collection.where(filter=FieldFilter('updated_at', '>=', updated_since))
        if updated_since is not None
        else collection
    )
    query = query.order_by('updated_at', direction=firestore.Query.ASCENDING).order_by(
        '__name__', direction=firestore.Query.ASCENDING
    )
    if after is not None:
        after_dt, after_id = after
        if after_dt is None:
            raise ValueError('action item sync timestamp is invalid')
        if not after_id.strip() or '/' in after_id:
            raise ValueError('action item sync doc id is invalid')
        query = query.start_after({'updated_at': after_dt, '__name__': collection.document(after_id)})
    query = query.select(list(ACTION_ITEMS_LIST_SELECT_FIELDS)).limit(limit + 1)

    docs = list(query.stream())
    page_docs = docs[:limit]
    items: List[Dict[str, Any]] = []
    last_position: Optional[Tuple[Any, str]] = None
    for doc in page_docs:
        data = typed_doc(doc)
        # The resume value must be the raw stored timestamp: the read prep
        # normalizes it to a plain datetime and could round the keyset edge.
        raw_updated_at = data.get('updated_at')
        data['id'] = doc.id
        items.append(prepare_action_item_for_read(data))
        last_position = (raw_updated_at, doc.id)
    resume = last_position if len(docs) > limit else None
    return items, resume
