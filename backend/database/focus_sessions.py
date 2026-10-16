"""Focus sessions — focus/distraction tracking and statistics.

Collection: users/{uid}/focus_sessions
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, cast

from google.api_core.exceptions import NotFound
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import db

logger = logging.getLogger(__name__)


def _user_col(uid: str, collection: str) -> Any:
    """Shorthand for users/{uid}/{collection}."""
    clean_uid = uid.strip() if isinstance(uid, str) else ''
    if not clean_uid:
        raise ValueError('uid must be a non-empty string')
    return db.collection('users').document(clean_uid).collection(collection)


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def create_focus_session(uid: str, status: str, app_or_site: str, description: str, **kwargs: Any) -> Dict[str, Any]:
    clean_uid = uid.strip() if isinstance(uid, str) else ''
    if not clean_uid:
        raise ValueError('uid must be a non-empty string')
    raw_status = str(status).strip().lower() if status is not None else 'focused'
    clean_status = raw_status if raw_status in ('focused', 'distracted') else 'focused'
    clean_app = str(app_or_site).strip() if app_or_site is not None and str(app_or_site).strip() else 'Unknown'
    clean_desc = str(description) if description is not None else ''
    clean_msg = str(kwargs['message']) if kwargs.get('message') is not None else None
    duration_seconds = _normalize_duration_seconds(kwargs.get('duration_seconds'))

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        'id': session_id,
        'status': clean_status,
        'app_or_site': clean_app,
        'description': clean_desc,
        'message': clean_msg,
        'created_at': now,
        'duration_seconds': duration_seconds,
    }
    _user_col(clean_uid, 'focus_sessions').document(session_id).set(doc)
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
    if not uid or not isinstance(uid, str) or not uid.strip():
        return []
    clean_uid = uid.strip()
    col = _user_col(clean_uid, 'focus_sessions')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    if date:
        if not isinstance(date, str) or not date.strip():
            return []
        try:
            day_start = datetime.strptime(date.strip(), '%Y-%m-%d').replace(tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            query = query.where(filter=FieldFilter('created_at', '>=', day_start))
            query = query.where(filter=FieldFilter('created_at', '<', day_end))
        except (ValueError, TypeError) as e:
            logger.warning(f'get_focus_sessions invalid date={date!r} for uid={clean_uid}: {e}')
            return []

    bounded_limit = max(1, min(limit if isinstance(limit, int) else 100, 5000))
    bounded_offset = max(0, offset if isinstance(offset, int) else 0)
    query = query.offset(bounded_offset).limit(bounded_limit)
    items: List[Dict[str, Any]] = []
    for doc in query.stream():
        data = _typed_doc(doc)
        items.append(_normalize_focus_session_doc(doc.id, data))
    return items


def delete_focus_session(uid: str, session_id: str) -> bool:
    if not uid or not isinstance(uid, str) or not uid.strip():
        return False
    if not session_id or not isinstance(session_id, str) or not session_id.strip():
        return False
    clean_uid = uid.strip()
    clean_session_id = session_id.strip()
    ref = _user_col(clean_uid, 'focus_sessions').document(clean_session_id)
    try:
        if not getattr(ref.get(), "exists", False):
            return False
        ref.delete()
        return True
    except NotFound:
        return False


def get_focus_stats(uid: str, date: Optional[str] = None) -> Dict[str, Any]:
    # A day's stats need a day.  Passing date=None straight through meant
    # get_focus_sessions applied no created_at filter at all, so the totals
    # below were summed from the user's entire history -- up to the 5000-row
    # cap -- and then labelled with a single date.  Anyone opening focus
    # stats without picking a day saw months of focus reported as today's.
    # get_daily_score resolves the same way: no date means today.
    if isinstance(date, str) and date.strip():
        clean_date = date.strip()
        try:
            datetime.strptime(clean_date, '%Y-%m-%d')
            day = clean_date
        except ValueError:
            logger.warning(f'get_focus_stats invalid date={clean_date!r}, falling back to today')
            day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    else:
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    if not uid or not isinstance(uid, str) or not uid.strip():
        return {
            'date': day,
            'focused_minutes': 0,
            'distracted_minutes': 0,
            'session_count': 0,
            'focused_count': 0,
            'distracted_count': 0,
            'top_distractions': [],
        }

    clean_uid = uid.strip()
    sessions = get_focus_sessions(clean_uid, date=day, limit=5000, offset=0)
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
