"""Neutral-store persistence for per-user task workflow migration controls."""

from config.what_matters_now_smoke_fixture import WHAT_MATTERS_NOW_SMOKE_UID, is_development_smoke_fixture
from database.read_boundary import parse_snapshot_or_none
from database.store import get_document_store
from database.store.errors import AlreadyExists
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

CONTROL_COLLECTION = 'task_intelligence_control'
CONTROL_DOCUMENT = 'state'
_SMOKE_FIXTURE_CONTROL = TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0)


def _store():
    return get_document_store()


class DevelopmentSmokeFixtureConflictError(RuntimeError):
    """The code-owned smoke fixture will not replace an existing control document."""


def _control_path(uid: str) -> str:
    return f'users/{uid}/{CONTROL_COLLECTION}/{CONTROL_DOCUMENT}'


def get_task_workflow_control(uid: str) -> TaskWorkflowControl:
    snapshot = _store().get(_control_path(uid))
    if snapshot.exists is not True:
        return TaskWorkflowControl()
    return parse_snapshot_or_none(TaskWorkflowControl, snapshot) or TaskWorkflowControl()


def set_task_workflow_control(uid: str, control: TaskWorkflowControl) -> None:
    _store().set(_control_path(uid), control.persisted_payload())


def ensure_development_smoke_fixture(uid: str, *, stage: str | None = None) -> bool:
    """Create the dev fixture control once, without replacing any existing state."""

    if not is_development_smoke_fixture(uid, stage=stage):
        return False
    expected_payload = _SMOKE_FIXTURE_CONTROL.persisted_payload()
    path = _control_path(uid)
    try:
        # ``create`` is an atomic exists=false compare-and-create at the storage port.
        _store().create(path, expected_payload)
    except AlreadyExists:
        snapshot = _store().get(path)
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
