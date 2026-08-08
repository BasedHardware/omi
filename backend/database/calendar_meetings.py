from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from database.store import get_document_store
from database.document_ids import calendar_meeting_doc_id


def _store():
    return get_document_store()


def _meetings_path(uid: str) -> str:
    """Logical path of a user's meetings collection."""
    return f'users/{uid}/meetings'


def create_meeting(uid: str, meeting_data: Dict[str, Any]) -> str:
    """
    Create or idempotently upsert a calendar meeting.
    Returns the deterministic document ID.

    NOTE: Times should already be in UTC before calling this function.
    """
    meeting_id = calendar_meeting_doc_id(uid, meeting_data['calendar_source'], meeting_data['calendar_event_id'])
    path = f'{_meetings_path(uid)}/{meeting_id}'
    now = datetime.now(timezone.utc)

    def _upsert(tx: Any) -> None:
        """Upsert a natural-key meeting while preserving first-created metadata."""
        snapshot = tx.get(path)
        payload: Dict[str, Any] = dict(meeting_data)
        payload['synced_at'] = now
        if not snapshot.exists:
            payload['created_at'] = now
        tx.set(path, payload, merge=True)

    _store().run_transaction(_upsert)
    return meeting_id


def update_meeting(uid: str, meeting_id: str, meeting_data: Dict[str, Any]) -> None:
    """
    Update an existing calendar meeting.

    NOTE: Times should already be in UTC before calling this function.
    """
    # Update synced_at timestamp (always in UTC for consistent querying)
    meeting_data['synced_at'] = datetime.now(timezone.utc)

    # Update document
    _store().update(f'{_meetings_path(uid)}/{meeting_id}', meeting_data)


def get_meeting(uid: str, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Get a calendar meeting by its document ID"""
    doc = _store().get(f'{_meetings_path(uid)}/{meeting_id}')

    if not doc.exists:
        return None

    raw: object = doc.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    data['id'] = doc.id
    return data


def get_meeting_id_by_calendar_event(uid: str, calendar_event_id: str, calendar_source: str) -> Optional[str]:
    """
    Find a meeting by its external calendar event ID and source.
    Returns the document ID if found, None otherwise.
    """
    docs = _store().query(
        _meetings_path(uid),
        filters=[
            ('calendar_event_id', '==', calendar_event_id),
            ('calendar_source', '==', calendar_source),
        ],
        limit=1,
    )
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
    filters: List[Any] = []
    if start_date:
        filters.append(('start_time', '>=', start_date))
    if end_date:
        filters.append(('start_time', '<=', end_date))

    docs = _store().query(
        _meetings_path(uid),
        filters=filters or None,
        order_by='start_time',
        direction='desc',
        limit=limit,
    )

    meetings: List[Dict[str, Any]] = []
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        meetings.append(data)

    return meetings


def delete_meeting(uid: str, meeting_id: str) -> None:
    """Delete a calendar meeting"""
    _store().delete(f'{_meetings_path(uid)}/{meeting_id}')


def delete_old_meetings(uid: str, before_date: datetime) -> int:
    """
    Delete meetings that ended before a certain date.
    Returns the number of meetings deleted.
    """
    store = _store()
    docs = store.query(_meetings_path(uid), filters=[('end_time', '<', before_date)])

    deleted_count = 0
    batch = store.batch()
    batch_size = 0

    for doc in docs:
        batch.delete(doc.path)
        batch_size += 1
        deleted_count += 1

        # Commit in batches of 500 (Firestore limit)
        if batch_size >= 500:
            batch.commit()
            batch = store.batch()
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
    docs = _store().query(
        _meetings_path(uid),
        filters=[
            ('start_time', '<', end_time),
            ('end_time', '>', start_time),
        ],
        order_by='start_time',
        direction='asc',
        limit=10,  # Cap to prevent excessive results
    )

    meetings: List[Dict[str, Any]] = []
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        meetings.append(data)

    return meetings
