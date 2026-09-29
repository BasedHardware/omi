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

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from . import redis_db
from ._client import db

logger = logging.getLogger(__name__)

DAILY_SUMMARIES_COLLECTION = 'daily_summaries'
DESKTOP_DAILY_USAGE_COLLECTION = 'desktop_daily_usage'
DESKTOP_DAILY_USAGE_COUNTER_FIELDS = (
    'watching_seconds',
    'listening_seconds',
    'proactive_cards_shown',
    'proactive_cards_acted',
    'ptt_turns',
)


def _clean_str(val: Any) -> Optional[str]:
    if not isinstance(val, str):
        return None
    s = val.strip()
    return s if s else None


def _clean_id(val: Any) -> Optional[str]:
    s = _clean_str(val)
    if not s or '/' in s:
        return None
    return s


def upsert_desktop_daily_usage(
    uid: str,
    date: str,
    timezone_name: str,
    client_device_id: str,
    counters: Dict[str, int],
) -> None:
    """Atomically merge one device's running daily counters by maximum value."""
    clean_uid = _clean_id(uid)
    clean_date = _clean_str(date)
    clean_device_id = _clean_id(client_device_id)
    if not clean_uid or not clean_date or not clean_device_id:
        raise ValueError('uid, date, and client_device_id must be valid non-empty identifiers')

    user_ref = db.collection('users').document(clean_uid)
    doc_id = f'{clean_date}__{clean_device_id}'
    usage_ref = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).document(doc_id)

    @firestore.transactional
    def merge_running_totals(write_transaction: Any) -> None:
        snapshot = usage_ref.get(transaction=write_transaction)
        existing_raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else {}
        existing = existing_raw if isinstance(existing_raw, dict) else {}
        payload: Dict[str, Any] = {
            'date': clean_date,
            'timezone': _clean_str(timezone_name) or 'UTC',
            'client_device_id': clean_device_id,
            'updated_at': datetime.now(timezone.utc),
        }
        for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
            previous = existing.get(field, 0)
            previous_value = (
                previous if isinstance(previous, int) and not isinstance(previous, bool) and previous >= 0 else 0
            )
            raw_counters: Any = counters
            raw_curr: Any = raw_counters.get(field, 0) if isinstance(raw_counters, dict) else 0
            curr_value = (
                raw_curr if isinstance(raw_curr, int) and not isinstance(raw_curr, bool) and raw_curr >= 0 else 0
            )
            payload[field] = max(previous_value, curr_value)
        write_transaction.set(usage_ref, payload)

    run_with_transaction_contention_retry(
        db.transaction, merge_running_totals, operation_name='upsert_desktop_daily_usage'
    )


def get_desktop_daily_usage(uid: str, date: str) -> Dict[str, int]:
    """Sum every device's counters for one local calendar date.

    A date with no usage documents returns every counter as zero.
    """
    clean_uid = _clean_id(uid)
    clean_date = _clean_str(date)
    totals = {field: 0 for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS}
    if not clean_uid or not clean_date:
        return totals

    user_ref = db.collection('users').document(clean_uid)
    query = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).where(filter=FieldFilter('date', '==', clean_date))
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
    clean_uid = _clean_id(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    raw_data: Any = summary_data
    if not isinstance(raw_data, dict):
        raise ValueError("summary_data must be a dictionary")

    payload: Dict[str, Any] = dict(summary_data)
    summary_id = _clean_id(payload.get('id'))
    if not summary_id:
        summary_id = str(uuid.uuid4())
        payload['id'] = summary_id

    now = datetime.now(timezone.utc)
    payload.setdefault('created_at', now)

    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
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
    clean_uid = _clean_id(uid)
    clean_summary_id = _clean_id(summary_id)
    if not clean_uid or not clean_summary_id:
        return None

    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    doc = summary_ref.get()

    if getattr(doc, "exists", False):
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            res = cast(Dict[str, Any], raw)
            res.setdefault('id', doc.id)
            return res
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
    clean_uid = _clean_id(uid)
    clean_date = _clean_str(date)
    if not clean_uid or not clean_date:
        return None

    user_ref = db.collection('users').document(clean_uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).where(filter=FieldFilter('date', '==', clean_date)).limit(1)

    docs = list(query.stream())
    if docs:
        raw: object = docs[0].to_dict()
        if isinstance(raw, dict):
            res = cast(Dict[str, Any], raw)
            res.setdefault('id', docs[0].id)
            return res
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
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return []

    raw_limit: Any = limit
    raw_offset: Any = offset
    bounded_limit = max(
        1, min(raw_limit if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) else 30, 500)
    )
    bounded_offset = max(0, raw_offset if isinstance(raw_offset, int) and not isinstance(raw_offset, bool) else 0)

    user_ref = db.collection('users').document(clean_uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION)

    clean_start = _clean_str(start_date)
    clean_end = _clean_str(end_date)
    if clean_start:
        query = query.where(filter=FieldFilter('date', '>=', clean_start))
    if clean_end:
        query = query.where(filter=FieldFilter('date', '<=', clean_end))

    query = query.order_by('date', direction=firestore.Query.DESCENDING)
    query = query.limit(bounded_limit).offset(bounded_offset)

    summaries: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            res = cast(Dict[str, Any], raw)
            res.setdefault('id', doc.id)
            summaries.append(res)
    return summaries


def update_daily_summary(uid: str, summary_id: str, summary_data: Dict[str, Any]) -> bool:
    """
    Overwrite an existing daily summary in place, preserving the original id.

    Used by the regenerate flow so that re-running generation replaces the
    contents of the summary the user is looking at instead of spawning a
    duplicate doc for the same date.
    """
    clean_uid = _clean_id(uid)
    clean_summary_id = _clean_id(summary_id)
    raw_data: Any = summary_data
    if not clean_uid or not clean_summary_id or not isinstance(raw_data, dict):
        return False

    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    payload: Dict[str, Any] = {**summary_data, 'id': clean_summary_id}
    summary_ref.set(payload)
    return True


def delete_daily_summary(uid: str, summary_id: str) -> bool:
    """
    Delete a daily summary.

    Args:
        uid: User ID
        summary_id: Summary document ID

    Returns:
        True if deleted successfully
    """
    clean_uid = _clean_id(uid)
    clean_summary_id = _clean_id(summary_id)
    if not clean_uid or not clean_summary_id:
        return False

    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    summary_ref.delete()
    try:
        redis_db.remove_daily_summary_to_uid(clean_summary_id)
    except Exception as exc:
        logger.warning(f"remove_daily_summary_to_uid failed for id={clean_summary_id}: {exc}")
    return True


def set_daily_summary_visibility(uid: str, summary_id: str, visibility: str) -> None:
    """Update visibility ('public' or 'private') for a daily summary."""
    clean_uid = _clean_id(uid)
    clean_summary_id = _clean_id(summary_id)
    clean_visibility = _clean_str(visibility)
    if not clean_uid or not clean_summary_id or not clean_visibility:
        raise ValueError('uid, summary_id, and visibility must be valid non-empty identifiers')

    user_ref = db.collection('users').document(clean_uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    summary_ref.update({'visibility': clean_visibility})


def get_summaries_count(uid: str) -> int:
    """
    Get total count of daily summaries for a user.

    Args:
        uid: User ID

    Returns:
        Count of summaries
    """
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return 0

    user_ref = db.collection('users').document(clean_uid)
    count_query = user_ref.collection(DAILY_SUMMARIES_COLLECTION).count()
    result = count_query.get()
    return int(result[0][0].value or 0)
