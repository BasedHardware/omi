"""Indexed summary-debt phases; cursors never need a document read."""

from typing import Any, Literal
from google.cloud import firestore
from database._client import get_firestore_client
from config.summary_guarantee import REPAIR_NEAR_EXPIRY_SECONDS, REPAIR_QUERY_PAGE_LIMIT
from utils.enrichment.age_gate import max_age_seconds, timestamp

Phase = Literal['near_expiry', 'newest']


def due_conversations(
    *,
    now: float,
    phase: Phase = 'newest',
    limit: int = 100,
    after: dict[str, Any] | None = None,
    firestore_client: Any = None,
) -> list[Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    window = max_age_seconds()
    if phase == 'near_expiry' and not window:
        return []
    cutoff = now - window
    boundary = cutoff + REPAIR_NEAR_EXPIRY_SECONDS
    query = client.collection_group('conversations').where(filter=firestore.FieldFilter('summary_due_at', '<=', now))
    if window:
        # Equality at the expiry cutoff is still eligible. Retained due
        # timestamps need not track pending timestamps; bound on the gate field.
        query = query.where(filter=firestore.FieldFilter('summary_first_pending_at', '>=', cutoff))
        query = query.where(
            filter=firestore.FieldFilter('summary_first_pending_at', '<=' if phase == 'near_expiry' else '>', boundary)
        )
    direction = firestore.Query.ASCENDING if phase == 'near_expiry' else firestore.Query.DESCENDING
    query = (
        query.order_by('summary_first_pending_at', direction=direction).order_by('summary_due_at').order_by('__name__')
    )
    if after and after.get('phase') == phase and after.get('window') == window and after.get('path'):
        pending, due = timestamp(after.get('pending')), timestamp(after.get('due'))
        in_band = pending is not None and (
            not window or (cutoff <= pending <= boundary if phase == 'near_expiry' else pending > boundary)
        )
        if in_band and due is not None:
            query = query.start_after(
                {
                    'summary_first_pending_at': pending,
                    'summary_due_at': due,
                    '__name__': client.document(after['path']),
                }
            )
        # Legacy, expired, wrong-phase and age-gate mode changes rewind safely.
    return list(query.limit(max(1, min(REPAIR_QUERY_PAGE_LIMIT, limit))).stream())
