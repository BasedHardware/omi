"""Indexed newest-first page of closed episodes for scheduled compose recovery."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.cloud import firestore

from config.episodes import COMPOSER_SWEEP_SCAN_LIMIT
from database._client import get_firestore_client
from database.firestore_query_types import FirestoreIndexField, FirestoreQueryFilter, FirestoreQuerySpec

EPISODE_COMPOSE_SWEEP_QUERY = FirestoreQuerySpec(
    identifier='episodes_compose_sweep_newest',
    collection_group='episodes',
    query_scope='COLLECTION_GROUP',
    filters=(FirestoreQueryFilter('status', '==', 'status'),),
    index_fields=(
        FirestoreIndexField('status', order='ASCENDING'),
        FirestoreIndexField('closed_at', order='DESCENDING'),
        FirestoreIndexField('__name__', order='DESCENDING'),
    ),
)


def closed_episodes_for_compose_sweep(
    *, limit: int = COMPOSER_SWEEP_SCAN_LIMIT, after: dict[str, Any] | None = None, firestore_client: Any = None
) -> list[Any]:
    """Return one bounded page; a stored path and timestamp form the keyset cursor."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = EPISODE_COMPOSE_SWEEP_QUERY.build(
        client.collection_group('episodes'), {'status': 'closed'}, field_filter_factory=firestore.FieldFilter
    )
    query = query.order_by('closed_at', direction=firestore.Query.DESCENDING).order_by(
        '__name__', direction=firestore.Query.DESCENDING
    )
    if after and after.get('path') and isinstance(after.get('closed_at'), datetime):
        query = query.start_after({'closed_at': after['closed_at'], '__name__': client.document(after['path'])})
    return list(query.limit(max(1, min(COMPOSER_SWEEP_SCAN_LIMIT, limit))).stream())
