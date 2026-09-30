from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import HTTPException

from backend.database.client import db
from backend.models.wrapped import WrappedStatus

# Constants
WRAPPED_COLLECTION = "wrapped"
VALID_WRAPPED_STATUSES = {
    WrappedStatus.PENDING,
    WrappedStatus.PROCESSING,
    WrappedStatus.COMPLETED,
    WrappedStatus.FAILED,
    WrappedStatus.RESET
}
MIN_YEAR = 2000
MAX_YEAR = 2100


def _validate_identifier(uid: str) -> str:
    """Validate and sanitize user identifier to prevent path traversal and invalid paths."""
    if not uid or not isinstance(uid, str):
        raise ValueError("User identifier must be a non-empty string")
    stripped_uid = uid.strip()
    if not stripped_uid:
        raise ValueError("User identifier cannot be empty or whitespace")
    if "/" in stripped_uid:
        raise ValueError("User identifier cannot contain path separators")
    return stripped_uid


def _validate_year(year: int) -> int:
    """Validate year is within acceptable bounds."""
    if not isinstance(year, int):
        raise ValueError("Year must be an integer")
    if year < MIN_YEAR or year > MAX_YEAR:
        raise ValueError(f"Year must be between {MIN_YEAR} and {MAX_YEAR}")
    return year


def _get_wrapped_doc_path(uid: str, year: int) -> str:
    """Construct Firestore document path for wrapped data."""
    validated_uid = _validate_identifier(uid)
    validated_year = _validate_year(year)
    return f"{WRAPPED_COLLECTION}/{validated_uid}/{validated_year}"


async def get_wrapped(uid: str, year: int) -> Optional[Dict[str, Any]]:
    """Retrieve wrapped data for a user and year. Returns None if invalid or not found."""
    try:
        doc_path = _get_wrapped_doc_path(uid, year)
        doc = await db.get_document(doc_path)
        return doc.to_dict() if doc.exists else None
    except (ValueError, TypeError):
        return None


async def create_wrapped(uid: str, year: int, initial_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create wrapped document with validated inputs."""
    doc_path = _get_wrapped_doc_path(uid, year)
    if not isinstance(initial_data, dict):
        raise ValueError("Initial data must be a dictionary")
    await db.set_document(doc_path, initial_data)
    return {"path": doc_path, **initial_data}


async def update_wrapped_status(
    uid: str, year: int, status: WrappedStatus, progress: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Update wrapped status with validation for status and progress."""
    if status not in VALID_WRAPPED_STATUSES:
        raise ValueError(f"Invalid status. Must be one of {VALID_WRAPPED_STATUSES}")
    if progress is not None and not isinstance(progress, dict):
        raise ValueError("Progress must be a dictionary or None")

    doc_path = _get_wrapped_doc_path(uid, year)
    update_data = {"status": status.value}
    if progress is not None:
        update_data["progress"] = progress

    await db.update_document(doc_path, update_data)
    return {"path": doc_path, "status": status.value, "progress": progress}


async def update_wrapped_progress(
    uid: str, year: int, progress: Dict[str, Any]
) -> Dict[str, Any]:
    """Update wrapped progress with validation."""
    if not isinstance(progress, dict):
        raise ValueError("Progress must be a dictionary")

    doc_path = _get_wrapped_doc_path(uid, year)
    await db.update_document(doc_path, {"progress": progress})
    return {"path": doc_path, "progress": progress}


async def reset_wrapped_for_regeneration(uid: str, year: int) -> Dict[str, Any]:
    """Reset wrapped document for regeneration with validated inputs."""
    doc_path = _get_wrapped_doc_path(uid, year)
    await db.set_document(
        doc_path,
        {
            "status": WrappedStatus.PENDING.value,
            "progress": {},
            "regenerated_at": datetime.utcnow().isoformat()
        }
    )
    return {"path": doc_path, "status": WrappedStatus.PENDING.value}


def is_wrapped_stuck(
    wrapped_data: Optional[Dict[str, Any]], stale_minutes: int = 30
) -> bool:
    """
    Check if wrapped generation is stuck based on last update time.
    Returns False if data is None, not a dict, or stale_minutes is non-positive.
    """
    if wrapped_data is None or not isinstance(wrapped_data, dict):
        return False
    if not isinstance(stale_minutes, int) or stale_minutes <= 0:
        return False

    last_updated_str = wrapped_data.get("last_updated")
    if not last_updated_str or not isinstance(last_updated_str, str):
        return False

    try:
        last_updated = datetime.fromisoformat(last_updated_str)
        stale_threshold = datetime.utcnow() - timedelta(minutes=stale_minutes)
        return last_updated < stale_threshold
    except (ValueError, TypeError):
        return False