import logging
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1 import FieldFilter

from ._client import db

logger = logging.getLogger(__name__)


def create(task_data: dict[str, Any]) -> None:
    """Create a task document in Firestore with input validation."""
    if not task_data or not task_data.get('id'):
        raise ValueError("task_data must contain an 'id' field")
    task_id = str(task_data['id']).strip()
    if not task_id:
        raise ValueError("task_data 'id' field must not be empty or whitespace")
    task_ref = db.collection('tasks').document(task_id)
    task_ref.set(task_data)


def update(task_id: str, task_data: dict[str, Any]) -> bool:
    """Update a task by id with TOCTOU NotFound guard. Returns True if updated, False if missing."""
    clean_id = (task_id or '').strip()
    if not clean_id:
        return False
    task_ref = db.collection('tasks').document(clean_id)
    try:
        task_ref.update(task_data)
        return True
    except NotFound as e:
        logger.warning("Task %s not found during update (concurrent deletion): %s", clean_id, e)
        return False


def get_task_by_action_request(action: str, request_id: str) -> dict[str, Any] | None:
    query = (
        db.collection('tasks')
        .where(filter=FieldFilter('action', '==', action))
        .where(filter=FieldFilter('request_id', '==', request_id))
        .limit(1)
    )
    tasks: list[dict[str, Any]] = [item.to_dict() for item in query.stream()]
    if len(tasks) > 0:
        return tasks[0]

    return None
