"""Regression: a malformed task workflow control doc must not 500 the reads that gate on it.

`get_task_workflow_control` is called by every candidate and staged-task router path
(routers/candidates.py, routers/staged_tasks.py). A single drifted control document
(the model is extra='forbid', so a removed/renamed field or a bad enum value fails to
load) used to raise ValidationError straight out to the client. The guard falls back to
the model's legacy-safe default instead, and only an unexpected non-ValidationError still
propagates.
"""

import pytest

import database.task_intelligence_control as task_control_db
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode
from tests.store_fakes import FakeDocumentStore

_CONTROL_PATH = 'users/uid-1/task_intelligence_control/state'


def _install_store(monkeypatch, data):
    store = FakeDocumentStore()
    if data is not None:
        store.set(_CONTROL_PATH, data)
    monkeypatch.setattr(task_control_db, '_store', lambda: store)
    return store


def test_malformed_control_falls_back_to_legacy_default(monkeypatch):
    # extra='forbid': an unknown/renamed persisted field fails to load with ValidationError.
    _install_store(
        monkeypatch,
        {'workflow_mode': 'write', 'account_generation': 2, 'unexpected_legacy_field': True},
    )

    control = task_control_db.get_task_workflow_control('uid-1')

    # Falls back to the default, which is legacy-safe: writes stay disabled, never silently enabled.
    assert control == TaskWorkflowControl()
    assert control.workflow_mode is TaskWorkflowMode.off
    assert control.account_generation == 0


def test_valid_control_is_parsed(monkeypatch):
    _install_store(monkeypatch, {'workflow_mode': 'write', 'account_generation': 2})

    control = task_control_db.get_task_workflow_control('uid-1')

    assert control.workflow_mode is TaskWorkflowMode.write
    assert control.account_generation == 2


def test_unexpected_error_propagates(monkeypatch):
    _install_store(monkeypatch, {'workflow_mode': 'write', 'account_generation': 2})

    def _boom(*_args, **_kwargs):
        raise RuntimeError('unexpected non-validation failure')

    # The guard catches only ValidationError; anything else must still surface.
    monkeypatch.setattr(task_control_db.TaskWorkflowControl, 'model_validate', _boom)

    with pytest.raises(RuntimeError, match='unexpected non-validation failure'):
        task_control_db.get_task_workflow_control('uid-1')
