"""Indexed first-week close-out page (SCA-4790).

One sparse collection-group query: an uncounted first-week conversation whose
stored window has ended, oldest window first. The sparse composite index exists
only for documents that carry the stamp, so the page never scans unrelated
conversations.
"""

import math
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
    *,
    now: float,
    until: float,
    limit: int = PAGE_LIMIT,
    after: dict[str, Any] | None = None,
    firestore_client: Any = None,
) -> list[Any]:
    """An uncounted first-week conversation whose window closes inside the reserve.

    Same sparse composite index as the close-out page: ``first_week_outcome``
    equality then the stored window end as a bounded range. It never scans an
    unstamped conversation and never reads a conversation body.

    ``after`` is the keyset cursor the forced phase carries across ticks
    (``{'window_end': <float>, 'path': 'users/<uid>/conversations/<id>'}``).
    Ordering is ``window_end_at`` then document name, so a page never repeats or
    skips a row that shares a window end, and the caller can walk the whole
    reserve instead of pinning the earliest 25 rows forever.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection_group('conversations')
        .where(filter=FieldFilter(OUTCOME_FIELD, '==', None))
        .where(filter=FieldFilter(WINDOW_END_PATH, '>', now))
        .where(filter=FieldFilter(WINDOW_END_PATH, '<=', until))
        .order_by(WINDOW_END_PATH)
        .order_by('__name__')
        .select([WINDOW_END_PATH])
        .limit(max(1, min(PAGE_LIMIT, limit)))
    )
    cursor = _keyset_cursor(after)
    if cursor is not None:
        query = query.start_after({WINDOW_END_PATH: cursor[0], '__name__': client.document(cursor[1])})
    return list(query.stream(timeout=20, retry=None))


def _keyset_cursor(after: Any) -> tuple[float, str] | None:
    """A usable ``(window_end_at, document path)`` bookmark, or None."""
    if not isinstance(after, dict):
        return None
    end, path = after.get('window_end'), after.get('path')
    if isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end):
        return None
    if not isinstance(path, str):
        return None
    parts = path.split('/')
    if len(parts) != 4 or parts[0] != 'users' or parts[2] != 'conversations' or not parts[1] or not parts[3]:
        return None
    return float(end), path
