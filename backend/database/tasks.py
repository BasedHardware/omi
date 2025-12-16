from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def create(task_data: dict):
    task_id = task_data['id']
    task_ref = db.collection('tasks').document(task_id)
    task_ref.set(task_data)


def update(task_id: str, task_data: dict):
    task_ref = db.collection('tasks').document(task_id)
    task_ref.update(task_data)


def get_task_by_action_request(action: str, request_id: str):
    query = (
        db.collection('tasks')
        .where(filter=FieldFilter('action', '==', action))
        .where(filter=FieldFilter('request_id', '==', request_id))
        .limit(1)
    )
    tasks = [item.to_dict() for item in query.stream()]
    if len(tasks) > 0:
        return tasks[0]

    return None


def get_tasks_by_user(user_uid: str, limit: int = 100, offset: int = 0):
    """Get tasks for a specific user with pagination."""
    query = (
        db.collection('tasks')
        .where(filter=FieldFilter('user_uid', '==', user_uid))
        .order_by('created_at', direction='DESCENDING')
        .limit(limit)
        .offset(offset)
    )
    tasks = [item.to_dict() for item in query.stream()]
    return tasks


def get_task_by_id(task_id: str):
    """Get a single task by ID."""
    task_ref = db.collection('tasks').document(task_id)
    task_doc = task_ref.get()
    if task_doc.exists:
        return task_doc.to_dict()
    return None
