from datetime import datetime
from typing import Dict, List, Optional

from google.cloud import firestore

from ._client import db


def _get_meetings_collection(uid: str):
    """Get user's meetings collection reference"""
    return db.collection('users').document(uid).collection('meetings')


def create_meeting(uid: str, meeting_data: Dict) -> str:
    """
    Create a new calendar meeting in Firestore.
    Returns the Firestore document ID.

    NOTE: Times should already be in UTC before calling this function.
    """
    # Add timestamps (always in UTC for consistent querying)
    from datetime import timezone

    now = datetime.now(timezone.utc)
    meeting_data['created_at'] = now
    meeting_data['synced_at'] = now

    # Create document
    doc_ref = _get_meetings_collection(uid).document()
    doc_ref.set(meeting_data)

    return doc_ref.id


def update_meeting(uid: str, meeting_id: str, meeting_data: Dict) -> None:
    """
    Update an existing calendar meeting.

    NOTE: Times should already be in UTC before calling this function.
    """
    # Update synced_at timestamp (always in UTC for consistent querying)
    from datetime import timezone

    meeting_data['synced_at'] = datetime.now(timezone.utc)

    # Update document
    _get_meetings_collection(uid).document(meeting_id).update(meeting_data)


def get_meeting(uid: str, meeting_id: str) -> Optional[Dict]:
    """Get a calendar meeting by its Firestore document ID"""
    doc = _get_meetings_collection(uid).document(meeting_id).get()

    if not doc.exists:
        return None

    data = doc.to_dict()
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
        return docs[0].id

    return None


def list_meetings(
    uid: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, limit: int = 50
) -> List[Dict]:
    """
    List calendar meetings, optionally filtered by date range.
    Returns meetings sorted by start_time descending.
    """
    query = _get_meetings_collection(uid).order_by('start_time', direction=firestore.Query.DESCENDING).limit(limit)

    if start_date:
        query = query.where('start_time', '>=', start_date)

    if end_date:
        query = query.where('start_time', '<=', end_date)

    meetings = []
    for doc in query.stream():
        data = doc.to_dict()
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


def get_meetings_in_time_range(uid: str, start_time: datetime, end_time: datetime) -> List[Dict]:
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

    meetings = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        meetings.append(data)

    return meetings
