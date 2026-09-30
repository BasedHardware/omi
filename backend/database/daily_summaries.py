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


def _validate_identifier(name: str, val: Any) -> str:
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"{name} must be a non-empty string")
    cleaned = val.strip()
    if '/' in cleaned:
        raise ValueError(f"Invalid character '/' in identifier {name}")
    return cleaned


def upsert_desktop_daily_usage(
    uid: str,
    date: str,
    timezone_name: str,
    client_device_id: str,
    counters: Dict[str, int],
) -> None:
    """Atomically merge one device's running daily counters by maximum value."""
    clean_uid = _validate_identifier('uid', uid)
    clean_date = _validate_identifier('date', date)
    clean_dev = _validate_identifier('client_device_id', client_device_id)

    user_ref = db.collection('users').document(clean_uid)
    usage_ref = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).document(f'{clean_date}__{clean_dev}')
    transaction = db.transaction()

    @firestore.transactional
    def merge_running_totals(write_transaction: Any) -> None:
        snapshot = usage_ref.get(transaction=write_transaction)
        existing_raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else {}
        existing = existing_raw if isinstance(existing_raw, dict) else {}
        payload: Dict[str, Any] = {
            'date': clean_date,
            'timezone': timezone_name,
            'client_device_id': clean_dev,
            'updated_at': datetime.now(timezone.utc),
        }
        safe_counters = counters if isinstance(counters, dict) else {}
        for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
            previous = existing.get(field, 0)
            previous_value = previous if isinstance(previous, int) and not isinstance(previous, bool) and previous >= 0 else 0
            incoming = safe_counters.get(field, 0)
            incoming_value = incoming if isinstance(incoming, int) and not isinstance(incoming, bool) and incoming >= 0 else 0
            payload[field] = max(previous_value, incoming_value)
        write_transaction.set(usage_ref, payload)

    merge_running_totals(transaction)


def get_desktop_daily_usage(uid: str, date: str) -> Dict[str, int]:
    """Sum every device's counters for one local calendar date.

    A date with no usage documents returns every counter as zero.
    """
    if not isinstance(uid, str) or not uid.strip() or not isinstance(date, str) or not date.strip():
        return {field: 0 for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS}

    user_ref = db.collection('users').document(uid.strip())
    query = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).where(filter=FieldFilter('date', '==', date.strip()))
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
    clean_uid = _validate_identifier('uid', uid)
    if not isinstance(summary_data, dict):
        raise ValueError("summary_data must be a dict")
    summary_id = summary_data.get('id')
    if not isinstance(summary_id, str) or not summary_id.strip():
        raise ValueError("summary_data must contain a non-empty 'id'")
    clean_id = summary_id.strip()

    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_id)
    summary_ref.set(summary_data)
    return clean_id


def get_daily_summary(uid: str, summary_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single daily summary by ID.

    Args:
        uid: User ID
        summary_id: Summary document ID

    Returns:
        Summary data dict or None if not found
    """
    if not isinstance(uid, str) or not uid.strip() or not isinstance(summary_id, str) or not summary_id.strip():
        return None

    user_ref = db.collection('users').document(uid.strip())
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id.strip())
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
    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION)

    if start_date:
        query = query.where(filter=FieldFilter('date', '>=', start_date))
    if end_date:
        query = query.where(filter=FieldFilter('date', '<=', end_date))

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
    user_ref = db.collection('users').document(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    summary_ref.delete()
    redis_db.remove_daily_summary_to_uid(summary_id)
    return True


def set_daily_summary_visibility(uid: str, summary_id: str, visibility: str) -> None:
    user_ref = db.collection('users').document(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    summary_ref.update({'visibility': visibility})


def get_summaries_count(uid: str) -> int:
    """
    Get total count of daily summaries for a user.

    Args:
        uid: User ID

    Returns:
        Count of summaries
    """
    user_ref = db.collection('users').document(uid)
    count_query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).count()
    result = count_query.get()
    return int(result[0][0].value or 0)
