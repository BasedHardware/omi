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
) -> List[Dict[str, Any]]:
    col = _user_col(uid, 'advice')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)
    if category:
        query = query.where(filter=FieldFilter('category', '==', category))
    if not include_dismissed:
        query = query.where(filter=FieldFilter('is_dismissed', '==', False))
    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)

    items: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        items.append(data)
    return items


def _update_advice_and_return(uid: str, advice_id: str, updates: dict) -> Optional[dict]:
    """Apply `updates` to an advice doc and return the fresh value, or None if it does not exist
    (or was deleted mid-update). Shared by update_advice and set_advice_feedback so both get the
    same existence check, NotFound guard, and None-on-re-read handling."""
    ref = _user_col(uid, 'advice').document(advice_id)
    snap = ref.get()
    if not getattr(snap, "exists", False):
        return None
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
    result['id'] = advice_id
    return result


def update_advice(uid: str, advice_id: str, is_read: bool = None, is_dismissed: bool = None) -> Optional[dict]:
    updates = {'updated_at': datetime.now(timezone.utc)}
    if is_read is not None:
        updates['is_read'] = is_read
    if is_dismissed is not None:
        updates['is_dismissed'] = is_dismissed
    return _update_advice_and_return(uid, advice_id, updates)


def set_advice_feedback(uid: str, advice_id: str, rating: int, reason: Optional[str] = None) -> Optional[dict]:
    """Record the user's feedback on an advice item.

    rating is 1 (helpful), -1 (not helpful), or 0 (clear any existing feedback). Returns the updated
    advice dict, or None if the advice does not exist (or was deleted mid-update).
    """
    now = datetime.now(timezone.utc)
    feedback = None if rating == 0 else {'rating': rating, 'reason': reason, 'rated_at': now}
    return _update_advice_and_return(uid, advice_id, {'feedback': feedback, 'updated_at': now})


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
