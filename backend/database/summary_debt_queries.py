"""Indexed, bounded summary-debt window; cursor never needs a document read."""

from typing import Any
from google.cloud import firestore
from database._client import get_firestore_client
from utils.enrichment.age_gate import max_age_seconds, timestamp


def due_conversations(
    *, now: float, limit: int = 100, after: dict[str, Any] | None = None, firestore_client: Any = None
) -> list[Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = client.collection_group('conversations').where(filter=firestore.FieldFilter('summary_due_at', '<=', now))
    window = max_age_seconds()
    cutoff = now - window
    if window:
        # Bound on the gate's own field: retained due timestamps need not track
        # pending timestamps. Every admissible non-expired pending time is >=
        # cutoff (equality is still eligible). Missing pending cannot redrive.
        query = query.where(filter=firestore.FieldFilter('summary_first_pending_at', '>=', cutoff)).order_by(
            'summary_first_pending_at'
        )
    query = query.order_by('summary_due_at').order_by('__name__')
    if after and after.get('path') and isinstance(after.get('due'), (float, int)):
        cursor = {'summary_due_at': after['due'], '__name__': client.document(after['path'])}
        pending = timestamp(after.get('pending'))
        if window and pending is not None and pending >= cutoff:
            cursor['summary_first_pending_at'] = pending
            query = query.start_after(cursor)
        elif not window and after.get('pending') is None:
            query = query.start_after(cursor)
        # Skip expired/legacy cursors and reset on an age-gate mode change.
    return list(query.limit(max(1, min(100, limit))).stream())
