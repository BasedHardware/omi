"""Firestore scan helpers for action-item cleanup preview.

Split out of database/action_items.py because that module is already at the
repo product-file line-count ratchet (THRESHOLD 1500) and may not grow further
without a declared exception. Cleanup preview needs oldest-first pagination,
open-count aggregation, and scan-cap disclosure — one cohesive block to extract.
"""

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database.firestore_index_registry import ACTION_ITEMS_CLEANUP_OPEN_CREATED_SCAN_QUERY
from database import action_items as action_items_db

logger = logging.getLogger(__name__)


def get_action_items_list_scan_cap() -> int:
    """Public accessor for the action-items list hard max."""
    return action_items_db.get_action_items_list_hard_max()


def get_open_action_items_count(uid: str) -> int:
    """Return the true count of open (incomplete) action items for a user.

    Uses Firestore count() aggregation — no document reads, no list hard-max cap —
    so callers (e.g. cleanup preview) can tell whether a bounded scan left tasks
    out of what it actually read.
    """
    base = action_items_db.db.collection('users').document(uid).collection(action_items_db.action_items_collection)
    total = int(base.count().get()[0][0].value)
    completed = int(base.where(filter=FieldFilter('completed', '==', True)).count().get()[0][0].value)

    deleted_total = 0
    deleted_completed = 0
    for doc in base.where(filter=FieldFilter('deleted', '==', True)).stream():
        deleted_total += 1
        if (doc.to_dict() or {}).get('completed'):
            deleted_completed += 1

    total = max(0, total - deleted_total)
    completed = max(0, min(completed - deleted_completed, total))
    return max(0, total - completed)


def _parse_cleanup_scan_created_at(value: Any) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.rstrip('Z')).replace(tzinfo=timezone.utc)
    if hasattr(value, 'timestamp'):
        return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def encode_cleanup_scan_cursor(created_at: datetime, doc_id: str) -> str:
    """Encode the last scanned open task for deterministic cleanup pagination."""
    normalized = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    payload = {'created_at': normalized.astimezone(timezone.utc).isoformat(), 'id': doc_id}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode()


def decode_cleanup_scan_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return _parse_cleanup_scan_created_at(payload['created_at']), str(payload['id'])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid cleanup scan cursor') from exc


def list_open_action_items_for_cleanup(
    uid: str,
    *,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], Optional[str], int]:
    """Return one oldest-first page of open action items for cleanup strategies."""
    hard_max = action_items_db.get_action_items_list_hard_max()
    row_cap = min(limit or hard_max, hard_max)
    coll = action_items_db.db.collection('users').document(uid).collection(action_items_db.action_items_collection)
    query = ACTION_ITEMS_CLEANUP_OPEN_CREATED_SCAN_QUERY.build(
        coll.select(list(action_items_db.get_action_items_list_select_fields())),
        {'completed': False},
        field_filter_factory=FieldFilter,
    ).order_by('created_at', direction=firestore.Query.ASCENDING)

    if cursor:
        created_at, doc_id = decode_cleanup_scan_cursor(cursor)
        query = query.start_after({'created_at': created_at, '__name__': coll.document(doc_id)})

    items, docs_read = action_items_db.stream_action_items_bounded(
        query,
        max_docs=action_items_db.list_scan_budget(row_cap),
    )
    items.sort(key=lambda item: (_parse_cleanup_scan_created_at(item.get('created_at')), item['id']))
    page_items = items[:row_cap]
    next_cursor = None
    if page_items and (len(items) > row_cap or docs_read >= action_items_db.list_scan_budget(row_cap)):
        last = page_items[-1]
        next_cursor = encode_cleanup_scan_cursor(_parse_cleanup_scan_created_at(last.get('created_at')), last['id'])
    logger.debug(
        'list_open_action_items_for_cleanup uid=%s page=%s docs_read=%s has_next=%s',
        uid,
        len(page_items),
        docs_read,
        bool(next_cursor),
    )
    return page_items, next_cursor, len(page_items)
