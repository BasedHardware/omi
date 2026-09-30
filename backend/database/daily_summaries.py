from typing import Any, Dict, Optional
from datetime import date

from google.cloud import firestore

from backend.core.config import settings
from backend.database.utils import get_firestore_client

# Constants
DESKTOP_DAILY_USAGE_COUNTER_FIELDS = [
    "total_active_time",
    "total_keystrokes",
    "total_mouse_clicks",
    "total_scrolls",
    "total_sessions",
    "total_afk_time",
    "total_idle_time",
]


def _validate_identifier(identifier: Any, field_name: str) -> str:
    """Validate that an identifier is a non-empty string without path separators."""
    if not isinstance(identifier, str):
        raise ValueError(f"{field_name} must be a string, got {type(identifier).__name__}")
    if not identifier.strip():
        raise ValueError(f"{field_name} cannot be empty or whitespace")
    if "/" in identifier:
        raise ValueError(f"{field_name} cannot contain path separators ('/')")
    return identifier.strip()


def _validate_and_get_counter(value: Any, field: str) -> int:
    """Safely extract and validate a counter value, defaulting to 0 if invalid."""
    if not isinstance(value, int) or isinstance(value, bool):
        return 0
    return max(0, value)


def _get_firestore() -> firestore.Client:
    return get_firestore_client()


async def upsert_desktop_daily_usage(
    uid: str,
    date: str,
    client_device_id: str,
    counters: Dict[str, Any],
) -> None:
    """Upsert desktop daily usage counters with validation."""
    # Validate identifiers
    uid = _validate_identifier(uid, "uid")
    date = _validate_identifier(date, "date")
    client_device_id = _validate_identifier(client_device_id, "client_device_id")

    db = _get_firestore()
    doc_ref = (
        db.collection("users")
        .document(uid)
        .collection("desktop_daily_usage")
        .document(date)
        .collection("devices")
        .document(client_device_id)
    )

    # Safely extract and validate counters
    sanitized_counters = {}
    for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
        sanitized_counters[field] = _validate_and_get_counter(
            counters.get(field, 0), field
        )

    @firestore.transactional
    def update_transaction(transaction: firestore.Transaction) -> None:
        snapshot = doc_ref.get(transaction=transaction)
        if snapshot.exists:
            existing_data = snapshot.to_dict() or {}
            merged_counters = {}
            for field in DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
                existing_value = _validate_and_get_counter(
                    existing_data.get(field, 0), field
                )
                new_value = sanitized_counters[field]
                merged_counters[field] = max(existing_value, new_value)
            transaction.update(doc_ref, merged_counters)
        else:
            transaction.set(doc_ref, sanitized_counters)

    await update_transaction()


async def get_desktop_daily_usage(
    uid: str,
    date: str,
    client_device_id: str,
) -> Optional[Dict[str, Any]]:
    """Get desktop daily usage with identifier validation."""
    try:
        uid = _validate_identifier(uid, "uid")
        date = _validate_identifier(date, "date")
        client_device_id = _validate_identifier(client_device_id, "client_device_id")
    except ValueError:
        return None

    db = _get_firestore()
    doc_ref = (
        db.collection("users")
        .document(uid)
        .collection("desktop_daily_usage")
        .document(date)
        .collection("devices")
        .document(client_device_id)
    )
    snapshot = await doc_ref.get()
    return snapshot.to_dict() if snapshot.exists else None


async def create_daily_summary(
    uid: str,
    date: str,
    summary_data: Dict[str, Any],
) -> None:
    """Create a daily summary with validation."""
    uid = _validate_identifier(uid, "uid")
    date = _validate_identifier(date, "date")

    if not isinstance(summary_data, dict):
        raise ValueError("summary_data must be a dictionary")
    if "id" not in summary_data:
        raise ValueError("summary_data must contain an 'id' field")
    summary_id = _validate_identifier(summary_data["id"], "summary_data['id']")

    db = _get_firestore()
    doc_ref = (
        db.collection("users")
        .document(uid)
        .collection("daily_summaries")
        .document(date)
        .collection("summaries")
        .document(summary_id)
    )
    await doc_ref.set(summary_data)


async def get_daily_summary(
    uid: str,
    date: str,
    summary_id: str,
) -> Optional[Dict[str, Any]]:
    """Get a daily summary with identifier validation."""
    try:
        uid = _validate_identifier(uid, "uid")
        date = _validate_identifier(date, "date")
        summary_id = _validate_identifier(summary_id, "summary_id")
    except ValueError:
        return None

    db = _get_firestore()
    doc_ref = (
        db.collection("users")
        .document(uid)
        .collection("daily_summaries")
        .document(date)
        .collection("summaries")
        .document(summary_id)
    )
    snapshot = await doc_ref.get()
    return snapshot.to_dict() if snapshot.exists else None
