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

import re
from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, cast

from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore
from google.api_core.exceptions import FailedPrecondition
from utils.observability.fallback import record_fallback
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

_MAX_ID_LENGTH = 256
_UNSAFE_ID_CHARS = ('/', '\\', ':')
_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_MIN_PAGE_LIMIT = 1
_MAX_PAGE_LIMIT = 100


def _clean_uid(uid: Any) -> str:
    """Validate a user id before it is used as a `users/{uid}` path segment.

    An empty or separator-bearing uid previously produced malformed collection
    paths (e.g. `users//daily_summaries/...`), silently writing orphaned
    documents that no reader could ever resolve.
    """
    if not isinstance(uid, str):
        raise ValueError('uid must be a non-empty string')
    cleaned = uid.strip()
    if not cleaned or len(cleaned) > _MAX_ID_LENGTH:
        raise ValueError('uid must be a non-empty, bounded string')
    if any(char in cleaned for char in _UNSAFE_ID_CHARS):
        raise ValueError('uid must not contain path separators')
    return cleaned


def _clean_id(value: Any, field: str = 'id') -> str:
    """Validate a document id (summary id / client device id) path segment."""
    if not isinstance(value, str):
        raise ValueError(f'{field} must be a non-empty string')
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_ID_LENGTH:
        raise ValueError(f'{field} must be a non-empty, bounded string')
    if cleaned in ('.', '..'):
        raise ValueError(f'{field} must not be a relative path segment')
    if any(char in cleaned for char in _UNSAFE_ID_CHARS):
        raise ValueError(f'{field} must not contain path separators')
    return cleaned


def _clean_date(value: Any, field: str = 'date') -> str:
    """Validate a `YYYY-MM-DD` date string before it is used in a query or id."""
    if not isinstance(value, str) or not _DATE_PATTERN.match(value.strip()):
        raise ValueError(f'{field} must be a YYYY-MM-DD string')
    return value.strip()


def _safe_counter(value: Any) -> int:
    """Coerce a stored/client counter to a non-negative int, else 0."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _as_page_int(value: Any, default: int) -> int:
    """Return ``value`` when it is a real int, else ``default``.

    ``bool`` is rejected explicitly because ``isinstance(True, int)`` is true and
    a boolean limit/offset is a caller bug, not a page window.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _require_summary_data(value: Any, field: str = 'summary_data') -> Dict[str, Any]:
    """Validate the untrusted summary payload before it reaches Firestore."""
    if not isinstance(value, dict):
        raise ValueError(f'{field} must be a dict')
    return value


def _user_ref(uid: Any) -> Any:
    """Validate ``uid`` *before* touching the client, then return its document ref.

    Ordering matters: validating inline as a call argument still builds
    ``users`` collection objects for a uid that is about to be rejected.
    """
    clean_uid = _clean_uid(uid)
    return db.collection('users').document(clean_uid)


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
    clean_uid = _clean_uid(uid)
    clean_date = _clean_date(date)
    clean_device = _clean_id(client_device_id, 'client_device_id')
    counters = counters or {}
    user_ref = db.collection('users').document(clean_uid)
    usage_ref = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).document(f'{clean_date}__{clean_device}')
    transaction = db.transaction()

    @firestore.transactional
    def merge_running_totals(write_transaction: Any) -> None:
        snapshot = usage_ref.get(transaction=write_transaction)
        existing_raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else {}
        existing = existing_raw if isinstance(existing_raw, dict) else {}
        payload: Dict[str, Any] = {
            'date': clean_date,
            'timezone': timezone_name,
            'client_device_id': clean_device,
            'updated_at': datetime.now(timezone.utc),
        }
        for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
            # Partial counter sets are legal: a missing or malformed field
            # contributes 0 instead of raising KeyError/TypeError mid-write.
            payload[field] = max(_safe_counter(existing.get(field)), _safe_counter(counters.get(field)))
        write_transaction.set(usage_ref, payload)

    merge_running_totals(transaction)


def get_desktop_daily_usage(uid: str, date: str) -> Dict[str, int]:
    """Sum every device's counters for one local calendar date.

    A date with no usage documents returns every counter as zero.
    """
    user_ref = _user_ref(uid)
    query = user_ref.collection(DESKTOP_DAILY_USAGE_COLLECTION).where(
        filter=FieldFilter('date', '==', _clean_date(date))
    )
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
    payload = _require_summary_data(summary_data)
    summary_id = _clean_id(payload.get('id'), 'id')
    user_ref = _user_ref(uid)
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
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    user_ref = _user_ref(uid)
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
    user_ref = _user_ref(uid)
    query = (
        user_ref.collection(DAILY_SUMMARIES_COLLECTION)
        .where(filter=FieldFilter('date', '==', _clean_date(date)))
        .limit(1)
    )

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
    # Clamp the page window: Firestore rejects negative offsets and a huge
    # limit is both an invalid query and an unbounded read.
    page_limit = max(_MIN_PAGE_LIMIT, min(_MAX_PAGE_LIMIT, _as_page_int(limit, 30)))
    page_offset = max(0, _as_page_int(offset, 0))

    user_ref = _user_ref(uid)
    query = user_ref.collection(DAILY_SUMMARIES_COLLECTION)

    if start_date:
        query = query.where(filter=FieldFilter('date', '>=', _clean_date(start_date, 'start_date')))
    if end_date:
        query = query.where(filter=FieldFilter('date', '<=', _clean_date(end_date, 'end_date')))

    query = query.order_by('date', direction=firestore.Query.DESCENDING)
    query = query.limit(page_limit).offset(page_offset)

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
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    payload = _require_summary_data(summary_data)
    user_ref = _user_ref(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    # Force id back to the existing doc id: the generator always allocates a
    # fresh UUID, and we don't want that leaking into the stored payload
    # where readers key off summary['id'].
    stored: Dict[str, Any] = {**payload, 'id': clean_summary_id}
    summary_ref.set(stored)


def mark_daily_summary_delivery_completed(uid: str, summary_id: str, *, firestore_client: Any = None) -> None:
    """Record completed push handling independently of backfill/webhook work.

    Patch only delivery metadata, preserving concurrent edits to the recap.
    A tokenless recap also completes push handling without sending anything.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    clean_uid = _clean_uid(uid)
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    summary_ref = (
        client.collection('users').document(clean_uid).collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    )
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
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    user_ref = _user_ref(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    summary_ref.delete()
    redis_db.remove_daily_summary_to_uid(clean_summary_id)
    return True


def set_daily_summary_visibility(uid: str, summary_id: str, visibility: str) -> None:
    clean_summary_id = _clean_id(summary_id, 'summary_id')
    user_ref = _user_ref(uid)
    summary_ref = user_ref.collection(DAILY_SUMMARIES_COLLECTION).document(clean_summary_id)
    summary_ref.update({'visibility': visibility})


def get_summaries_count(uid: str) -> int:
    """
    Get total count of daily summaries for a user.

    Args:
        uid: User ID

    Returns:
        Count of summaries
    """
    user_ref = _user_ref(uid)
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
