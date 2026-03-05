import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from google.cloud import firestore

from ._client import db

logger = logging.getLogger(__name__)

USERS_COLLECTION = 'users'
FOCUS_SESSIONS_SUBCOLLECTION = 'focus_sessions'


def _collection_ref(uid: str):
    return db.collection(USERS_COLLECTION).document(uid).collection(FOCUS_SESSIONS_SUBCOLLECTION)


def create_focus_session(uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new focus session document. Returns the created document with id."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    doc_data = {
        'status': data['status'],
        'app_or_site': data['app_or_site'],
        'description': data['description'],
        'created_at': now,
    }
    if data.get('message') is not None:
        doc_data['message'] = data['message']
    if data.get('duration_seconds') is not None:
        doc_data['duration_seconds'] = data['duration_seconds']

    _collection_ref(uid).document(session_id).set(doc_data)

    doc_data['id'] = session_id
    return doc_data


def get_focus_sessions(
    uid: str,
    limit: int = 100,
    offset: int = 0,
    date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query focus sessions, ordered by created_at DESC. Optional date filter (YYYY-MM-DD)."""
    query = _collection_ref(uid).order_by('created_at', direction=firestore.Query.DESCENDING)

    if date:
        day_start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        day_end = day_start.replace(hour=23, minute=59, second=59)
        query = query.where(filter=firestore.FieldFilter('created_at', '>=', day_start))
        query = query.where(filter=firestore.FieldFilter('created_at', '<=', day_end))

    query = query.offset(offset).limit(limit)

    results = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        results.append(data)
    return results


def delete_focus_session(uid: str, session_id: str) -> bool:
    """Delete a focus session document. Returns True on success."""
    _collection_ref(uid).document(session_id).delete()
    return True


def get_focus_sessions_for_stats(uid: str, date: str) -> List[Dict[str, Any]]:
    """Get up to 1000 sessions for a date, for stats computation."""
    return get_focus_sessions(uid, limit=1000, offset=0, date=date)
