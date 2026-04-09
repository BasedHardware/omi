"""Focus sessions — focus/distraction tracking and statistics.

Collection: users/{uid}/focus_sessions
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import db

logger = logging.getLogger(__name__)


def _user_col(uid: str, collection: str):
    """Shorthand for users/{uid}/{collection}."""
    return db.collection('users').document(uid).collection(collection)


def create_focus_session(uid: str, status: str, app_or_site: str, description: str, **kwargs) -> dict:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': session_id,
        'status': status,
        'app_or_site': app_or_site,
        'description': description,
        'message': kwargs.get('message'),
        'created_at': now,
        'duration_seconds': kwargs.get('duration_seconds'),
    }
    _user_col(uid, 'focus_sessions').document(session_id).set(doc)
    return doc


def get_focus_sessions(uid: str, date: str = None, limit: int = 100, offset: int = 0) -> List[dict]:
    col = _user_col(uid, 'focus_sessions')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    if date:
        day_start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        query = query.where(filter=FieldFilter('created_at', '>=', day_start))
        query = query.where(filter=FieldFilter('created_at', '<', day_end))

    query = query.offset(offset).limit(limit)
    items = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(data)
    return items


def delete_focus_session(uid: str, session_id: str) -> bool:
    ref = _user_col(uid, 'focus_sessions').document(session_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def get_focus_stats(uid: str, date: str = None) -> dict:
    sessions = get_focus_sessions(uid, date=date, limit=5000, offset=0)
    focused_count = 0
    distracted_count = 0
    total_focus_seconds = 0
    total_distracted_seconds = 0
    distractions = {}

    for s in sessions:
        if s.get('status') == 'focused':
            focused_count += 1
            total_focus_seconds += s.get('duration_seconds') or 0
        elif s.get('status') == 'distracted':
            distracted_count += 1
            total_distracted_seconds += s.get('duration_seconds') or 60
            app = s.get('app_or_site', 'Unknown')
            entry = distractions.setdefault(app, {'total_seconds': 0, 'count': 0})
            entry['total_seconds'] += s.get('duration_seconds') or 60
            entry['count'] += 1

    top = sorted(distractions.items(), key=lambda x: x[1]['total_seconds'], reverse=True)[:5]

    return {
        'date': date or datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'focused_minutes': total_focus_seconds // 60,
        'distracted_minutes': total_distracted_seconds // 60,
        'session_count': focused_count + distracted_count,
        'focused_count': focused_count,
        'distracted_count': distracted_count,
        'top_distractions': [
            {'app_or_site': app, 'total_seconds': v['total_seconds'], 'count': v['count']} for app, v in top
        ],
    }
