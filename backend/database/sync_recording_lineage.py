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


MAX_LINEAGE_LIMIT = 500


def _collection(uid: str, firestore_client: Any) -> Any:
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return client.collection('users').document(uid.strip()).collection(CONVERSATIONS_COLLECTION)


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
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    if not isinstance(origin_id, str) or not origin_id.strip():
        raise ValueError('origin_id must be a non-empty string')
    if not isinstance(started_before, datetime):
        raise ValueError('started_before must be a datetime')
    if not isinstance(finished_after, datetime):
        raise ValueError('finished_after must be a datetime')
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError('limit must be a positive integer')

    clamped_limit = min(limit, MAX_LINEAGE_LIMIT)
    uid = uid.strip()
    origin_id = origin_id.strip()

    query = SYNC_RECORDING_LINEAGE_QUERY.build(
        _collection(uid, firestore_client),
        {'recording_origin_id': origin_id, 'started_before': started_before, 'finished_after': finished_after},
        field_filter_factory=FieldFilter,
    )
    query = (
        query.order_by('started_at', direction=firestore.Query.DESCENDING)
        .order_by('finished_at', direction=firestore.Query.DESCENDING)
        .select(list(LINEAGE_FIELD_PATHS))
        .limit(clamped_limit + 1)
    )
    return _rows(query)


def get_origin_generation(
    uid: str, origin_id: str, *, limit: int, firestore_client: Any = None
) -> list[dict[str, Any]]:
    """Rows bound to the origin recording id itself, for generations created before the origin stamp."""
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    if not isinstance(origin_id, str) or not origin_id.strip():
        raise ValueError('origin_id must be a non-empty string')
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError('limit must be a positive integer')

    clamped_limit = min(limit, MAX_LINEAGE_LIMIT)
    uid = uid.strip()
    origin_id = origin_id.strip()

    query = (
        _collection(uid, firestore_client)
        .where(filter=FieldFilter('external_data.recording_session_id', '==', origin_id))
        .select(list(LINEAGE_FIELD_PATHS))
        .limit(clamped_limit + 1)
    )
    return _rows(query)
