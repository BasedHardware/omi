from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import transactional  # type: ignore[reportUnknownMemberType]  # firestore SDK stub gap

from ._client import db
from database.document_ids import calendar_meeting_doc_id

T = TypeVar("T")


def _clean_uid(uid: Any) -> str:
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError("uid must be a non-empty string")
    return uid.strip()


def _clean_id(val: Any, name: str = "identifier") -> str:
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return val.strip()


def _typed_transactional(func: Callable[..., T]) -> Callable[..., T]:
    """Wrap @transactional preserving the wrapped function's typed signature.

    google-cloud-firestore's @transactional decorator surfaces as partially
    unknown under strict Pyright (no stubs); this thin wrapper keeps the typed
    call site while delegating runtime behavior to the SDK decorator.
    """
    return transactional(func)


def _get_meetings_collection(uid: str) -> Any:
    """Get user's meetings collection reference"""
    clean_uid = _clean_uid(uid)
    return db.collection("users").document(clean_uid).collection("meetings")


@_typed_transactional
def _upsert_meeting_transaction(transaction: Any, doc_ref: Any, meeting_data: Dict[str, Any], now: datetime) -> None:
    """Upsert a natural-key meeting while preserving first-created metadata."""
    snapshot = doc_ref.get(transaction=transaction)
    payload: Dict[str, Any] = dict(meeting_data)
    payload["synced_at"] = now
    if not getattr(snapshot, "exists", False):
        payload["created_at"] = now
    transaction.set(doc_ref, payload, merge=True)


def create_meeting(uid: str, meeting_data: Any) -> str:
    """
    Create or idempotently upsert a calendar meeting in Firestore.
    Returns the deterministic Firestore document ID.

    NOTE: Times should already be in UTC before calling this function.
    """
    clean_uid = _clean_uid(uid)
    if not isinstance(meeting_data, dict):
        raise ValueError("meeting_data must be a dictionary")
    calendar_source = _clean_id(meeting_data.get("calendar_source"), "calendar_source")
    calendar_event_id = _clean_id(meeting_data.get("calendar_event_id"), "calendar_event_id")

    meeting_id = calendar_meeting_doc_id(clean_uid, calendar_source, calendar_event_id)
    doc_ref = _get_meetings_collection(clean_uid).document(meeting_id)
    transaction = db.transaction()
    _upsert_meeting_transaction(transaction, doc_ref, meeting_data, datetime.now(timezone.utc))
    return meeting_id


def update_meeting(uid: str, meeting_id: str, meeting_data: Any) -> None:
    """
    Update an existing calendar meeting.

    NOTE: Times should already be in UTC before calling this function.
    """
    clean_uid = _clean_uid(uid)
    clean_meeting_id = _clean_id(meeting_id, "meeting_id")
    if not isinstance(meeting_data, dict):
        raise ValueError("meeting_data must be a dictionary")
    if not meeting_data:
        return

    # Update synced_at timestamp (always in UTC for consistent querying)
    payload = dict(meeting_data)
    payload["synced_at"] = datetime.now(timezone.utc)

    # Update document
    _get_meetings_collection(clean_uid).document(clean_meeting_id).update(payload)


def get_meeting(uid: str, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Get a calendar meeting by its Firestore document ID"""
    clean_uid = _clean_uid(uid)
    clean_meeting_id = _clean_id(meeting_id, "meeting_id")
    doc = _get_meetings_collection(clean_uid).document(clean_meeting_id).get()

    if not getattr(doc, "exists", False):
        return None

    raw: object = doc.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    data["id"] = doc.id
    return data


def get_meeting_id_by_calendar_event(uid: str, calendar_event_id: str, calendar_source: str) -> Optional[str]:
    """
    Find a meeting by its external calendar event ID and source.
    Returns the Firestore document ID if found, None otherwise.
    """
    clean_uid = _clean_uid(uid)
    clean_eid = _clean_id(calendar_event_id, "calendar_event_id")
    clean_src = _clean_id(calendar_source, "calendar_source")

    query = (
        _get_meetings_collection(clean_uid)
        .where("calendar_event_id", "==", clean_eid)
        .where("calendar_source", "==", clean_src)
        .limit(1)
    )

    docs = list(query.stream())
    if docs:
        return str(docs[0].id)

    return None


def _to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def list_meetings(
    uid: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """List calendar meetings, optionally filtered by date range, sorted by start_time descending."""
    clean_uid = _clean_uid(uid)
    if limit <= 0:
        return []
    clamped_limit = min(limit, 500)

    if start_date is not None and not isinstance(cast(object, start_date), datetime):
        raise ValueError("start_date must be a datetime")
    if end_date is not None and not isinstance(cast(object, end_date), datetime):
        raise ValueError("end_date must be a datetime")

    query: Any = _get_meetings_collection(clean_uid)
    if start_date:
        query = query.where("start_time", ">=", _to_utc(start_date))
    if end_date:
        query = query.where("start_time", "<=", _to_utc(end_date))
    query = query.order_by("start_time", direction=firestore.Query.DESCENDING).limit(clamped_limit)

    meetings: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data["id"] = doc.id
        meetings.append(data)

    return meetings


def delete_meeting(uid: str, meeting_id: str) -> None:
    """Delete a calendar meeting"""
    clean_uid = _clean_uid(uid)
    clean_meeting_id = _clean_id(meeting_id, "meeting_id")
    _get_meetings_collection(clean_uid).document(clean_meeting_id).delete()


def delete_old_meetings(uid: str, before_date: datetime) -> int:
    """Delete meetings that ended before a certain date. Returns the number of meetings deleted."""
    clean_uid = _clean_uid(uid)
    if not isinstance(cast(object, before_date), datetime):
        raise ValueError("before_date must be a datetime")

    query = _get_meetings_collection(clean_uid).where("end_time", "<", _to_utc(before_date))

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
    clean_uid = _clean_uid(uid)
    if not isinstance(cast(object, start_time), datetime):
        raise ValueError("start_time must be a datetime")
    if not isinstance(cast(object, end_time), datetime):
        raise ValueError("end_time must be a datetime")

    query = (
        _get_meetings_collection(clean_uid)
        .where("start_time", "<", _to_utc(end_time))
        .where("end_time", ">", _to_utc(start_time))
        .order_by("start_time", direction=firestore.Query.ASCENDING)
        .limit(10)
    )

    meetings: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data["id"] = doc.id
        meetings.append(data)

    return meetings
