"""
Daily Summaries database module

Structure:
users/{uid}/daily_summaries/{summary_id}
    ├── id: str
    ├── date: str (YYYY-MM-DD)
    ├── created_at: timestamp
    ├── headline: str
    ├── overview: str
    ├── day_emoji: str
    ├── highlights: List[TopicHighlight]
    ├── action_items: List[ActionItemSummary]
    ├── people_mentioned: List[PersonMentioned]
    ├── memorable_moments: List[MemorabeMoment]
    ├── stats: DayStats
    ├── tomorrow_focus: str
    └── overall_sentiment: str

users/{uid}/desktop_daily_usage/{date}__{client_device_id}
    ├── date/timezone/client_device_id
    ├── watching_seconds/listening_seconds
    ├── proactive_cards_shown/proactive_cards_acted/ptt_turns
    └── updated_at
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore
from ._client import db
from . import redis_db

DAILY_SUMMARIES_COLLECTION = 'daily_summaries'
DESKTOP_DAILY_USAGE_COLLECTION = 'desktop_daily_usage'
DESKTOP_DAILY_USAGE_COUNTER_FIELDS = (
    'watching_seconds',
    'listening_seconds',
    'proactive_cards_shown',
    'proactive_cards_acted',
    'ptt_turns',
)


def upsert_desktop_daily_usage(
    uid: str,
    date: str,
    timezone_name: str,
    client_device_id: str,
    counters: Dict[str, int],
) -> None:
    """Atomically merge one device's running daily counters by maximum value."""
    if (
        not uid or not isinstance(uid, str) or not uid.strip()
        or not date or not isinstance(date, str) or not date.strip()
        or not client_device_id or not isinstance(client_device_id, str) or not client_device_id.strip()
    ):
        raise ValueError('uid, date, and client_device_id are required')
    uid = uid.strip()
    date = date.strip()
    client_device_id = client_device_id.strip()
    counters = counters if isinstance(counters, dict) else {}

    user_ref = db.collection('users').document(uid)
    usage_ref = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).document(f'{date}__{client_device_id}')
    transaction = db.transaction()

    @firestore.transactional
    def merge_running_totals(write_transaction: Any) -> None:
        snapshot = usage_ref.get(transaction=write_transaction)
        existing_raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else {}
        existing = existing_raw if isinstance(existing_raw, dict) else {}
        payload: Dict[str, Any] = {
            'date': date,
            'timezone': timezone_name,
            'client_device_id': client_device_id,
            'updated_at': datetime.now(timezone.utc),
        }
        for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
            previous = existing.get(field, 0)
            previous_value = previous if isinstance(previous, int) and not isinstance(previous, bool) else 0
            incoming = counters.get(field, 0)
            incoming_value = incoming if isinstance(incoming, int) and not isinstance(incoming, bool) else 0
            payload[field] = max(previous_value, incoming_value)
        write_transaction.set(usage_ref, payload)

    merge_running_totals(transaction)


def get_desktop_daily_usage(uid: str, date: str) -> Dict[str, int]:
    """Sum every device's counters for one local calendar date.

    A date with no usage documents returns every counter as zero.
    """
    if not uid or not isinstance(uid, str) or not uid.strip() or not date or not isinstance(date, str) or not date.strip():
        return {field: 0 for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS}
    uid = uid.strip()
    date = date.strip()
    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).where(filter=FieldFilter('date', '==', date))
    totals = {field: 0 for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS}
    for doc in query.stream():
        raw = doc.to_dict()
        if not isinstance(raw, dict):
            continue
        for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
            value = raw.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                totals[field] += value
    return totals


def create_daily_summary(uid: str, summary_data: Dict[str, Any]) -> str:
    """
    Create a new daily summary document.

    Args:
        uid: User ID
        summary_data: Dictionary containing the summary data

    Returns:
        The summary ID
    """
    if not uid or not isinstance(uid, str) or not uid.strip():
        raise ValueError('uid is required')
    if not isinstance(summary_data, dict):
        raise ValueError('summary_data must be a dictionary')
    summary_id = summary_data.get('id')
    if not summary_id or not isinstance(summary_id, str) or not summary_id.strip():
        raise ValueError('summary_data id is required')

    uid = uid.strip()
    summary_id = summary_id.strip()
    user_ref = db.collection('users').document(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    summary_ref.set(summary_data, merge=True)
    return summary_id


def get_daily_summary(uid: str, summary_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single daily summary by ID.

    Args:
        uid: User ID
        summary_id: Summary document ID

    Returns:
        Summary data dict or None if not found
    """
    if not uid or not isinstance(uid, str) or not uid.strip() or not summary_id or not isinstance(summary_id, str) or not summary_id.strip():
        return None
    uid = uid.strip()
    summary_id = summary_id.strip()
    user_ref = db.collection('users').document(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    doc = summary_ref.get()

    if getattr(doc, "exists", False):
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_daily_summary_by_date(uid: str, date: str) -> Optional[Dict[str, Any]]:
    """
    Get a daily summary by date (YYYY-MM-DD format).

    Args:
        uid: User ID
        date: Date string in YYYY-MM-DD format

    Returns:
        Summary data dict or None if not found
    """
    if not uid or not isinstance(uid, str) or not uid.strip() or not date or not isinstance(date, str) or not date.strip():
        return None
    uid = uid.strip()
    date = date.strip()
    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).where(filter=FieldFilter('date', '==', date)).limit(1)

    docs = list(query.stream())
    if docs:
        raw: object = docs[0].to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_daily_summaries(
    uid: str,
    limit: int = 30,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get list of daily summaries for a user, ordered by date descending.

    Args:
        uid: User ID
        limit: Maximum number of summaries to return
        offset: Number of summaries to skip
        start_date: Filter summaries from this date (YYYY-MM-DD)
        end_date: Filter summaries until this date (YYYY-MM-DD)

    Returns:
        List of summary data dicts
    """
    if not uid or not isinstance(uid, str) or not uid.strip():
        return []
    uid = uid.strip()
    limit = max(1, min(limit if isinstance(limit, int) else 30, 100))
    offset = max(0, offset if isinstance(offset, int) else 0)

    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION)

    if start_date:
        query = query.where(filter=FieldFilter('date', '>=', start_date.strip()))
    if end_date:
        query = query.where(filter=FieldFilter('date', '<=', end_date.strip()))

    query = query.order_by('date', direction=firestore.Query.DESCENDING)
    query = query.limit(limit).offset(offset)

    summaries: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            summaries.append(cast(Dict[str, Any], raw))
    return summaries


def update_daily_summary(uid: str, summary_id: str, summary_data: Dict[str, Any]) -> None:
    """
    Overwrite an existing daily summary in place, preserving the original id.

    Used by the regenerate flow so that re-running generation replaces the
    contents of the summary the user is looking at instead of spawning a
    duplicate doc for the same date.
    """
    if not uid or not isinstance(uid, str) or not uid.strip() or not summary_id or not isinstance(summary_id, str) or not summary_id.strip():
        raise ValueError('uid and summary_id are required')
    if not isinstance(summary_data, dict):
        raise ValueError('summary_data must be a dictionary')

    uid = uid.strip()
    summary_id = summary_id.strip()
    user_ref = db.collection('users').document(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    # Force id back to the existing doc id: the generator always allocates a
    # fresh UUID, and we don't want that leaking into the stored payload
    # where readers key off summary['id'].
    payload: Dict[str, Any] = {**summary_data, 'id': summary_id}
    summary_ref.set(payload)


def delete_daily_summary(uid: str, summary_id: str) -> bool:
    """
    Delete a daily summary.

    Args:
        uid: User ID
        summary_id: Summary document ID

    Returns:
        True if deleted successfully
    """
    if not uid or not isinstance(uid, str) or not uid.strip() or not summary_id or not isinstance(summary_id, str) or not summary_id.strip():
        return False

    uid = uid.strip()
    summary_id = summary_id.strip()
    user_ref = db.collection('users').document(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    try:
        summary_ref.delete()
    except NotFound:
        pass
    try:
        redis_db.remove_daily_summary_to_uid(summary_id)
    except Exception:
        pass
    return True


def set_daily_summary_visibility(uid: str, summary_id: str, visibility: str) -> bool:
    if not uid or not isinstance(uid, str) or not uid.strip() or not summary_id or not isinstance(summary_id, str) or not summary_id.strip():
        raise ValueError('uid and summary_id are required')
    if not visibility or not isinstance(visibility, str) or not visibility.strip():
        raise ValueError('visibility is required')

    uid = uid.strip()
    summary_id = summary_id.strip()
    visibility = visibility.strip()
    user_ref = db.collection('users').document(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    try:
        summary_ref.update({'visibility': visibility})
        return True
    except NotFound:
        return False


def get_summaries_count(uid: str) -> int:
    """
    Get total count of daily summaries for a user.

    Args:
        uid: User ID

    Returns:
        Count of summaries
    """
    if not uid or not isinstance(uid, str) or not uid.strip():
        return 0
    uid = uid.strip()
    user_ref = db.collection('users').document(uid)
    count_query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).count()
    result = count_query.get()
    if not result or not result[0]:
        return 0
    return int(result[0][0].value or 0)
