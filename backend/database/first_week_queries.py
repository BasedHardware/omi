"""Indexed first-week close-out page (SCA-4790).

One sparse collection-group query: an uncounted first-week conversation whose
stored window has ended, oldest window first. The sparse composite index exists
only for documents that carry the stamp, so the page never scans unrelated
conversations.
"""

from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client

OUTCOME_FIELD = 'first_week_outcome'
WINDOW_END_PATH = 'first_week_summary.window_end_at'
PAGE_LIMIT = 100


def due_first_week_conversations(*, now: float, limit: int = PAGE_LIMIT, firestore_client: Any = None) -> list[Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection_group('conversations')
        .where(filter=FieldFilter(OUTCOME_FIELD, '==', None))
        .where(filter=FieldFilter(WINDOW_END_PATH, '<=', now))
        .order_by(WINDOW_END_PATH)
        .limit(max(1, min(PAGE_LIMIT, limit)))
    )
    return list(query.stream(timeout=20, retry=None))


def approaching_first_week_conversations(
    *, now: float, until: float, limit: int = PAGE_LIMIT, firestore_client: Any = None
) -> list[Any]:
    """An uncounted first-week conversation whose window closes inside the reserve.

    Same sparse composite index as the close-out page: ``first_week_outcome``
    equality then the stored window end as a bounded range. It never scans an
    unstamped conversation and never reads a conversation body.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection_group('conversations')
        .where(filter=FieldFilter(OUTCOME_FIELD, '==', None))
        .where(filter=FieldFilter(WINDOW_END_PATH, '>', now))
        .where(filter=FieldFilter(WINDOW_END_PATH, '<=', until))
        .order_by(WINDOW_END_PATH)
        .limit(max(1, min(PAGE_LIMIT, limit)))
    )
    return list(query.stream(timeout=20, retry=None))
