from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from google.cloud import firestore

from ._client import db
import logging

logger = logging.getLogger(__name__)

SCREEN_ACTIVITY_COLLECTION = 'screen_activity'
USERS_COLLECTION = 'users'


def upsert_screen_activity(uid: str, rows: List[Dict[str, Any]]) -> int:
    """Batch write screen activity rows to Firestore users/{uid}/screen_activity/{id}."""
    if not rows:
        return 0

    collection_ref = db.collection(USERS_COLLECTION).document(uid).collection(SCREEN_ACTIVITY_COLLECTION)
    written = 0

    # Firestore batch limit is 500
    for i in range(0, len(rows), 500):
        chunk = rows[i : i + 500]
        batch = db.batch()
        for row in chunk:
            doc_id = str(row['id'])
            doc_data = {
                'timestamp': row['timestamp'],
                'appName': row.get('appName', ''),
                'windowTitle': row.get('windowTitle', ''),
                'ocrText': (row.get('ocrText') or '')[:1000],
            }
            batch.set(collection_ref.document(doc_id), doc_data)
        batch.commit()
        written += len(chunk)

    return written


def get_screen_activity(
    uid: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    app_filter: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Query screen activity by date range with optional app filter."""
    collection_ref = db.collection(USERS_COLLECTION).document(uid).collection(SCREEN_ACTIVITY_COLLECTION)

    query = collection_ref.order_by('timestamp', direction=firestore.Query.ASCENDING)

    if start_date:
        ts = start_date.isoformat() if isinstance(start_date, datetime) else start_date
        query = query.where(filter=firestore.FieldFilter('timestamp', '>=', ts))
    if end_date:
        ts = end_date.isoformat() if isinstance(end_date, datetime) else end_date
        query = query.where(filter=firestore.FieldFilter('timestamp', '<=', ts))
    if app_filter:
        query = query.where(filter=firestore.FieldFilter('appName', '==', app_filter))

    query = query.limit(limit)

    results = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        results.append(data)

    return results


def get_screen_activity_summary(
    uid: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Get aggregated app usage summary — groups by appName, counts screenshots, estimates time."""
    rows = get_screen_activity(uid, start_date=start_date, end_date=end_date, limit=5000)

    if not rows:
        return {'apps': {}, 'total_screenshots': 0}

    apps: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        app_name = row.get('appName') or 'Unknown'
        if app_name not in apps:
            apps[app_name] = {
                'count': 0,
                'first_seen': row.get('timestamp'),
                'last_seen': row.get('timestamp'),
                'window_titles': set(),
            }
        apps[app_name]['count'] += 1
        apps[app_name]['last_seen'] = row.get('timestamp')
        title = row.get('windowTitle', '')
        if title:
            apps[app_name]['window_titles'].add(title)

    # Convert sets to lists for serialization
    for app_name in apps:
        titles = apps[app_name]['window_titles']
        apps[app_name]['window_titles'] = list(titles)[:10]  # Top 10 titles

    return {
        'apps': apps,
        'total_screenshots': len(rows),
    }
