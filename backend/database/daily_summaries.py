"""
Daily Summaries and Desktop Daily Usage Database Module.

Collections:
users/{uid}/daily_summaries/{id}
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


def _validate_identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    if '/' in cleaned or '\\' in cleaned:
        raise ValueError(f"{field_name} cannot contain path separators")
    return cleaned


def _validate_and_get_counter(value: Any, field_name: Optional[str] = None) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def upsert_desktop_daily_usage(
    uid: str,
    date: str,
    timezone_name: str,
    client_device_id: str,
    counters: Dict[str, int],
) -> None:
    """Atomically merge one device's running daily counters by maximum value."""
    valid_uid = _validate_identifier(uid, 'uid')
    valid_date = _validate_identifier(date, 'date')
    valid_tz = _validate_identifier(timezone_name, 'timezone_name')
    valid_device = _validate_identifier(client_device_id, 'client_device_id')

    user_ref = db.collection('users').document(valid_uid)
    usage_ref = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).document(f'{valid_date}__{valid_device}')
    transaction = db.transaction()

    @firestore.transactional
    def merge_running_totals(write_transaction: Any) -> None:
        snapshot = usage_ref.get(transaction=write_transaction)
        existing_raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else {}
        existing = existing_raw if isinstance(existing_raw, dict) else {}
        payload: Dict[str, Any] = {
            'date': valid_date,
            'timezone': valid_tz,
            'client_device_id': valid_device,
            'updated_at': datetime.now(timezone.utc),
        }
        counter_dict = counters if isinstance(counters, dict) else {}
        for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
            previous = existing.get(field, 0)
            previous_value = _validate_and_get_counter(previous, field)
            incoming = counter_dict.get(field, 0)
            incoming_value = _validate_and_get_counter(incoming, field)
            payload[field] = max(previous_value, incoming_value)
        write_transaction.set(usage_ref, payload)

    merge_running_totals(transaction)


def get_desktop_daily_usage(uid: str, date: str) -> Dict[str, int]:
    """Sum every device's counters for one local calendar date.

    A date with no usage documents returns every counter as zero.
    """
    valid_uid = _validate_identifier(uid, 'uid')
    valid_date = _validate_identifier(date, 'date')
    user_ref = db.collection('users').document(valid_uid)
    query = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).where(filter=FieldFilter('date', '==', valid_date))
    totals = {field: 0 for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS}
    for doc in query.stream():
        raw = doc.to_dict()
        if not isinstance(raw, dict):
            continue
        for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
            value = raw.get(field)
            totals[field] += _validate_and_get_counter(value, field)
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
    valid_uid = _validate_identifier(uid, 'uid')
    if not isinstance(summary_data, dict):
        raise ValueError("summary_data must be a dictionary")
    summary_id = _validate_identifier(summary_data.get('id'), 'summary_id')
    user_ref = db.collection('users').document(valid_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    summary_ref.set(summary_data)
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
    valid_uid = _validate_identifier(uid, 'uid')
    valid_id = _validate_identifier(summary_id, 'summary_id')
    user_ref = db.collection('users').document(valid_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(valid_id)
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
    valid_uid = _validate_identifier(uid, 'uid')
    valid_date = _validate_identifier(date, 'date')
    user_ref = db.collection('users').document(valid_uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).where(filter=FieldFilter('date', '==', valid_date)).limit(1)

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
    valid_uid = _validate_identifier(uid, 'uid')
    safe_limit = max(1, min(limit if isinstance(limit, int) else 30, 100))
    safe_offset = max(0, offset if isinstance(offset, int) else 0)

    user_ref = db.collection('users').document(valid_uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION)

    if start_date:
        valid_start = _validate_identifier(start_date, 'start_date')
        query = query.where(filter=FieldFilter('date', '>=', valid_start))
    if end_date:
        valid_end = _validate_identifier(end_date, 'end_date')
        query = query.where(filter=FieldFilter('date', '<=', valid_end))

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
    valid_uid = _validate_identifier(uid, 'uid')
    valid_id = _validate_identifier(summary_id, 'summary_id')
    if not isinstance(summary_data, dict):
        raise ValueError("summary_data must be a dictionary")
    user_ref = db.collection('users').document(valid_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(valid_id)
    payload: Dict[str, Any] = {**summary_data, 'id': valid_id}
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
    valid_uid = _validate_identifier(uid, 'uid')
    valid_id = _validate_identifier(summary_id, 'summary_id')
    user_ref = db.collection('users').document(valid_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(valid_id)
    summary_ref.delete()
    redis_db.remove_daily_summary_to_uid(valid_id)
    return True


def set_daily_summary_visibility(uid: str, summary_id: str, visibility: str) -> None:
    valid_uid = _validate_identifier(uid, 'uid')
    valid_id = _validate_identifier(summary_id, 'summary_id')
    user_ref = db.collection('users').document(valid_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(valid_id)
    summary_ref.update({'visibility': visibility})


def get_summaries_count(uid: str) -> int:
    """
    Get total count of daily summaries for a user.

    Args:
        uid: User ID

    Returns:
        Count of summaries
    """
    valid_uid = _validate_identifier(uid, 'uid')
    user_ref = db.collection('users').document(valid_uid)
    count_query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).count()
    result = count_query.get()
    return int(result[0][0].value or 0)
