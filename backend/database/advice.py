import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from google.cloud import firestore

from ._client import db

logger = logging.getLogger(__name__)

USERS_COLLECTION = 'users'
ADVICE_SUBCOLLECTION = 'advice'


def _collection_ref(uid: str):
    return db.collection(USERS_COLLECTION).document(uid).collection(ADVICE_SUBCOLLECTION)


def create_advice(uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new advice document. Returns the created document with id."""
    advice_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    doc_data = {
        'content': data['content'],
        'category': data.get('category', 'other'),
        'confidence': data.get('confidence', 0.5),
        'is_read': False,
        'is_dismissed': False,
        'created_at': now,
    }
    for optional_field in ('reasoning', 'source_app', 'context_summary', 'current_activity'):
        if data.get(optional_field) is not None:
            doc_data[optional_field] = data[optional_field]

    _collection_ref(uid).document(advice_id).set(doc_data)

    doc_data['id'] = advice_id
    return doc_data


def get_advice(
    uid: str,
    limit: int = 100,
    offset: int = 0,
    category: Optional[str] = None,
    include_dismissed: bool = False,
) -> List[Dict[str, Any]]:
    """Query advice, ordered by created_at DESC."""
    query = _collection_ref(uid).order_by('created_at', direction=firestore.Query.DESCENDING)

    if not include_dismissed:
        query = query.where(filter=firestore.FieldFilter('is_dismissed', '==', False))
    if category:
        query = query.where(filter=firestore.FieldFilter('category', '==', category))

    query = query.offset(offset).limit(limit)

    results = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        results.append(data)
    return results


def update_advice(uid: str, advice_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an advice document (is_read, is_dismissed). Returns updated doc."""
    doc_ref = _collection_ref(uid).document(advice_id)

    update_data = {'updated_at': datetime.now(timezone.utc)}
    if 'is_read' in data:
        update_data['is_read'] = data['is_read']
    if 'is_dismissed' in data:
        update_data['is_dismissed'] = data['is_dismissed']

    try:
        doc_ref.update(update_data)
    except Exception as e:
        if hasattr(e, 'code') and e.code == 404:
            return None
        raise

    doc = doc_ref.get()
    if doc.exists:
        result = doc.to_dict()
        result['id'] = doc.id
        return result
    return None


def delete_advice(uid: str, advice_id: str) -> bool:
    """Delete an advice document. Returns True on success."""
    _collection_ref(uid).document(advice_id).delete()
    return True


def mark_all_advice_read(uid: str) -> int:
    """Mark all unread, non-dismissed advice as read. Returns count of marked items."""
    query = _collection_ref(uid).where(
        filter=firestore.FieldFilter('is_dismissed', '==', False)
    ).where(
        filter=firestore.FieldFilter('is_read', '==', False)
    ).limit(1000)

    count = 0
    now = datetime.now(timezone.utc)
    for doc in query.stream():
        doc.reference.update({'is_read': True, 'updated_at': now})
        count += 1
    return count
