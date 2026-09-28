"""
Daily Summaries database module

Structure:
users/{uid}/daily_summaries/{summary_id}
    * id: str
    * date: str (YYYY-MM-DD)
    * created_at: timestamp
    * headline: str
    * overview: str
    * day_emoji: str
    * highlights: List[TopicHighlight]
    * action_items: List[ActionItemSummary]
    * people_mentioned: List[PersonMentioned]
    * memorable_moments: List[MemorabeMoment]
    * stats: DayStats
    * tomorrow_focus: str
    * overall_sentiment: str

users/{uid}/desktop_daily_usage/{date}__{client_device_id}
    * date/timezone/client_device_id
    * watching_seconds/listening_seconds
    * proactive_cards_shown/proactive_cards_acted/ptt_turns
    * updated_at
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

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


def _clean_uid(uid: Any) -> str:
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError('uid must be a non-empty string')
    return uid.strip()


def _clean_id(val: Any, name: str = 'identifier') -> str:
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f'{name} must be a non-empty string')
    return val.strip()


def _clean_date(val: Any, name: str = 'date') -> str:
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f'{name} must be a non-empty string')
    return val.strip()


def upsert_desktop_daily_usage(
    uid: str,
    date: str,
    timezone_name: str,
    client_device_id: str,
    counters: Dict[str, int],
) -> None:
    """Atomically merge one device's running daily counters by maximum value."""
    clean_uid = _clean_uid(uid)
    clean_date = _clean_date(date, 'date')
    clean_device_id = _clean_id(client_device_id, 'client_device_id')
    clean_tz = timezone_name.strip() if isinstance(timezone_name, str) and timezone_name.strip() else 'UTC'
    if not isinstance(counters, dict):
        raise ValueError('counters must be a dictionary')

    user_ref = db.collection('users').document(clean_uid)
    usage_ref = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).document(f'{clean_date}__{clean_device_id}')
    transaction = db.transaction()

    @firestore.transactional
    def merge_running_totals(write_transaction: Any) -> None:
        snapshot = usage_ref.get(transaction=write_transaction)
        existing_raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else {}
        existing = existing_raw if isinstance(existing_raw, dict) else {}
        payload: Dict[str, Any] = {
            'date': clean_date,
            'timezone': clean_tz,
            'client_device_id': clean_device_id,
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
    clean_uid = _clean_uid(uid)
    clean_date = _clean_date(date, 'date')
    user_ref = db.collection('users').document(clean_uid)
    query = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).where(filter=FieldFilter('date', '==', clean_date))
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
    clean_uid = _clean_uid(uid)
    if not isinstance(summary_data, dict):
        raise ValueError('summary_data must be a dictionary')
    summary_id = _clean_id(summary_data.get('id'), 'summary_id')

    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    payload = dict(summary_data)
    payload['id'] = summary_id
    summary_ref.set(payload)
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
    clean_uid = _clean_uid(uid)
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
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
    clean_uid = _clean_uid(uid)
    clean_date = _clean_date(date, 'date')
    user_ref = db.collection('users').document(clean_uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).where(filter=FieldFilter('date', '==', clean_date)).limit(1)

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
        limit: Maximum number of summaries to return (clamped 1-100)
        offset: Number of summaries to skip (non-negative)
        start_date: Filter summaries from this date (YYYY-MM-DD)
        end_date: Filter summaries until this date (YYYY-MM-DD)

    Returns:
        List of summary data dicts
    """
    clean_uid = _clean_uid(uid)
    safe_limit = max(1, min(int(limit) if isinstance(limit, int) and not isinstance(limit, bool) else 30, 100))
    safe_offset = max(0, int(offset) if isinstance(offset, int) and not isinstance(offset, bool) else 0)

    user_ref = db.collection('users').document(clean_uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION)

    if start_date is not None and isinstance(start_date, str) and start_date.strip():
        query = query.where(filter=FieldFilter('date', '>=', start_date.strip()))
    if end_date is not None and isinstance(end_date, str) and end_date.strip():
        query = query.where(filter=FieldFilter('date', '<=', end_date.strip()))

    query = query.order_by('date', direction=firestore.Query.DESCENDING)
    query = query.limit(safe_limit).offset(safe_offset)

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
    clean_uid = _clean_uid(uid)
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    if not isinstance(summary_data, dict):
        raise ValueError('summary_data must be a dictionary')

    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    # Force id back to the existing doc id: the generator always allocates a
    # fresh UUID, and we don't want that leaking into the stored payload
    # where readers key off summary['id'].
    payload: Dict[str, Any] = {**summary_data, 'id': clean_summary_id}
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
    clean_uid = _clean_uid(uid)
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    summary_ref.delete()
    redis_db.remove_daily_summary_to_uid(clean_summary_id)
    return True


def set_daily_summary_visibility(uid: str, summary_id: str, visibility: str) -> None:
    clean_uid = _clean_uid(uid)
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    if not isinstance(visibility, str) or not visibility.strip():
        raise ValueError('visibility must be a non-empty string')
    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    summary_ref.update({'visibility': visibility.strip()})


def get_summaries_count(uid: str) -> int:
    """
    Get total count of daily summaries for a user.

    Args:
        uid: User ID

    Returns:
        Count of summaries
    """
    clean_uid = _clean_uid(uid)
    user_ref = db.collection('users').document(clean_uid)
    count_query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).count()
    result = count_query.get()
    return int(result[0][0].value or 0)
