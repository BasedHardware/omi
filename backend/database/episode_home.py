"""Paginated Home reads. No episode lifecycle writes; one automatic started_at index."""

from datetime import datetime, timedelta
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.episodes import MAX_EPISODE_SECONDS
from database._client import get_firestore_client
from database import episodes


def list_episode_window(
    uid: str,
    start: datetime,
    end: datetime,
    *,
    limit: int = 50,
    cursor: str | None = None,
    firestore_client: Any = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Page the recorded window, including starts before it (episodes have a 4h span cap).

    Pagination advances over scanned documents, even when overlap/visibility filtering
    leaves an empty page. The document snapshot cursor preserves equal-start ordering.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection('episodes')
    query = (
        collection.where(filter=FieldFilter('started_at', '>=', start - timedelta(seconds=MAX_EPISODE_SECONDS)))
        .where(filter=FieldFilter('started_at', '<=', end))
        .order_by('started_at', direction=firestore.Query.DESCENDING)
        .limit(limit + 1)
    )
    if cursor:
        snapshot = collection.document(cursor).get()
        if not snapshot.exists:
            raise ValueError('Episode cursor no longer exists')
        query = query.start_after(snapshot)
    documents = list(query.stream())
    page = documents[:limit]
    rows = []
    for document in page:
        row = episodes.unseal(uid, document.to_dict())
        if row and (row.get('last_activity_at') or row['started_at']) >= start:
            rows.append({**row, 'id': document.id})
    return rows, page[-1].id if len(documents) > limit else None
