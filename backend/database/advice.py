"""Advice — proactive coaching items.

Collection: users/{uid}/advice
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from google.api_core.exceptions import NotFound
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import db

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500  # Firestore hard limit


def _user_col(uid: str, collection: str) -> Any:
    """Shorthand for users/{uid}/{collection}."""
    normalized_uid = str(uid or '').strip()
    if not normalized_uid:
        raise ValueError('uid must be a non-empty string')
    return db.collection('users').document(normalized_uid).collection(collection)


def create_advice(uid: str, content: str, category: str = 'other', **kwargs: Any) -> Dict[str, Any]:
    normalized_uid = str(uid or '').strip()
    if not normalized_uid:
        raise ValueError('uid must be a non-empty string')
    normalized_content = str(content or '').strip()
    if not normalized_content:
        raise ValueError('content must be a non-empty string')
    normalized_category = str(category or 'other').strip() or 'other'

    raw_confidence = kwargs.get('confidence', 0.5)
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    advice_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        'id': advice_id,
        'content': normalized_content,
        'category': normalized_category,
        'reasoning': kwargs.get('reasoning'),
        'source_app': kwargs.get('source_app'),
        'confidence': confidence,
        'context_summary': kwargs.get('context_summary'),
        'current_activity': kwargs.get('current_activity'),
        'created_at': now,
        'updated_at': now,
        'is_read': False,
        'is_dismissed': False,
    }
    _user_col(normalized_uid, 'advice').document(advice_id).set(doc)
    return doc


def get_advice(
    uid: str, category: Optional[str] = None, limit: int = 50, offset: int = 0, include_dismissed: bool = False
) -> List[Dict[str, Any]]:
    normalized_uid = str(uid or '').strip()
    if not normalized_uid:
        return []
    if limit is not None and limit <= 0:
        return []

    safe_limit = min(limit, 1000) if limit is not None else 50
    safe_offset = max(0, offset) if offset is not None else 0

    col = _user_col(normalized_uid, 'advice')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)
    if category and str(category).strip():
        query = query.where(filter=FieldFilter('category', '==', str(category).strip()))
    if not include_dismissed:
        query = query.where(filter=FieldFilter('is_dismissed', '==', False))
    if safe_offset > 0:
        query = query.offset(safe_offset)
    query = query.limit(safe_limit)

    items: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        items.append(data)
    return items


def update_advice(
    uid: str, advice_id: str, is_read: Optional[bool] = None, is_dismissed: Optional[bool] = None
) -> Optional[Dict[str, Any]]:
    normalized_uid = str(uid or '').strip()
    normalized_advice_id = str(advice_id or '').strip()
    if not normalized_uid or not normalized_advice_id:
        return None
    ref = _user_col(normalized_uid, 'advice').document(normalized_advice_id)
    snap = ref.get()
    if not getattr(snap, "exists", False):
        return None
    updates: Dict[str, Any] = {'updated_at': datetime.now(timezone.utc)}
    if is_read is not None:
        updates['is_read'] = bool(is_read)
    if is_dismissed is not None:
        updates['is_dismissed'] = bool(is_dismissed)
    try:
        ref.update(updates)
    except NotFound:
        # The advice was deleted between the existence check and the update.
        return None
    raw: object = ref.get().to_dict()
    if raw is None:
        # The advice was deleted between the update and the re-read.
        return None
    result: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    result['id'] = normalized_advice_id
    return result


def delete_advice(uid: str, advice_id: str) -> bool:
    normalized_uid = str(uid or '').strip()
    normalized_advice_id = str(advice_id or '').strip()
    if not normalized_uid or not normalized_advice_id:
        return False
    ref = _user_col(normalized_uid, 'advice').document(normalized_advice_id)
    if not getattr(ref.get(), "exists", False):
        return False
    ref.delete()
    return True


def mark_all_advice_read(uid: str) -> int:
    """Mark all unread advice items as read for a given user.

    Batches updates in chunks of BATCH_LIMIT (500) to adhere to Firestore limits.
    Note: Chunked commits break all-or-nothing multi-chunk atomicity if a failure
    occurs after the first chunk commits; previously committed chunks persist.
    """
    normalized_uid = str(uid or '').strip()
    if not normalized_uid:
        return 0
    col = _user_col(normalized_uid, 'advice')
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
