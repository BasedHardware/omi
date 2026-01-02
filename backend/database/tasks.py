from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def create(task_data: dict):
    task_id = task_data['id']
    task_ref = db.collection('tasks').document(task_id)
    task_ref.set(task_data)


def get_task_by_id(task_id: str):
    doc = db.collection('tasks').document(task_id).get()
    if doc.exists:
        return doc.to_dict()
    return None

def get_tasks_by_user(user_uid: str, limit=20, offset=0):
    query = (
        db.collection('tasks')
        .where(filter=FieldFilter('user_uid', '==', user_uid))
        .limit(limit + offset)
    )
    results = [doc.to_dict() for doc in query.stream()]
    return results[offset:]

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
