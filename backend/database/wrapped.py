"""
Database operations for Wrapped (yearly recap) stored in users/{uid}/wrapped/{year}.
"""

from datetime import datetime, timezone
from typing import Optional

from ._client import db


# Collection name under user document
WRAPPED_COLLECTION = 'wrapped'


class WrappedStatus:
    NOT_GENERATED = 'not_generated'
    PROCESSING = 'processing'
    DONE = 'done'
    ERROR = 'error'


def get_wrapped(uid: str, year: int) -> Optional[dict]:
    """
    Get the wrapped document for a user and year.

    Args:
        uid: User ID
        year: Year (e.g., 2025)

    Returns:
        Wrapped document data or None if not found
    """
    user_ref = db.collection('users').document(uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(year))
    doc = wrapped_ref.get()

    if not doc.exists:
        return None

    data = doc.to_dict()

    # Convert Firestore timestamps to datetime objects
    for field in ['started_at', 'completed_at', 'updated_at']:
        if field in data and data[field]:
            if hasattr(data[field], 'timestamp'):
                data[field] = datetime.fromtimestamp(data[field].timestamp(), tz=timezone.utc)

    return data


def create_wrapped(uid: str, year: int) -> dict:
    """
    Create a new wrapped document with status=processing.

    Args:
        uid: User ID
        year: Year (e.g., 2025)

    Returns:
        The created wrapped document data
    """
    now = datetime.now(timezone.utc)
    wrapped_data = {
        'year': year,
        'status': WrappedStatus.PROCESSING,
        'started_at': now,
        'updated_at': now,
        'completed_at': None,
        'result': None,
        'error': None,
        'schema_version': 1,
    }

    user_ref = db.collection('users').document(uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(year))
    wrapped_ref.set(wrapped_data)

    return wrapped_data


def update_wrapped_status(
    uid: str,
    year: int,
    status: str,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> bool:
    """
    Update the status of a wrapped document.

    Args:
        uid: User ID
        year: Year (e.g., 2025)
        status: New status (processing, done, error)
        result: Result payload (only when status=done)
        error: Error message (only when status=error)

    Returns:
        True if updated successfully
    """
    user_ref = db.collection('users').document(uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(year))

    if not wrapped_ref.get().exists:
        return False

    now = datetime.now(timezone.utc)
    update_data = {
        'status': status,
        'updated_at': now,
    }

    if status == WrappedStatus.DONE:
        update_data['completed_at'] = now
        update_data['result'] = result
        update_data['error'] = None
    elif status == WrappedStatus.ERROR:
        update_data['error'] = error
        update_data['result'] = None

    wrapped_ref.update(update_data)
    return True


def update_wrapped_progress(uid: str, year: int, progress: dict) -> bool:
    """
    Update the progress of a wrapped generation (heartbeat).

    Args:
        uid: User ID
        year: Year (e.g., 2025)
        progress: Progress info (e.g., {"step": "computing_stats", "pct": 0.5})

    Returns:
        True if updated successfully
    """
    user_ref = db.collection('users').document(uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(year))

    if not wrapped_ref.get().exists:
        return False

    wrapped_ref.update(
        {
            'progress': progress,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def reset_wrapped_for_regeneration(uid: str, year: int) -> dict:
    """
    Reset a stuck or errored wrapped document for regeneration.

    Args:
        uid: User ID
        year: Year (e.g., 2025)

    Returns:
        The updated wrapped document data
    """
    now = datetime.now(timezone.utc)
    wrapped_data = {
        'year': year,
        'status': WrappedStatus.PROCESSING,
        'started_at': now,
        'updated_at': now,
        'completed_at': None,
        'result': None,
        'error': None,
        'progress': None,
        'schema_version': 1,
    }

    user_ref = db.collection('users').document(uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(year))
    wrapped_ref.set(wrapped_data)

    return wrapped_data


def is_wrapped_stuck(wrapped_data: dict, stale_minutes: int = 15) -> bool:
    """
    Check if a wrapped generation is stuck (no heartbeat for stale_minutes).

    Args:
        wrapped_data: The wrapped document data
        stale_minutes: Minutes after which a processing job is considered stuck

    Returns:
        True if the job appears stuck
    """
    if wrapped_data.get('status') != WrappedStatus.PROCESSING:
        return False

    updated_at = wrapped_data.get('updated_at')
    if not updated_at:
        return True

    # Ensure updated_at is a datetime
    if hasattr(updated_at, 'timestamp'):
        updated_at = datetime.fromtimestamp(updated_at.timestamp(), tz=timezone.utc)
    elif updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    elapsed = (now - updated_at).total_seconds() / 60

    return elapsed > stale_minutes
