import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from google.api_core import exceptions
from google.cloud import firestore
from google.cloud.firestore_v1 import transactional  # type: ignore[reportUnknownMemberType]  # firestore SDK stub gap

from ._client import db
from database.document_ids import calendar_meeting_doc_id

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _typed_transactional(func: Callable[..., T]) -> Callable[..., T]:
    """Wrap @transactional preserving the wrapped function's typed signature.

    google-cloud-firestore's @transactional decorator surfaces as partially
    unknown under strict Pyright (no stubs); this thin wrapper keeps the typed
    call site while delegating runtime behavior to the SDK decorator.
    """
    return transactional(func)


def _clean_path_id(val: Any, field_name: str) -> str:
    """Validate and normalize document path segments (uid, meeting_id)."""
    if not isinstance(val, str):
        raise ValueError(f"{field_name} must be a string, got {type(val).__name__}")
    cleaned = val.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty or whitespace-only")
    if '/' in cleaned or '\\' in cleaned or '\x00' in cleaned:
        raise ValueError(f"{field_name} cannot contain path separator characters")
    return cleaned


def _clean_identifier(val: Any, field_name: str) -> str:
    """Validate and normalize external identifiers (calendar_event_id, calendar_source).
    
    Does not restrict slashes, as external provider event IDs (e.g. Outlook / Microsoft Graph)
    are frequently base64-derived and legitimately contain slashes.
    """
    if not isinstance(val, str):
        raise ValueError(f"{field_name} must be a string, got {type(val).__name__}")
    cleaned = val.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty or whitespace-only")
    return cleaned


# Backward-compatible alias for path segment cleaning
_clean_id = _clean_path_id


def _get_meetings_collection(uid: str, client: Any | None = None) -> Any:
    """Get user's meetings collection reference"""
    clean_uid = _clean_path_id(uid, "uid")
    firestore_client = client or db
    return firestore_client.collection('users').document(clean_uid).collection('meetings')


@_typed_transactional
def _upsert_meeting_transaction(transaction: Any, doc_ref: Any, meeting_data: Dict[str, Any], now: datetime) -> None:
    """Upsert a natural-key meeting while preserving first-created metadata."""
    snapshot = doc_ref.get(transaction=transaction)
    payload: Dict[str, Any] = dict(meeting_data)
    payload['synced_at'] = now
    if not getattr(snapshot, "exists", False):
        payload['created_at'] = now
    transaction.set(doc_ref, payload, merge=True)


def _resolve_meetings_col(uid: str, client: Any | None = None) -> Any:
    if client is not None:
        return _get_meetings_collection(uid, client)
    return _get_meetings_collection(uid)


def create_meeting(uid: str, meeting_data: Dict[str, Any], db_client: Any | None = None) -> str:
    """
    Create or idempotently upsert a calendar meeting in Firestore.
    Returns the deterministic Firestore document ID.

    NOTE: Times should already be in UTC before calling this function.
    """
    clean_uid = _clean_path_id(uid, "uid")
    if not isinstance(meeting_data, dict):
        raise ValueError("meeting_data must be a dictionary")

    source = meeting_data.get('calendar_source')
    event_id = meeting_data.get('calendar_event_id')
    clean_source = _clean_identifier(source, "calendar_source")
    clean_event_id = _clean_identifier(event_id, "calendar_event_id")

    meeting_id = calendar_meeting_doc_id(clean_uid, clean_source, clean_event_id)
    doc_ref = _resolve_meetings_col(clean_uid, client=db_client).document(meeting_id)
    client = db_client or db
    transaction = client.transaction()
    _upsert_meeting_transaction(transaction, doc_ref, meeting_data, datetime.now(timezone.utc))
    return meeting_id


def update_meeting(
    uid: str, meeting_id: str, meeting_data: Dict[str, Any], db_client: Any | None = None
) -> None:
    """
    Update an existing calendar meeting.

    NOTE: Times should already be in UTC before calling this function.
    """
    clean_uid = _clean_path_id(uid, "uid")
    clean_meeting_id = _clean_path_id(meeting_id, "meeting_id")
    if not isinstance(meeting_data, dict):
        raise ValueError("meeting_data must be a dictionary")

    # Update synced_at timestamp (always in UTC for consistent querying)
    meeting_data['synced_at'] = datetime.now(timezone.utc)

    # Update document with NotFound resilience (upsert on concurrency race)
    doc_ref = _resolve_meetings_col(clean_uid, client=db_client).document(clean_meeting_id)
    try:
        doc_ref.update(meeting_data)
    except exceptions.NotFound:
        logger.warning(
            "Calendar meeting doc %s not found on update for user %s; upserting via merge",
            clean_meeting_id,
            clean_uid,
        )
        doc_ref.set(meeting_data, merge=True)


def get_meeting(uid: str, meeting_id: str, db_client: Any | None = None) -> Optional[Dict[str, Any]]:
    """Get a calendar meeting by its Firestore document ID"""
    clean_uid = _clean_path_id(uid, "uid")
    clean_meeting_id = _clean_path_id(meeting_id, "meeting_id")
    doc = _resolve_meetings_col(clean_uid, client=db_client).document(clean_meeting_id).get()

    if not getattr(doc, "exists", False):
        return None

    raw: object = doc.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    data['id'] = doc.id
    return data


def get_meeting_id_by_calendar_event(
    uid: str, calendar_event_id: str, calendar_source: str, db_client: Any | None = None
) -> Optional[str]:
    """
    Find a meeting by its external calendar event ID and source.
    Returns the Firestore document ID if found, None otherwise.
    """
    clean_uid = _clean_path_id(uid, "uid")
    clean_event_id = _clean_identifier(calendar_event_id, "calendar_event_id")
    clean_source = _clean_identifier(calendar_source, "calendar_source")

    query = (
        _resolve_meetings_col(clean_uid, client=db_client)
        .where('calendar_event_id', '==', clean_event_id)
        .where('calendar_source', '==', clean_source)
        .limit(1)
    )

    docs = list(query.stream())
    if docs:
        return str(docs[0].id)

    return None


def _to_utc(dt: Any) -> datetime:
    """Strictly convert a datetime to UTC. Never silently falls back to current time."""
    if not isinstance(dt, datetime):
        raise ValueError(f"Expected datetime instance, got {type(dt).__name__}")
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def list_meetings(
    uid: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 50,
    db_client: Any | None = None,
) -> List[Dict[str, Any]]:
    """List calendar meetings, optionally filtered by date range, sorted by start_time descending."""
    clean_uid = _clean_id(uid, "uid")
    clamped_limit = max(1, min(int(limit), 500))

    query: Any = _resolve_meetings_col(clean_uid, client=db_client)
    if start_date:
        query = query.where('start_time', '>=', _to_utc(start_date))
    if end_date:
        query = query.where('start_time', '<=', _to_utc(end_date))
    query = query.order_by('start_time', direction=firestore.Query.DESCENDING).limit(clamped_limit)

    meetings: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        meetings.append(data)

    return meetings


def delete_meeting(uid: str, meeting_id: str, db_client: Any | None = None) -> None:
    """Delete a calendar meeting"""
    clean_uid = _clean_id(uid, "uid")
    clean_meeting_id = _clean_id(meeting_id, "meeting_id")
    _resolve_meetings_col(clean_uid, client=db_client).document(clean_meeting_id).delete()


def delete_old_meetings(uid: str, before_date: datetime, db_client: Any | None = None) -> int:
    """Delete meetings that ended before a certain date. Returns the number of meetings deleted."""
    clean_uid = _clean_id(uid, "uid")
    utc_before = _to_utc(before_date)
    query = _resolve_meetings_col(clean_uid, client=db_client).where('end_time', '<', utc_before)

    deleted_count = 0
    client = db_client or db
    batch = client.batch()
    batch_size = 0

    for doc in query.stream():
        batch.delete(doc.reference)
        batch_size += 1
        deleted_count += 1
        if batch_size >= 500:
            batch.commit()
            batch = client.batch()
            batch_size = 0

    if batch_size > 0:
        batch.commit()

    return deleted_count


def get_meetings_in_time_range(
    uid: str, start_time: datetime, end_time: datetime, db_client: Any | None = None
) -> List[Dict[str, Any]]:
    """Find meetings that overlap with the given time range, sorted by start_time ascending."""
    clean_uid = _clean_id(uid, "uid")
    start_utc = _to_utc(start_time)
    end_utc = _to_utc(end_time)

    query = (
        _resolve_meetings_col(clean_uid, client=db_client)
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
