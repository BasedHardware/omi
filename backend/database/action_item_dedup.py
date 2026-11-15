"""Read-only, bounded proof that conversation task dedup has no candidates."""

from datetime import datetime
from typing import Any

from database._client import get_firestore_client
from database.action_item_codec import prepare_action_item_for_read
from database.firestore_retry import FIRESTORE_NO_RETRY


def may_have_recent_dedup_candidates(
    uid: str,
    cutoff: datetime,
    excluded_conversation_ids: set[str],
    *,
    firestore_client: Any = None,
) -> bool:
    """Prove an empty dedup pool with at most 16 projected document reads.

    Use the existing single-field timestamp indexes, not completed=False:
    legacy rows can omit completed and updated_at. An ordered cursor (rather
    than a type-restricted inequality filter) also includes strings, which
    Firestore sorts after timestamps. Legacy ISO dates pass through the same
    read codec as get_action_items_by_ids.

    A full page is inconclusive: keep Pinecone rather than scan more rows or
    incorrectly hide an eligible item beyond the page. No shared cache or
    writes are involved; exclusions belong to this processing invocation.
    """
    client = firestore_client or get_firestore_client()
    collection = client.collection('users').document(uid).collection('action_items')
    fields = ['completed', 'status', 'conversation_id', 'updated_at', 'created_at']
    for timestamp_field in ('updated_at', 'created_at'):
        query = collection.order_by(timestamp_field).start_at({timestamp_field: cutoff}).select(fields).limit(8)
        docs = list(query.stream(timeout=2, retry=FIRESTORE_NO_RETRY))
        if len(docs) == 8:
            return True
        for doc in docs:
            item = prepare_action_item_for_read(doc.to_dict() or {})
            if item.get('completed', False) or item.get('conversation_id') in excluded_conversation_ids:
                continue
            last_active = item.get('updated_at') or item.get('created_at')
            if last_active is not None and last_active >= cutoff:
                return True
    return False
