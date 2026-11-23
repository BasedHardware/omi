"""Indexed summary-debt phases; cursors never need a document read."""

from typing import Any, Literal
import math
from google.cloud import firestore
from database._client import get_firestore_client
from config.summary_guarantee import REPAIR_NEAR_EXPIRY_SECONDS, REPAIR_QUERY_PAGE_LIMIT
from utils.enrichment.age_gate import max_age_seconds, timestamp

Phase = Literal['historical', 'near_expiry', 'newest']


def due_conversations(
    *,
    now: float,
    phase: Phase = 'newest',
    limit: int = 100,
    after: dict[str, Any] | None = None,
    firestore_client: Any = None,
    historical_before: float | None = None,
    timeout: float | None = None,
) -> list[Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    window = max_age_seconds()
    if phase != 'newest' and not window:
        return []
    cutoff = now - window
    boundary = cutoff + REPAIR_NEAR_EXPIRY_SECONDS
    phase_end = historical_before if phase == 'historical' else None
    if phase == 'historical' and (phase_end is None or phase_end <= boundary):
        return []
    query = client.collection_group('conversations').where(filter=firestore.FieldFilter('summary_due_at', '<=', now))
    if window:
        # Equality at the expiry cutoff is still eligible. Retained due
        # timestamps need not track pending timestamps; bound on the gate field.
        query = query.where(filter=firestore.FieldFilter('summary_first_pending_at', '>=', cutoff))
        query = query.where(
            filter=firestore.FieldFilter('summary_first_pending_at', '<=' if phase == 'near_expiry' else '>', boundary)
        )
        if phase_end is not None:
            query = query.where(filter=firestore.FieldFilter('summary_first_pending_at', '<', phase_end))
        direction = firestore.Query.DESCENDING if phase == 'newest' else firestore.Query.ASCENDING
        query = query.order_by('summary_first_pending_at', direction=direction)
    query = query.order_by('summary_due_at').order_by('__name__')
    if not window:
        # Preserve the legacy due-only order and cursor, including debt with
        # no pending timestamp. A pending-time cursor belongs to another order.
        if after and after.get('path') and isinstance(after.get('due'), (float, int)) and after.get('pending') is None:
            query = query.start_after({'summary_due_at': after['due'], '__name__': client.document(after['path'])})
    elif after and after.get('phase') == phase and after.get('window') == window and after.get('path'):
        pending = timestamp(after.get('pending'))
        due = after.get('due')
        if not isinstance(due, (int, float)) or isinstance(due, bool):
            due = timestamp(due)
        elif not math.isfinite(due):
            due = None
        in_band = (
            pending is not None
            and (phase_end is None or pending < phase_end)
            and (cutoff <= pending <= boundary if phase == 'near_expiry' else pending > boundary)
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
    query = query.limit(max(1, min(REPAIR_QUERY_PAGE_LIMIT, limit)))
    if timeout is not None:
        return list(query.stream(timeout=timeout, retry=None))
    return list(query.stream())
