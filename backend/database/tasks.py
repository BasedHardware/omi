from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def create(task_data: dict[str, Any]) -> None:
    task_id = task_data.get('id')
    if not task_id:
        raise ValueError("task_data must include 'id'")
    task_ref = db.collection('tasks').document(str(task_id))
    task_ref.set(task_data, merge=True)


def update(task_id: str, task_data: dict[str, Any]) -> None:
    if not task_id:
        raise ValueError("task_id is required")
    task_ref = db.collection('tasks').document(str(task_id))
    task_ref.set(task_data, merge=True)


def get_task_by_action_request(action: str, request_id: str) -> dict[str, Any] | None:
    if not action or not request_id:
        return None
    query = (
        db.collection('tasks')
        .where(filter=FieldFilter('action', '==', action))
        .where(filter=FieldFilter('request_id', '==', request_id))
        .limit(1)
    )
    for item in query.stream():
        data = item.to_dict()
        if isinstance(data, dict):
            data.setdefault('id', item.id)
            return data

    return None
