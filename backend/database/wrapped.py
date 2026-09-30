"""
Database operations for Wrapped (yearly recap) stored in users/{uid}/wrapped/{year}.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from ._client import db

# Collection name under user document
WRAPPED_COLLECTION = 'wrapped'


class WrappedStatus:
    NOT_GENERATED = 'not_generated'
    PROCESSING = 'processing'
    DONE = 'done'
    ERROR = 'error'


VALID_WRAPPED_STATUSES = {
    WrappedStatus.NOT_GENERATED,
    WrappedStatus.PROCESSING,
    WrappedStatus.DONE,
    WrappedStatus.ERROR,
}


def _validate_identifier(value: Any, field_name: str = "uid") -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or '/' in cleaned or '\\' in cleaned:
        return None
    return cleaned


def _validate_year(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if 2000 <= value <= 2100:
            return value
        return None
    if isinstance(value, str):
        val_str = value.strip()
        if val_str.isdigit():
            val_int = int(val_str)
            if 2000 <= val_int <= 2100:
                return val_int
    return None


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _coerce_timestamp(value: Any) -> Optional[datetime]:
    if hasattr(value, 'timestamp'):
        return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return None


def get_wrapped(uid: str, year: int) -> Optional[Dict[str, Any]]:
    """
    Get the wrapped document for a user and year.

    Args:
        uid: User ID
        year: Year (e.g., 2025)

    Returns:
        Wrapped document data or None if not found or invalid args
    """
    valid_uid = _validate_identifier(uid, "uid")
    valid_year = _validate_year(year)
    if not valid_uid or valid_year is None:
        return None

    user_ref = db.collection('users').document(valid_uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(valid_year))
    doc = wrapped_ref.get()

    if not getattr(doc, "exists", False):
        return None

    data = _typed_doc(doc)

    # Convert Firestore timestamps to datetime objects
    for field in ['started_at', 'completed_at', 'updated_at']:
        if field in data and data[field]:
            coerced = _coerce_timestamp(data[field])
            if coerced is not None:
                data[field] = coerced

    return data


def create_wrapped(uid: str, year: int) -> Dict[str, Any]:
    """
    Create a new wrapped document with status=processing.

    Args:
        uid: User ID
        year: Year (e.g., 2025)

    Returns:
        The created wrapped document data
    """
    valid_uid = _validate_identifier(uid, "uid")
    valid_year = _validate_year(year)
    if not valid_uid:
        raise ValueError("uid must be a non-empty string without path separators")
    if valid_year is None:
        raise ValueError("year must be a valid integer between 2000 and 2100")

    now = datetime.now(timezone.utc)
    wrapped_data: Dict[str, Any] = {
        'year': valid_year,
        'status': WrappedStatus.PROCESSING,
        'started_at': now,
        'updated_at': now,
        'completed_at': None,
        'result': None,
        'error': None,
        'schema_version': 1,
    }

    user_ref = db.collection('users').document(valid_uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(valid_year))
    wrapped_ref.set(wrapped_data)

    return wrapped_data


def update_wrapped_status(
    uid: str,
    year: int,
    status: str,
    result: Optional[Dict[str, Any]] = None,
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
    valid_uid = _validate_identifier(uid, "uid")
    valid_year = _validate_year(year)
    if not valid_uid or valid_year is None or status not in VALID_WRAPPED_STATUSES:
        return False

    user_ref = db.collection('users').document(valid_uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(valid_year))

    if not getattr(wrapped_ref.get(), "exists", False):
        return False

    now = datetime.now(timezone.utc)
    update_data: Dict[str, Any] = {
        'status': status,
        'updated_at': now,
    }

    if status == WrappedStatus.DONE:
        update_data['completed_at'] = now
        update_data['result'] = result if isinstance(result, dict) else {}
        update_data['error'] = None
    elif status == WrappedStatus.ERROR:
        update_data['error'] = str(error) if error is not None else "Unknown error"
        update_data['result'] = None

    wrapped_ref.update(update_data)
    return True


def update_wrapped_progress(uid: str, year: int, progress: Dict[str, Any]) -> bool:
    """
    Update the progress of a wrapped generation (heartbeat).

    Args:
        uid: User ID
        year: Year (e.g., 2025)
        progress: Progress info (e.g., {"step": "computing_stats", "pct": 0.5})

    Returns:
        True if updated successfully
    """
    valid_uid = _validate_identifier(uid, "uid")
    valid_year = _validate_year(year)
    if not valid_uid or valid_year is None or not isinstance(progress, dict):
        return False

    user_ref = db.collection('users').document(valid_uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(valid_year))

    if not getattr(wrapped_ref.get(), "exists", False):
        return False

    wrapped_ref.update(
        {
            'progress': progress,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def reset_wrapped_for_regeneration(uid: str, year: int) -> Dict[str, Any]:
    """
    Reset a stuck or errored wrapped document for regeneration.

    Args:
        uid: User ID
        year: Year (e.g., 2025)

    Returns:
        The updated wrapped document data
    """
    valid_uid = _validate_identifier(uid, "uid")
    valid_year = _validate_year(year)
    if not valid_uid:
        raise ValueError("uid must be a non-empty string without path separators")
    if valid_year is None:
        raise ValueError("year must be a valid integer between 2000 and 2100")

    now = datetime.now(timezone.utc)
    wrapped_data: Dict[str, Any] = {
        'year': valid_year,
        'status': WrappedStatus.PROCESSING,
        'started_at': now,
        'updated_at': now,
        'completed_at': None,
        'result': None,
        'error': None,
        'progress': None,
        'schema_version': 1,
    }

    user_ref = db.collection('users').document(valid_uid)
    wrapped_ref = user_ref.collection(WRAPPED_COLLECTION).document(str(valid_year))
    wrapped_ref.set(wrapped_data)

    return wrapped_data


def is_wrapped_stuck(wrapped_data: Optional[Dict[str, Any]], stale_minutes: int = 15) -> bool:
    """
    Check if a wrapped generation is stuck (no heartbeat for stale_minutes).

    Args:
        wrapped_data: The wrapped document data
        stale_minutes: Minutes after which a processing job is considered stuck

    Returns:
        True if the job appears stuck (fail-safe for missing or unparseable updated_at)
    """
    if not isinstance(wrapped_data, dict):
        return False

    if wrapped_data.get('status') != WrappedStatus.PROCESSING:
        return False

    updated_at_raw = wrapped_data.get('updated_at')
    if not updated_at_raw:
        return True

    updated_at = _coerce_timestamp(updated_at_raw)
    if updated_at is None:
        return True

    now = datetime.now(timezone.utc)
    elapsed = (now - updated_at).total_seconds() / 60

    return elapsed > stale_minutes