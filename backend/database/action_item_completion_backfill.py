"""Bounded, resumable normalization of missing/null task completion fields.

No serving read writes data. The operator runs one explicit user's page at a
time. Snapshot preconditions preserve concurrent edits. The existing cheap
aggregation probe remains authoritative, so a late legacy restore cannot make
an old migration marker suppress tasks. No permanent marker is trusted.
"""

from typing import Any

from google.api_core.exceptions import FailedPrecondition, NotFound

from database._client import get_firestore_client
from database.action_item_codec import prepare_action_item_for_read
from database.action_items_cache import bump_action_items_list_version


def backfill_completion_page(
    uid: str, *, apply: bool = False, cursor: str | None = None, limit: int = 400, firestore_client: Any = None
) -> dict:
    if not uid or '/' in uid or (cursor is not None and '/' in cursor) or not 1 <= limit <= 400:
        raise ValueError('A user, document cursor and page limit 1..400 are required')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection('action_items')
    query = collection.select(['completed', 'status']).order_by('__name__')
    if cursor:
        query = query.start_after({'__name__': collection.document(cursor)})
    docs = list(query.limit(limit + 1).stream())
    page = docs[:limit]
    legacy = updated = conflicts = 0
    try:
        for doc in page:
            raw = doc.to_dict() or {}
            if raw.get('completed') is not None:
                continue
            legacy += 1
            if apply:
                completed = prepare_action_item_for_read(dict(raw))['completed']
                try:
                    doc.reference.update(
                        {'completed': completed}, option=client.write_option(last_update_time=doc.update_time)
                    )
                    updated += 1
                except (FailedPrecondition, NotFound):
                    conflicts += 1
    finally:
        # SDK commit fencing also invalidates Developer pages. Retain the
        # first-party list's independent invalidation, including partial errors.
        if updated:
            bump_action_items_list_version(uid)
    return {
        'scanned': len(page),
        'legacy': legacy,
        'updated': updated,
        'conflicts': conflicts,
        'has_more': len(docs) > limit,
        'next_cursor': page[-1].id if len(docs) > limit else None,
    }
