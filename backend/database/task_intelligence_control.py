"""Firestore persistence for per-user task workflow migration controls."""

from typing import Any, cast

from database._client import db
from models.task_intelligence import TaskWorkflowControl

CONTROL_COLLECTION = 'task_intelligence_control'
CONTROL_DOCUMENT = 'state'


def get_task_workflow_control(uid: str) -> TaskWorkflowControl:
    ref = db.collection('users').document(uid).collection(CONTROL_COLLECTION).document(CONTROL_DOCUMENT)
    snapshot = ref.get()
    if snapshot.exists is not True:
        return TaskWorkflowControl()
    payload = snapshot.to_dict()
    if not isinstance(payload, dict):
        return TaskWorkflowControl()
    return TaskWorkflowControl.model_validate(cast(dict[str, Any], payload))


def set_task_workflow_control(uid: str, control: TaskWorkflowControl) -> None:
    ref = db.collection('users').document(uid).collection(CONTROL_COLLECTION).document(CONTROL_DOCUMENT)
    ref.set(control.model_dump(mode='json'))


__all__ = ['get_task_workflow_control', 'set_task_workflow_control']
