"""Advice — proactive coaching items.

Collection: users/{uid}/advice
"""

import logging
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.read_boundary import parse_snapshot_or_none, parse_snapshots
from google.api_core.exceptions import NotFound
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from models.advice import Advice

from ._client import db

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500  # Firestore hard limit


def _user_col(uid: str, collection: str) -> Any:
    """Shorthand for users/{uid}/{collection}."""
    return db.collection('users').document(uid).collection(collection)


# Raw documents read per stream() page while filling a get_advice request. The
# floor keeps tiny requests from paying one round trip per couple of rows.
RAW_ADVICE_STREAM_PAGE = 100


def _advice_payload(snapshot: Any) -> Mapping[str, Any]:
    """Snapshot payload with the Firestore document id made authoritative.

    A legacy or corrupted stored ``id`` must never reach the response: clients
    address advice by that id on PATCH/DELETE, so a mismatched stored id would
    make the next write hit a different document. The shared boundary's
    ``document_id_field`` only fills a missing field (``setdefault``), so it
    cannot repair a corrupt stored value — overwrite here instead.
    """
    payload = snapshot.to_dict()
    if not isinstance(payload, Mapping):
        raise TypeError('Firestore snapshot payload must be a mapping')
    parsed = dict(payload)
    parsed['id'] = snapshot.id
    return parsed


def create_advice(uid: str, content: str, category: str = 'other', **kwargs: Any) -> Dict[str, Any]:
    advice_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        'id': advice_id,
        'content': content,
        'category': category,
        'reasoning': kwargs.get('reasoning'),
        'source_app': kwargs.get('source_app'),
        'confidence': kwargs.get('confidence', 0.5),
        'context_summary': kwargs.get('context_summary'),
        'current_activity': kwargs.get('current_activity'),
        'created_at': now,
        'updated_at': now,
        'is_read': False,
        'is_dismissed': False,
    }
    _user_col(uid, 'advice').document(advice_id).set(doc)
    return doc


def get_advice(
    uid: str, category: Optional[str] = None, limit: int = 50, offset: int = 0, include_dismissed: bool = False
) -> List[Advice]:
    query = _user_col(uid, 'advice').order_by('created_at', direction=firestore.Query.DESCENDING)
    if category:
        query = query.where(filter=FieldFilter('category', '==', category))
    if not include_dismissed:
        query = query.where(filter=FieldFilter('is_dismissed', '==', False))

    # One malformed/legacy stored advice row must not 500 the whole advice feed:
    # Advice requires content/category/created_at/updated_at, so raw dicts straight
    # from Firestore made FastAPI raise ResponseValidationError (HTTP 500) for the
    # entire list. Rows are parsed through the shared read boundary and malformed
    # ones dropped.
    #
    # offset/limit must describe VALID rows, not raw documents: Firestore applies
    # its own offset/limit before the parser sees anything, so a page holding
    # malformed rows would come back short (or empty) and hide later valid advice.
    # Stream raw pages behind a start_after cursor and fill the request from valid
    # rows instead: skip the first `offset` valid rows, return up to `limit` valid
    # rows, stop when the stream is exhausted.
    page_size = max(limit, RAW_ADVICE_STREAM_PAGE)
    collected: List[Advice] = []
    skipped = 0
    cursor: Any = None
    while len(collected) < limit:
        page_query = query if cursor is None else query.start_after(cursor)
        snapshots = list(page_query.limit(page_size).stream())
        if not snapshots or (cursor is not None and snapshots[0] is cursor):
            # Empty page, or a stream that cannot advance past the cursor
            # (defensive: a replayed cursor must not spin; real start_after
            # never returns the cursor document itself).
            break
        cursor = snapshots[-1]
        for row in parse_snapshots(Advice, snapshots, payload_from_snapshot=_advice_payload):
            if skipped < offset:
                skipped += 1
                continue
            collected.append(row)
            if len(collected) >= limit:
                break
    return collected


def update_advice(
    uid: str, advice_id: str, is_read: Optional[bool] = None, is_dismissed: Optional[bool] = None
) -> Optional[Advice]:
    ref = _user_col(uid, 'advice').document(advice_id)
    snap = ref.get()
    if not getattr(snap, "exists", False):
        return None
    updates: Dict[str, Any] = {'updated_at': datetime.now(timezone.utc)}
    if is_read is not None:
        updates['is_read'] = is_read
    if is_dismissed is not None:
        updates['is_dismissed'] = is_dismissed
    try:
        ref.update(updates)
    except NotFound:
        # The advice was deleted between the existence check and the update.
        return None
    snapshot = ref.get()
    if not getattr(snapshot, "exists", False):
        # The advice was deleted between the update and the re-read.
        return None
    # Same read-boundary contract as get_advice: a poisoned row surfaces as
    # "not found" instead of a 500 from the PATCH response serializer, and the
    # document id stays authoritative for the same PATCH/DELETE addressing reason.
    return parse_snapshot_or_none(Advice, snapshot, payload_from_snapshot=_advice_payload)


def delete_advice(uid: str, advice_id: str) -> bool:
    ref = _user_col(uid, 'advice').document(advice_id)
    if not getattr(ref.get(), "exists", False):
        return False
    ref.delete()
    return True


def mark_all_advice_read(uid: str) -> int:
    col = _user_col(uid, 'advice')
    query = col.where(filter=FieldFilter('is_read', '==', False))
    batch = db.batch()
    total = 0
    batch_count = 0
    for doc in query.stream():
        batch.update(col.document(doc.id), {'is_read': True, 'updated_at': datetime.now(timezone.utc)})
        total += 1
        batch_count += 1
        if batch_count >= BATCH_LIMIT:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
        batch.commit()
    return total
