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


class _FakeSnapshot:
    def __init__(self, *, exists, data):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


class _FakeDoc:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def collection(self, _name):
        return _FakeCollection(self._snapshot)

    def get(self):
        return self._snapshot


class _FakeCollection:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def document(self, _id):
        return _FakeDoc(self._snapshot)


class _FakeDb:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def collection(self, _name):
        return _FakeCollection(self._snapshot)


def _install_db(monkeypatch, snapshot):
    monkeypatch.setattr(task_control_db, 'db', _FakeDb(snapshot))


def test_malformed_control_falls_back_to_legacy_default(monkeypatch):
    # extra='forbid': an unknown/renamed persisted field fails to load with ValidationError.
    snapshot = _FakeSnapshot(
        exists=True,
        data={'workflow_mode': 'write', 'account_generation': 2, 'unexpected_legacy_field': True},
    )
    _install_db(monkeypatch, snapshot)

    control = task_control_db.get_task_workflow_control('uid-1')

    # Falls back to the default, which is legacy-safe: writes stay disabled, never silently enabled.
    assert control == TaskWorkflowControl()
    assert control.workflow_mode is TaskWorkflowMode.off
    assert control.account_generation == 0


def test_valid_control_is_parsed(monkeypatch):
    snapshot = _FakeSnapshot(exists=True, data={'workflow_mode': 'write', 'account_generation': 2})
    _install_db(monkeypatch, snapshot)

    control = task_control_db.get_task_workflow_control('uid-1')

    assert control.workflow_mode is TaskWorkflowMode.write
    assert control.account_generation == 2


def test_unexpected_error_propagates(monkeypatch):
    snapshot = _FakeSnapshot(exists=True, data={'workflow_mode': 'write', 'account_generation': 2})
    _install_db(monkeypatch, snapshot)

    def _boom(*_args, **_kwargs):
        raise RuntimeError('unexpected non-validation failure')

    # The guard catches only ValidationError; anything else must still surface.
    monkeypatch.setattr(task_control_db.TaskWorkflowControl, 'model_validate', _boom)

    with pytest.raises(RuntimeError, match='unexpected non-validation failure'):
        task_control_db.get_task_workflow_control('uid-1')
