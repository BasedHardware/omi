import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from google.api_core.exceptions import NotFound
from google.cloud import firestore
from google.cloud.firestore_v1 import transactional  # type: ignore[reportUnknownMemberType]  # firestore SDK stub gap

from ._client import db
from database.document_ids import calendar_meeting_doc_id
from database.firestore_transaction_retry import run_with_transaction_contention_retry

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _clean_str(value: Any) -> str:
    return str(value).strip() if value is not None and not isinstance(value, bool) else ""


def _clean_id(value: Any) -> str:
    s = _clean_str(value)
    if not s or "/" in s or "\\" in s or s in (".", ".."):
        return ""
    return s


def _typed_transactional(func: Callable[..., T]) -> Callable[..., T]:
    """Wrap @transactional preserving the wrapped function's typed signature.

    google-cloud-firestore's @transactional decorator surfaces as partially
    unknown under strict Pyright (no stubs); this thin wrapper keeps the typed
    call site while delegating runtime behavior to the SDK decorator.
    """
    return transactional(func)


def _get_meetings_collection(uid: str) -> Any:
    """Get user's meetings collection reference"""
    clean_uid = _clean_id(uid)
    return db.collection('users').document(clean_uid).collection('meetings')


@_typed_transactional
def _upsert_meeting_transaction(transaction: Any, doc_ref: Any, meeting_data: Dict[str, Any], now: datetime) -> None:
    """Upsert a natural-key meeting while preserving first-created metadata."""
    snapshot = doc_ref.get(transaction=transaction)
    payload: Dict[str, Any] = dict(meeting_data)
    payload['synced_at'] = now
    if not getattr(snapshot, "exists", False):
        payload['created_at'] = now
    transaction.set(doc_ref, payload, merge=True)


def create_meeting(uid: str, meeting_data: Dict[str, Any]) -> str:
    """
    Create or idempotently upsert a calendar meeting in Firestore.
    Returns the deterministic Firestore document ID.

    NOTE: Times should already be in UTC before calling this function.
    """
    clean_uid = _clean_id(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    raw_data: Any = meeting_data
    if not isinstance(raw_data, dict):
        raise ValueError("meeting_data must be a dictionary")

    raw_source = meeting_data.get('calendar_source')
    raw_event_id = meeting_data.get('calendar_event_id')
    clean_source = _clean_str(raw_source) or 'unknown_source'
    clean_event_id = _clean_str(raw_event_id) or str(uuid.uuid4())

    meeting_id = calendar_meeting_doc_id(clean_uid, clean_source, clean_event_id)
    doc_ref = _get_meetings_collection(clean_uid).document(meeting_id)
    now = datetime.now(timezone.utc)

    def run_transaction(transaction: Any) -> None:
        _upsert_meeting_transaction(transaction, doc_ref, meeting_data, now)

    run_with_transaction_contention_retry(
        db.transaction,
        run_transaction,
        operation_name='create_calendar_meeting',
    )
    return meeting_id


def update_meeting(uid: str, meeting_id: str, meeting_data: Dict[str, Any]) -> None:
    """
    Update an existing calendar meeting.

    NOTE: Times should already be in UTC before calling this function.
    """
    clean_uid = _clean_id(uid)
    clean_meeting_id = _clean_id(meeting_id)
    raw_data: Any = meeting_data
    if not clean_uid or not clean_meeting_id or not isinstance(raw_data, dict):
        return

    payload: Dict[str, Any] = dict(meeting_data)
    payload['synced_at'] = datetime.now(timezone.utc)
    try:
        _get_meetings_collection(clean_uid).document(clean_meeting_id).update(payload)
    except NotFound:
        pass
    except Exception as exc:
        logger.warning(f"update_meeting failed for uid={clean_uid} meeting_id={clean_meeting_id}: {exc}")


def get_meeting(uid: str, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Get a calendar meeting by its Firestore document ID"""
    clean_uid = _clean_id(uid)
    clean_meeting_id = _clean_id(meeting_id)
    if not clean_uid or not clean_meeting_id:
        return None

    doc = _get_meetings_collection(clean_uid).document(clean_meeting_id).get()
    if not getattr(doc, "exists", False):
        return None

    raw: object = doc.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    data['id'] = doc.id
    return data


def get_meeting_id_by_calendar_event(uid: str, calendar_event_id: str, calendar_source: str) -> Optional[str]:
    """
    Find a meeting by its external calendar event ID and source.
    Returns the Firestore document ID if found, None otherwise.
    """
    clean_uid = _clean_id(uid)
    clean_event_id = _clean_str(calendar_event_id)
    clean_source = _clean_str(calendar_source)
    if not clean_uid or not clean_event_id or not clean_source:
        return None

    query = (
        _get_meetings_collection(clean_uid)
        .where('calendar_event_id', '==', clean_event_id)
        .where('calendar_source', '==', clean_source)
        .limit(1)
    )

    docs = list(query.stream())
    if docs:
        return str(docs[0].id)

    return None


def _to_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def list_meetings(
    uid: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """List calendar meetings, optionally filtered by date range, sorted by start_time descending."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return []

    raw_limit: Any = limit
    bounded_limit = max(
        1, min(raw_limit if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) else 50, 500)
    )

    query: Any = _get_meetings_collection(clean_uid)
    if start_date:
        query = query.where('start_time', '>=', _to_utc(start_date))
    if end_date:
        query = query.where('start_time', '<=', _to_utc(end_date))
    query = query.order_by('start_time', direction=firestore.Query.DESCENDING).limit(bounded_limit)

    meetings: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        meetings.append(data)

    return meetings


def delete_meeting(uid: str, meeting_id: str) -> None:
    """Delete a calendar meeting"""
    clean_uid = _clean_id(uid)
    clean_meeting_id = _clean_id(meeting_id)
    if not clean_uid or not clean_meeting_id:
        return
    try:
        _get_meetings_collection(clean_uid).document(clean_meeting_id).delete()
    except NotFound:
        pass


def delete_old_meetings(uid: str, before_date: datetime) -> int:
    """Delete meetings that ended before a certain date. Returns the number of meetings deleted."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return 0

    before_utc = _to_utc(before_date)
    query = _get_meetings_collection(clean_uid).where('end_time', '<', before_utc)

    deleted_count = 0
    batch = db.batch()
    batch_size = 0

    for doc in query.stream():
        batch.delete(doc.reference)
        batch_size += 1
        deleted_count += 1
        if batch_size >= 500:
            batch.commit()
            batch = db.batch()
            batch_size = 0

    if batch_size > 0:
        batch.commit()

    return deleted_count


def get_meetings_in_time_range(uid: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Find meetings that overlap with the given time range, sorted by start_time ascending."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return []

    start_utc = _to_utc(start_time)
    end_utc = _to_utc(end_time)
    if start_utc >= end_utc:
        return []

    query = (
        _get_meetings_collection(clean_uid)
        .where('start_time', '<', end_utc)
        .where('end_time', '>', start_utc)
        .order_by('start_time', direction=firestore.Query.ASCENDING)
        .limit(10)
    )

    meetings: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        meetings.append(data)

    return meetings
