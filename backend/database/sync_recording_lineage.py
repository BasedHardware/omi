"""Metadata-only reads of one live recording's rollover generations for sync binding.

Every live generation created while ``SYNC_LINEAGE_RESOLVE_ENABLED`` is on carries
``external_data.recording_origin_id`` (the client recording id the phone also
puts on its WALs). Both reads project routing metadata only: transcript text,
photos and speaker data are never fetched.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import get_firestore_client
from .firestore_index_registry import SYNC_RECORDING_LINEAGE_QUERY
from .firestore_read_metrics import FirestoreReadFamily, FirestoreReadMode, record_firestore_read

CONVERSATIONS_COLLECTION = 'conversations'

LINEAGE_FIELD_PATHS = (
    'started_at',
    'finished_at',
    'source',
    'client_device_id',
    'is_locked',
    'deleted',
    'sync_merged_into',
    'smart_merge.role',
    'external_data.recording_session_id',
    'external_data.recording_origin_id',
)


def _collection(uid: str, firestore_client: Any) -> Any:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION)


def _rows(query: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for doc in query.stream():
        data = doc.to_dict()
        if isinstance(data, dict):
            data['id'] = doc.id
            rows.append(data)
    record_firestore_read(FirestoreReadFamily.SYNC_RECORDING_LINEAGE, FirestoreReadMode.BOUNDED, len(rows))
    return rows


def get_recording_generations(
    uid: str,
    origin_id: str,
    *,
    started_before: datetime,
    finished_after: datetime,
    limit: int,
    firestore_client: Any = None,
) -> list[dict[str, Any]]:
    """Newest-first generations that can overlap the upload's segment envelope.

    Reads at most ``limit + 1`` documents so the caller can tell a complete
    window from a truncated one.
    """
    query = SYNC_RECORDING_LINEAGE_QUERY.build(
        _collection(uid, firestore_client),
        {'recording_origin_id': origin_id, 'started_before': started_before, 'finished_after': finished_after},
        field_filter_factory=FieldFilter,
    )
    query = (
        query.order_by('started_at', direction=firestore.Query.DESCENDING)
        .order_by('finished_at', direction=firestore.Query.DESCENDING)
        .select(list(LINEAGE_FIELD_PATHS))
        .limit(limit + 1)
    )
    return _rows(query)


def get_origin_generation(
    uid: str, origin_id: str, *, limit: int, firestore_client: Any = None
) -> list[dict[str, Any]]:
    """Rows bound to the origin recording id itself, for generations created before the origin stamp."""
    query = (
        _collection(uid, firestore_client)
        .where(filter=FieldFilter('external_data.recording_session_id', '==', origin_id))
        .select(list(LINEAGE_FIELD_PATHS))
        .limit(limit + 1)
    )
    return _rows(query)
