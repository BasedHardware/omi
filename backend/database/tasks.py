import logging
from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from ._client import db

logger = logging.getLogger(__name__)


def _clean_task_id(task_id: Any) -> str | None:
    """Validate task identifier, rejecting path traversal and empty allocations."""
    if not isinstance(task_id, str):
        return None
    cleaned = task_id.strip()
    if not cleaned or len(cleaned) > 128:
        return None
    if "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        return None
    return cleaned


def create(task_data: dict[str, Any], *, db_client: Any = None) -> bool:
    """Create a task document with defensive validation and error handling."""
    if not isinstance(task_data, dict):
        return False
    clean_id = _clean_task_id(task_data.get("id"))
    if not clean_id:
        return False
    client = db_client or db
    try:
        task_ref = client.collection("tasks").document(clean_id)
        task_ref.set(task_data)
        return True
    except Exception as exc:
        logger.warning("Failed to create task id=%s: %s", clean_id, exc)
        return False


def update(task_id: str, task_data: dict[str, Any], *, db_client: Any = None) -> bool:
    """Update an existing task document safely."""
    clean_id = _clean_task_id(task_id)
    if not clean_id or not isinstance(task_data, dict) or not task_data:
        return False
    client = db_client or db
    try:
        task_ref = client.collection("tasks").document(clean_id)
        task_ref.update(task_data)
        return True
    except Exception as exc:
        logger.warning("Failed to update task id=%s: %s", clean_id, exc)
        return False


def get_task_by_action_request(action: str, request_id: str, *, db_client: Any = None) -> dict[str, Any] | None:
    """Retrieve task matching action and request_id with early input validation."""
    if not isinstance(action, str) or not isinstance(request_id, str):
        return None
    clean_action = action.strip()
    clean_request_id = request_id.strip()
    if not clean_action or not clean_request_id:
        return None

    client = db_client or db
    try:
        query = (
            client.collection("tasks")
            .where(filter=FieldFilter("action", "==", clean_action))
            .where(filter=FieldFilter("request_id", "==", clean_request_id))
            .limit(1)
        )
        tasks: list[dict[str, Any]] = [item.to_dict() for item in query.stream() if getattr(item, "to_dict", None)]
        if tasks:
            return tasks[0]
        return None
    except Exception as exc:
        logger.warning("Failed to retrieve task by action=%s request_id=%s: %s", clean_action, clean_request_id, exc)
        return None
