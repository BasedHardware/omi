from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union, cast

from google.cloud import firestore

from ._client import data_plane_db as db
import logging

logger = logging.getLogger(__name__)

SCREEN_ACTIVITY_COLLECTION = 'screen_activity'
USERS_COLLECTION = 'users'

# Date inputs may arrive as datetime or as pre-formatted 'YYYY-MM-DD HH:MM:SS.mmm' strings.
DateInput = Union[datetime, str]


def normalize_screen_activity_timestamp(value: DateInput, *, end_of_second: bool = False) -> str:
    """Return the one lexicographically sortable timestamp representation stored in Firestore."""
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        try:
            parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('screen activity timestamp must be ISO-8601 compatible') from exc

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    milliseconds = 999 if end_of_second and parsed.microsecond == 0 else parsed.microsecond // 1000
    return f"{parsed.strftime('%Y-%m-%d %H:%M:%S')}.{milliseconds:03d}"


def get_screen_activity_ids(uid: str) -> List[str]:
    """Return all screen activity document IDs for a user (IDs-only projection).

    Used for bulk operations like account deletion (e.g. to purge derived Pinecone vectors)."""
    coll = db.collection(USERS_COLLECTION).document(uid).collection(SCREEN_ACTIVITY_COLLECTION)
    return [str(doc.id) for doc in coll.select([]).stream()]


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
            doc_id = str(row.get('storageId') or row['id'])
            doc_data = {
                'timestamp': row['timestamp'],
                'appName': row.get('appName', ''),
                'windowTitle': row.get('windowTitle', ''),
                'ocrText': (row.get('ocrText') or '')[:1000],
                # The Firestore/vector ID is device-qualified, while the desktop
                # frame database is addressed by this original numeric ID.
                'localScreenshotId': str(row['id']),
                # The desktop only creates sync rows from captures admitted by
                # Rewind's local exclusion policy; persist that attestation so
                # automatic selection remains fail closed.
                'captureEligible': row.get('captureEligible') is True,
            }
            if row.get('deviceName'):
                doc_data['deviceName'] = row['deviceName']
            if row.get('clientDeviceId'):
                doc_data['clientDeviceId'] = row['clientDeviceId']
            doc_data['accountGeneration'] = max(0, int(row.get('accountGeneration') or 0))
            retention = row.get('deviceRetentionSeconds')
            if isinstance(retention, int) and retention > 0:
                doc_data['deviceRetentionSeconds'] = retention
            batch.set(collection_ref.document(doc_id), doc_data)
        batch.commit()
        written += len(chunk)

    return written


def get_screen_activity(
    uid: str,
    start_date: Optional[DateInput] = None,
    end_date: Optional[DateInput] = None,
    app_filter: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Query screen activity by date range with optional app filter."""
    collection_ref = db.collection(USERS_COLLECTION).document(uid).collection(SCREEN_ACTIVITY_COLLECTION)

    query = collection_ref.order_by('timestamp', direction=firestore.Query.ASCENDING)

    if start_date:
        ts = normalize_screen_activity_timestamp(start_date)
        query = query.where(filter=firestore.FieldFilter('timestamp', '>=', ts))
    if end_date:
        ts = normalize_screen_activity_timestamp(end_date, end_of_second=True)
        query = query.where(filter=firestore.FieldFilter('timestamp', '<=', ts))
    if app_filter:
        query = query.where(filter=firestore.FieldFilter('appName', '==', app_filter))

    query = query.limit(limit)

    results: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        results.append(data)

    return results


def get_screen_activity_summary(
    uid: str,
    start_date: Optional[DateInput] = None,
    end_date: Optional[DateInput] = None,
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
                'window_titles': set[Any](),
            }
        apps[app_name]['count'] += 1
        apps[app_name]['last_seen'] = row.get('timestamp')
        title = row.get('windowTitle', '')
        if title:
            titles: set[Any] = apps[app_name]['window_titles']
            titles.add(title)

    # Convert sets to lists for serialization
    for app_name in apps:
        titles = apps[app_name]['window_titles']
        apps[app_name]['window_titles'] = list(titles)[:10]  # Top 10 titles

    return {
        'apps': apps,
        'total_screenshots': len(rows),
    }
