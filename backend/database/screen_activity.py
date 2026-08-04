from datetime import datetime
from typing import List, Dict, Any, Optional, Union, cast

from database.store import Filter, ensure_id_segment, get_document_store
import logging

logger = logging.getLogger(__name__)

SCREEN_ACTIVITY_COLLECTION = 'screen_activity'
USERS_COLLECTION = 'users'

# Date inputs may arrive as datetime or as pre-formatted 'YYYY-MM-DD HH:MM:SS.mmm' strings.
DateInput = Union[datetime, str]


def _store():
    return get_document_store()


def _collection_path(uid: str) -> str:
    return f'{USERS_COLLECTION}/{uid}/{SCREEN_ACTIVITY_COLLECTION}'


def get_screen_activity_ids(uid: str) -> List[str]:
    """Return all screen activity document IDs for a user (IDs-only projection).

    Used for bulk operations like account deletion (e.g. to purge derived Pinecone vectors)."""
    return [str(doc_id) for doc_id in _store().list_ids(_collection_path(uid))]


def upsert_screen_activity(uid: str, rows: List[Dict[str, Any]]) -> int:
    """Batch write screen activity rows to Firestore users/{uid}/screen_activity/{id}."""
    if not rows:
        return 0

    collection_path = _collection_path(uid)
    store = _store()
    written = 0

    # Chunked for throughput (adapters honor their own batch limits; Firestore caps at 500).
    for i in range(0, len(rows), 500):
        chunk = rows[i : i + 500]
        batch = store.batch()
        for row in chunk:
            # storageId / id are client-provided; a '/' would split the composed path into extra
            # segments (wrong Mongo collection/key; Firestore rejects the odd-segment path).
            doc_id = ensure_id_segment(str(row.get('storageId') or row['id']))
            doc_data = {
                'timestamp': row['timestamp'],
                'appName': row.get('appName', ''),
                'windowTitle': row.get('windowTitle', ''),
                'ocrText': (row.get('ocrText') or '')[:1000],
            }
            if row.get('deviceName'):
                doc_data['deviceName'] = row['deviceName']
            if row.get('clientDeviceId'):
                doc_data['clientDeviceId'] = row['clientDeviceId']
            batch.set(f'{collection_path}/{doc_id}', doc_data)
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
    collection_path = _collection_path(uid)

    filters: List[Filter] = []
    if start_date:
        # Timestamps stored as 'YYYY-MM-DD HH:MM:SS.mmm' strings — must match format for comparison
        ts = start_date.strftime('%Y-%m-%d %H:%M:%S.000') if isinstance(start_date, datetime) else str(start_date)
        filters.append(('timestamp', '>=', ts))
    if end_date:
        ts = end_date.strftime('%Y-%m-%d %H:%M:%S.999') if isinstance(end_date, datetime) else str(end_date)
        filters.append(('timestamp', '<=', ts))
    if app_filter:
        filters.append(('appName', '==', app_filter))

    results: List[Dict[str, Any]] = []
    for doc in _store().query(
        collection_path,
        filters=filters,
        order_by='timestamp',
        direction='asc',
        limit=limit,
    ):
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


def get_screen_activity_ocr_text(uid: str, sid: str, max_len: int = 200) -> str:
    """Return the OCR text for one screen-activity document, truncated to max_len.

    Returns '' if the document is missing or has no OCR text.
    """
    # Normalize the id segment (as the write path does) so a sid containing '/' can't compose a path
    # that reads an unintended document/collection.
    doc = _store().get(f'{_collection_path(uid)}/{ensure_id_segment(str(sid))}')
    if doc.exists:
        data = cast(Dict[str, Any], doc.to_dict() or {})
        return (data.get('ocrText', '') or '')[:max_len]
    return ''
