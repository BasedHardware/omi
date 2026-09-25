"""Focus sessions — focus/distraction tracking and statistics.

Collection: users/{uid}/focus_sessions
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import db

logger = logging.getLogger(__name__)


def _user_col(uid: str, collection: str) -> Any:
    """Shorthand for users/{uid}/{collection}."""
    return db.collection('users').document(uid).collection(collection)


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def create_focus_session(uid: str, status: str, app_or_site: str, description: str, **kwargs: Any) -> Dict[str, Any]:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
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


def _normalize_duration_seconds(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        coerced = int(value)
        return coerced if coerced >= 0 else 0
    if isinstance(value, str):
        try:
            coerced = int(float(value.strip()))
            return coerced if coerced >= 0 else 0
        except ValueError:
            return None
    return None


def _normalize_created_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if hasattr(value, 'timestamp'):
        try:
            return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
        except Exception:
            pass
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _normalize_focus_session_doc(doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    raw_app = data.get('app_or_site')
    app_or_site = str(raw_app).strip() if raw_app is not None and str(raw_app).strip() else 'Unknown'
    raw_status = data.get('status')
    status = str(raw_status).strip() if raw_status is not None and str(raw_status).strip() else 'focused'
    raw_description = data.get('description')
    description = str(raw_description) if raw_description is not None else ''
    raw_message = data.get('message')
    message = str(raw_message) if raw_message is not None else None
    return {
        **data,
        'id': str(doc_id or data.get('id') or ''),
        'status': status,
        'app_or_site': app_or_site,
        'description': description,
        'message': message,
        'created_at': _normalize_created_at(data.get('created_at')),
        'duration_seconds': _normalize_duration_seconds(data.get('duration_seconds')),
    }


def get_focus_sessions(uid: str, date: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    col = _user_col(uid, 'focus_sessions')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    if date:
        day_start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        query = query.where(filter=FieldFilter('created_at', '>=', day_start))
        query = query.where(filter=FieldFilter('created_at', '<', day_end))

    query = query.offset(offset).limit(limit)
    items: List[Dict[str, Any]] = []
    for doc in query.stream():
        data = _typed_doc(doc)
        items.append(_normalize_focus_session_doc(doc.id, data))
    return items


def delete_focus_session(uid: str, session_id: str) -> bool:
    ref = _user_col(uid, 'focus_sessions').document(session_id)
    if not getattr(ref.get(), "exists", False):
        return False
    ref.delete()
    return True


def get_focus_stats(uid: str, date: Optional[str] = None) -> Dict[str, Any]:
    # A day's stats need a day.  Passing date=None straight through meant
    # get_focus_sessions applied no created_at filter at all, so the totals
    # below were summed from the user's entire history -- up to the 5000-row
    # cap -- and then labelled with a single date.  Anyone opening focus
    # stats without picking a day saw months of focus reported as today's.
    # get_daily_score resolves the same way: no date means today.
    day = date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    sessions = get_focus_sessions(uid, date=day, limit=5000, offset=0)
    focused_count = 0
    distracted_count = 0
    total_focus_seconds = 0
    total_distracted_seconds = 0
    distractions: Dict[str, Dict[str, int]] = {}

    for s in sessions:
        duration = _normalize_duration_seconds(s.get('duration_seconds'))
        if s.get('status') == 'focused':
            focused_count += 1
            total_focus_seconds += 0 if duration is None else duration
        elif s.get('status') == 'distracted':
            distracted_count += 1
            distracted_duration = 60 if duration is None else duration
            total_distracted_seconds += distracted_duration
            raw_app = s.get('app_or_site')
            app = str(raw_app).strip() if raw_app is not None and str(raw_app).strip() else 'Unknown'
            entry = distractions.setdefault(app, {'total_seconds': 0, 'count': 0})
            entry['total_seconds'] += distracted_duration
            entry['count'] += 1

    top = sorted(distractions.items(), key=lambda x: x[1]['total_seconds'], reverse=True)[:5]

    return {
        'date': day,
        'focused_minutes': total_focus_seconds // 60,
        'distracted_minutes': total_distracted_seconds // 60,
        'session_count': focused_count + distracted_count,
        'focused_count': focused_count,
        'distracted_count': distracted_count,
        'top_distractions': [
            {'app_or_site': app, 'total_seconds': v['total_seconds'], 'count': v['count']} for app, v in top
        ],
    }
