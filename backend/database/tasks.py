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


def get_tasks(uid: str, limit: int = 10, offset: int = 0):
    # Tasks likely store user_uid or uid. models/task.py says 'user_uid'
    query = (
        db.collection('tasks')
        .where(filter=FieldFilter('user_uid', '==', uid))
        .order_by('created_at', direction='DESCENDING')
        .limit(limit)
        .offset(offset)
    )
    return [item.to_dict() for item in query.stream()]


def delete_task(task_id: str):
    db.collection('tasks').document(task_id).delete()
