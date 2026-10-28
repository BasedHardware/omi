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
    ├── overall_sentiment: str
    └── notification_delivery_completed: bool (push handling acknowledged, including tokenless skip)

users/{uid}/desktop_daily_usage/{date}__{client_device_id}
    ├── date/timezone/client_device_id
    ├── watching_seconds/listening_seconds
    ├── proactive_cards_shown/proactive_cards_acted/ptt_turns
    └── updated_at
"""

from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Any, Callable, Dict, List, Optional, cast

from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore
from google.api_core.exceptions import FailedPrecondition
from utils.observability.fallback import record_fallback
from utils.other.list_budget import ListReadBudget, budgeted_stream_iter
from database.firestore_index_registry import MCP_DAILY_RECORDINGS_QUERY
import logging
from ._client import db, get_firestore_client
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
    uid: object,
    date: str,
    timezone_name: str,
    client_device_id: str,
    counters: Mapping[str, object],
) -> None:
    """Atomically merge one device's running daily counters by maximum value."""
    # An empty uid/date/client_device_id makes a malformed doc path/id; the
    # counters dict may legitimately omit a counter field. Reject the path
    # inputs and read each counter with a default so neither crashes.
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError('uid must be a non-empty string')
    if not date or not client_device_id:
        raise ValueError('date and client_device_id are required')
    counters = counters or {}
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
            current = counters.get(field, 0)
            current_value = current if isinstance(current, int) and not isinstance(current, bool) else 0
            payload[field] = max(previous_value, current_value)
        write_transaction.set(usage_ref, payload)

    merge_running_totals(transaction)


def get_desktop_daily_usage(uid: str, date: str) -> Dict[str, int]:
    """Sum every device's counters for one local calendar date.

    A date with no usage documents returns every counter as zero.
    """
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
    user_ref = db.collection('users').document(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(summary_data['id'])
    summary_ref.set(summary_data)
    return summary_data['id']


def get_daily_summary(uid: str, summary_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single daily summary by ID.

    Args:
        uid: User ID
        summary_id: Summary document ID

    Returns:
        Summary data dict or None if not found
    """
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
    *,
    record_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
    read_budget: Optional[ListReadBudget] = None,
) -> List[Dict[str, Any]]:
    """
    Get list of daily summaries for a user, ordered by date descending.

    Args:
        uid: User ID
        limit: Maximum number of summaries to return
        offset: Number of summaries to skip
        start_date: Filter summaries from this date (YYYY-MM-DD)
        end_date: Filter summaries until this date (YYYY-MM-DD)
        record_filter: Optional response predicate, applied before the returned-row offset/limit.
        read_budget: Bounds the filtered scan's time and total documents, including skipped rows.

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
    if record_filter is None:
        query = query.limit(limit).offset(offset)

    summaries: List[Dict[str, Any]] = []
    stream = budgeted_stream_iter(query, read_budget)
    skipped = 0
    try:
        for doc in stream:
            raw: object = doc.to_dict()
            if not isinstance(raw, dict):
                continue
            row = cast(Dict[str, Any], raw)
            if record_filter is not None:
                if not record_filter(row):
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
            summaries.append(row)
            if len(summaries) >= limit:
                break
    finally:
        # The filtered projection stops its one ordered stream as soon as the page is full;
        # it does not reissue growing offset queries or retain skipped documents in memory.
        close = getattr(stream, 'close', None)
        if close is not None:
            close()
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


def mark_daily_summary_delivery_completed(uid: str, summary_id: str, *, firestore_client: Any = None) -> None:
    """Record completed push handling independently of backfill/webhook work.

    Patch only delivery metadata, preserving concurrent edits to the recap.
    A tokenless recap also completes push handling without sending anything.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    summary_ref = client.collection('users').document(uid).collection(DAILY_SUMMARIES_COLLECTION).document(summary_id)
    summary_ref.update({'notification_delivery_completed': True})


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


def get_day_recording_count(uid: str, start: datetime, end: datetime, *, firestore_client: Any = None) -> int:
    """Aggregate all non-discarded recordings by started_at, independent of list caps."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection('conversations')
    query = MCP_DAILY_RECORDINGS_QUERY.build(
        collection, {'start': start, 'end': end, 'discarded': False}, field_filter_factory=FieldFilter
    )
    try:
        return int(query.count().get()[0][0].value or 0)
    except FailedPrecondition:
        record_fallback(
            component='daily_summary',
            from_mode='indexed',
            to_mode='scan',
            reason='other',
            outcome='degraded',
            log=logging.getLogger(__name__),
        )
        # Single-field fallback works during index rollout. Never turn a capped
        # scan into a count: fail explicitly if this fallback cannot finish.
        snapshots = list(
            collection.where(filter=FieldFilter('started_at', '>=', start))
            .where(filter=FieldFilter('started_at', '<=', end))
            .select(['discarded'])
            .limit(10001)
            .stream()
        )
        if len(snapshots) > 10000:
            raise RuntimeError('daily_recording_count_incomplete: required index is not ready')
        return sum(1 for snapshot in snapshots if (snapshot.to_dict() or {}).get('discarded') is False)


def get_daily_summary_generation_status(uid: str, date: str, *, firestore_client: Any = None) -> Optional[dict]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = client.collection('users').document(uid).collection('daily_summary_generation').document(date).get()
    return snapshot.to_dict() if snapshot.exists else None


def set_daily_summary_generation_status(uid: str, date: str, status: str, *, firestore_client: Any = None) -> None:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    client.collection('users').document(uid).collection('daily_summary_generation').document(date).set(
        {'status': status, 'updated_at': datetime.now(timezone.utc), 'generated_at': None}
    )
