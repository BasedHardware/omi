import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import firestore
from google.cloud.firestore_v1 import transactional  # type: ignore[reportUnknownMemberType]  # firestore SDK stub gap

from ._client import db
from database.document_ids import calendar_meeting_doc_id

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MEETINGS_LIMIT = 50
MAX_MEETINGS_LIMIT = 500


def _typed_transactional(func: Callable[..., T]) -> Callable[..., T]:
    """Wrap @transactional preserving the wrapped function's typed signature.

    google-cloud-firestore's @transactional decorator surfaces as partially
    unknown under strict Pyright (no stubs); this thin wrapper keeps the typed
    call site while delegating runtime behavior to the SDK decorator.
    """
    return transactional(func)


def _validate_uid(uid: Any) -> str:
    """Validate user ID to prevent empty paths or path traversal."""
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError("Invalid user ID")
    return uid.strip()


def _validate_meeting_id(meeting_id: Any) -> str:
    """Validate meeting ID to prevent empty paths or path traversal."""
    if not isinstance(meeting_id, str) or not meeting_id.strip() or '/' in meeting_id:
        raise ValueError("Invalid meeting ID")
    return meeting_id.strip()


def _get_meetings_collection(uid: str) -> Any:
    """Get user's meetings collection reference"""
    clean_uid = _validate_uid(uid)
    return db.collection('users').document(clean_uid).collection('meetings')


def _to_utc(dt: Any) -> datetime:
    """Safely convert any datetime-like or ISO string value to timezone-aware UTC datetime.

    Raises:
        ValueError: If input cannot be converted to a valid timezone-aware UTC datetime.
    """
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    if hasattr(dt, 'timestamp') and callable(getattr(dt, 'timestamp')):
        try:
            return datetime.fromtimestamp(dt.timestamp(), tz=timezone.utc)
        except Exception as exc:
            raise ValueError(f"Cannot convert timestamp object to UTC datetime: {dt!r}") from exc
    if isinstance(dt, str) and dt.strip():
        try:
            parsed = datetime.fromisoformat(dt.strip().replace('Z', '+00:00'))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO datetime string: {dt!r}") from exc
    raise ValueError(f"Cannot convert {type(dt).__name__} to UTC datetime: {dt!r}")


@_typed_transactional
def _upsert_meeting_transaction(transaction: Any, doc_ref: Any, meeting_data: Dict[str, Any], now: datetime) -> None:
    """Upsert a natural-key meeting while preserving first-created metadata."""
    snapshot = doc_ref.get(transaction=transaction)
    payload: Dict[str, Any] = dict(meeting_data)
    payload['synced_at'] = now
    if not getattr(snapshot, "exists", False):
        payload['created_at'] = now
    if 'start_time' in payload and payload['start_time'] is not None:
        payload['start_time'] = _to_utc(payload['start_time'])
    if 'end_time' in payload and payload['end_time'] is not None:
        payload['end_time'] = _to_utc(payload['end_time'])
    transaction.set(doc_ref, payload, merge=True)


def create_meeting(uid: str, meeting_data: Any) -> str:
    """Create or idempotently upsert a calendar meeting in Firestore.
    Returns the deterministic Firestore document ID.

    NOTE: Times should already be in UTC before calling this function.
    """
    clean_uid = _validate_uid(uid)
    if not meeting_data or not hasattr(meeting_data, 'get'):
        raise ValueError("meeting_data must be a dictionary")

    calendar_source = str(meeting_data.get('calendar_source') or '').strip()
    calendar_event_id = str(meeting_data.get('calendar_event_id') or '').strip()
    if not calendar_source or not calendar_event_id:
        raise ValueError("calendar_source and calendar_event_id are required")

    meeting_id = calendar_meeting_doc_id(clean_uid, calendar_source, calendar_event_id)
    doc_ref = _get_meetings_collection(clean_uid).document(meeting_id)
    transaction = db.transaction()
    _upsert_meeting_transaction(transaction, doc_ref, cast(Dict[str, Any], meeting_data), datetime.now(timezone.utc))
    return meeting_id


def update_meeting(uid: str, meeting_id: str, meeting_data: Any) -> bool:
    """Update an existing calendar meeting.
    Returns True if updated successfully, False if document does not exist or input is invalid.

    NOTE: Times should already be in UTC before calling this function.
    """
    try:
        clean_uid = _validate_uid(uid)
        clean_meeting_id = _validate_meeting_id(meeting_id)
    except ValueError:
        return False

    if not meeting_data or not hasattr(meeting_data, 'get'):
        return False

    doc_ref = _get_meetings_collection(clean_uid).document(clean_meeting_id)
    if not getattr(doc_ref.get(), "exists", False):
        return False

    # Update synced_at timestamp (always in UTC for consistent querying)
    payload: Dict[str, Any] = dict(cast(Dict[str, Any], meeting_data))
    payload['synced_at'] = datetime.now(timezone.utc)
    if 'start_time' in payload and payload['start_time'] is not None:
        try:
            payload['start_time'] = _to_utc(payload['start_time'])
        except ValueError:
            return False
    if 'end_time' in payload and payload['end_time'] is not None:
        try:
            payload['end_time'] = _to_utc(payload['end_time'])
        except ValueError:
            return False

    doc_ref.update(payload)
    return True


def get_meeting(uid: str, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Get a calendar meeting by its Firestore document ID"""
    try:
        clean_uid = _validate_uid(uid)
        clean_meeting_id = _validate_meeting_id(meeting_id)
    except ValueError:
        return None

    doc = _get_meetings_collection(clean_uid).document(clean_meeting_id).get()

    if not getattr(doc, "exists", False):
        return None

    raw: object = doc.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    data['id'] = doc.id
    return data


def get_meeting_id_by_calendar_event(uid: str, calendar_event_id: str, calendar_source: str) -> Optional[str]:
    """Find a meeting by its external calendar event ID and source.
    Returns the Firestore document ID if found, None otherwise.
    """
    try:
        clean_uid = _validate_uid(uid)
    except ValueError:
        return None

    clean_event_id = str(calendar_event_id or '').strip()
    clean_source = str(calendar_source or '').strip()
    if not clean_event_id or not clean_source:
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


def list_meetings(
    uid: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = DEFAULT_MEETINGS_LIMIT,
) -> List[Dict[str, Any]]:
    """List calendar meetings, optionally filtered by date range, sorted by start_time descending."""
    try:
        clean_uid = _validate_uid(uid)
    except ValueError:
        return []

    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = DEFAULT_MEETINGS_LIMIT
    bounded_limit = max(1, min(parsed_limit, MAX_MEETINGS_LIMIT))
    query: Any = _get_meetings_collection(clean_uid)

    start_utc: Optional[datetime] = None
    if start_date is not None:
        try:
            start_utc = _to_utc(start_date)
        except ValueError:
            return []

    end_utc: Optional[datetime] = None
    if end_date is not None:
        try:
            end_utc = _to_utc(end_date)
        except ValueError:
            return []

    if start_utc and end_utc and start_utc > end_utc:
        return []

    if start_utc:
        query = query.where('start_time', '>=', start_utc)
    if end_utc:
        query = query.where('start_time', '<=', end_utc)
    query = query.order_by('start_time', direction=firestore.Query.DESCENDING).limit(bounded_limit)

    meetings: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        meetings.append(data)

    return meetings


def delete_meeting(uid: str, meeting_id: str) -> bool:
    """Delete a calendar meeting. Returns True if deleted, False on invalid IDs."""
    try:
        clean_uid = _validate_uid(uid)
        clean_meeting_id = _validate_meeting_id(meeting_id)
    except ValueError:
        return False

    _get_meetings_collection(clean_uid).document(clean_meeting_id).delete()
    return True


def delete_old_meetings(uid: str, before_date: Any) -> int:
    """Delete meetings that ended before a certain date. Returns the number of meetings deleted."""
    try:
        clean_uid = _validate_uid(uid)
    except ValueError:
        return 0

    if before_date is None:
        return 0
    try:
        before_utc = _to_utc(before_date)
    except ValueError:
        return 0

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
    """Find meetings that overlap with the given time range, sorted by start_time ascending.

    Args:
        uid: User ID.
        start_time: Window start datetime.
        end_time: Window end datetime.

    Returns:
        List of meeting dictionaries overlapping the window, up to 10 entries.

    Note:
        When the composite Firestore index (start_time ASC, end_time ASC) is unavailable,
        the query falls back to a single-field query on start_time. The fallback inspects
        up to 50 candidates in the start_time window before in-memory end_time filtering,
        capping results at 10 to balance performance on the conversation-processing hot path.
    """
    try:
        clean_uid = _validate_uid(uid)
    except ValueError:
        return []

    try:
        start_utc = _to_utc(start_time)
        end_utc = _to_utc(end_time)
    except ValueError:
        return []

    if start_utc >= end_utc:
        return []

    try:
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
    except GoogleAPICallError as exc:
        logger.warning(
            "Composite range query failed for user %s (%s). Falling back to single-field query. "
            "Note: Fallback scans up to 50 candidates in start_time window before in-memory filtering.",
            clean_uid,
            type(exc).__name__,
        )
        # Note: When the composite index is missing or unavailable, this fallback
        # scans up to 50 meetings ordered by start_time and filters end_time in-memory,
        # capping returned meetings at 10 to balance latency and coverage on conversation processing.
        fallback_query = (
            _get_meetings_collection(clean_uid)
            .where('start_time', '<', end_utc)
            .order_by('start_time', direction=firestore.Query.ASCENDING)
            .limit(50)
        )
        filtered: List[Dict[str, Any]] = []
        for doc in fallback_query.stream():
            raw = doc.to_dict()
            data = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
            data['id'] = doc.id
            doc_end = data.get('end_time')
            try:
                if doc_end and _to_utc(doc_end) > start_utc:
                    filtered.append(data)
                    if len(filtered) >= 10:
                        break
            except ValueError:
                continue
        return filtered
