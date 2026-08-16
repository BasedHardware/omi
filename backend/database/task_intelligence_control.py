"""Firestore persistence for per-user task workflow migration controls."""

from google.api_core.exceptions import AlreadyExists, Conflict

from config.what_matters_now_smoke_fixture import WHAT_MATTERS_NOW_SMOKE_UID, is_development_smoke_fixture
from database._client import db
from database.read_boundary import parse_snapshot_or_none
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

CONTROL_COLLECTION = 'task_intelligence_control'
CONTROL_DOCUMENT = 'state'
_SMOKE_FIXTURE_CONTROL = TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0)


class DevelopmentSmokeFixtureConflictError(RuntimeError):
    """The code-owned smoke fixture will not replace an existing control document."""


def _control_ref(uid: str):
    return db.collection('users').document(uid).collection(CONTROL_COLLECTION).document(CONTROL_DOCUMENT)


def get_task_workflow_control(uid: str) -> TaskWorkflowControl:
    ref = _control_ref(uid)
    snapshot = ref.get()
    if snapshot.exists is not True:
        return TaskWorkflowControl()
    return parse_snapshot_or_none(TaskWorkflowControl, snapshot) or TaskWorkflowControl()


def set_task_workflow_control(uid: str, control: TaskWorkflowControl) -> None:
    ref = _control_ref(uid)
    ref.set(control.persisted_payload())


def ensure_development_smoke_fixture(uid: str, *, stage: str | None = None) -> bool:
    """Create the dev fixture control once, without replacing any existing state."""

    if not is_development_smoke_fixture(uid, stage=stage):
        return False
    expected_payload = _SMOKE_FIXTURE_CONTROL.persisted_payload()
    ref = _control_ref(uid)
    try:
        # Firestore's create operation is an atomic exists=false compare-and-create.
        ref.create(expected_payload)
    except (AlreadyExists, Conflict):
        snapshot = ref.get()
        if snapshot.exists:
            existing = parse_snapshot_or_none(TaskWorkflowControl, snapshot)
            if existing is not None and existing.persisted_payload() == expected_payload:
                return False
        raise DevelopmentSmokeFixtureConflictError(
            'development smoke fixture control already exists with differing state'
        ) from None

    return True


__all__ = [
    'WHAT_MATTERS_NOW_SMOKE_UID',
    'DevelopmentSmokeFixtureConflictError',
    'ensure_development_smoke_fixture',
    'get_task_workflow_control',
    'set_task_workflow_control',
]
