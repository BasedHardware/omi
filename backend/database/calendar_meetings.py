from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import transactional  # type: ignore[reportUnknownMemberType]  # firestore SDK stub gap

from ._client import db
from database.document_ids import calendar_meeting_doc_id

T = TypeVar("T")


def _typed_transactional(func: Callable[..., T]) -> Callable[..., T]:
    """Wrap @transactional preserving the wrapped function's typed signature.

    google-cloud-firestore's @transactional decorator surfaces as partially
    unknown under strict Pyright (no stubs); this thin wrapper keeps the typed
    call site while delegating runtime behavior to the SDK decorator.
    """
    return transactional(func)


def _get_meetings_collection(uid: str) -> Any:
    """Get user's meetings collection reference"""
    return db.collection('users').document(uid).collection('meetings')


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
    meeting_id = calendar_meeting_doc_id(uid, meeting_data['calendar_source'], meeting_data['calendar_event_id'])
    doc_ref = _get_meetings_collection(uid).document(meeting_id)
    transaction = db.transaction()
    _upsert_meeting_transaction(transaction, doc_ref, meeting_data, datetime.now(timezone.utc))
    return meeting_id


def update_meeting(uid: str, meeting_id: str, meeting_data: Dict[str, Any]) -> None:
    """
    Update an existing calendar meeting.

    NOTE: Times should already be in UTC before calling this function.
    """
    # Update synced_at timestamp (always in UTC for consistent querying)
    meeting_data['synced_at'] = datetime.now(timezone.utc)

    # Update document
    _get_meetings_collection(uid).document(meeting_id).update(meeting_data)


def get_meeting(uid: str, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Get a calendar meeting by its Firestore document ID"""
    doc = _get_meetings_collection(uid).document(meeting_id).get()

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
    query = (
        _get_meetings_collection(uid)
        .where('calendar_event_id', '==', calendar_event_id)
        .where('calendar_source', '==', calendar_source)
        .limit(1)
    )

    docs = list(query.stream())
    if docs:
        return str(docs[0].id)

    return None


def list_meetings(
    uid: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """
    List calendar meetings, optionally filtered by date range.
    Returns meetings sorted by start_time descending.
    """
    query = _get_meetings_collection(uid).order_by('start_time', direction=firestore.Query.DESCENDING).limit(limit)

    if start_date:
        query = query.where('start_time', '>=', start_date)

    if end_date:
        query = query.where('start_time', '<=', end_date)

    meetings: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        meetings.append(data)

    return meetings


def delete_meeting(uid: str, meeting_id: str) -> None:
    """Delete a calendar meeting"""
    _get_meetings_collection(uid).document(meeting_id).delete()


def delete_old_meetings(uid: str, before_date: datetime) -> int:
    """
    Delete meetings that ended before a certain date.
    Returns the number of meetings deleted.
    """
    query = _get_meetings_collection(uid).where('end_time', '<', before_date)

    deleted_count = 0
    batch = db.batch()
    batch_size = 0

    for doc in query.stream():
        batch.delete(doc.reference)
        batch_size += 1
        deleted_count += 1

        # Commit in batches of 500 (Firestore limit)
        if batch_size >= 500:
            batch.commit()
            batch = db.batch()
            batch_size = 0

    # Commit remaining
    if batch_size > 0:
        batch.commit()

    return deleted_count


def get_meetings_in_time_range(uid: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """
    Find meetings that overlap with the given time range.
    A meeting overlaps if: meeting.start_time < range.end_time AND meeting.end_time > range.start_time

    Note: This requires a composite index on (start_time, end_time).
    Returns meetings sorted by start_time ascending.
    """
    # Query for meetings where:
    # - meeting starts before the range ends (start_time < end_time)
    # - meeting ends after the range starts (end_time > start_time)
    # This captures all overlapping meetings
    query = (
        _get_meetings_collection(uid)
        .where('start_time', '<', end_time)
        .where('end_time', '>', start_time)
        .order_by('start_time', direction=firestore.Query.ASCENDING)
        .limit(10)  # Cap to prevent excessive results
    )

    meetings: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        meetings.append(data)

    return meetings
