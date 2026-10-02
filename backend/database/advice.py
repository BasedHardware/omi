"""Advice — proactive coaching items.

Collection: users/{uid}/advice
"""

import logging
import uuid
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
    col = _user_col(uid, 'advice')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)
    if category:
        query = query.where(filter=FieldFilter('category', '==', category))
    if not include_dismissed:
        query = query.where(filter=FieldFilter('is_dismissed', '==', False))
    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)

    # One malformed/legacy stored advice row must not 500 the whole advice feed:
    # Advice requires content/category/created_at/updated_at, so raw dicts straight
    # from Firestore made FastAPI raise ResponseValidationError (HTTP 500) for the
    # entire list. Parse through the shared read boundary and drop malformed rows.
    return parse_snapshots(Advice, query.stream(), document_id_field='id')


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
    # "not found" instead of a 500 from the PATCH response serializer.
    return parse_snapshot_or_none(Advice, snapshot, document_id_field='id')


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
