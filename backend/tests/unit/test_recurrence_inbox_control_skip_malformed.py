"""Regression: a malformed task_intelligence_control doc must not crash the recurrence handoff.

recurrence_inbox._validate_generation loads the per-user control doc with
TaskWorkflowControl.model_validate. The model is extra='forbid', so a drifted document raised
ValidationError straight out of the recurrence enqueue/transaction paths. The guard falls back to
the legacy-safe default, which fails the generation/mode checks, so a malformed control is treated
as a RecurrenceGenerationMismatchError (an outcome callers already handle) rather than crashing.
"""

import pytest

import database.recurrence_inbox as recurrence_inbox_db
from database.recurrence_inbox import _validate_generation, RecurrenceGenerationMismatchError


class _FakeSnapshot:
    def __init__(self, *, exists, data):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


def test_malformed_control_is_treated_as_generation_mismatch():
    # extra='forbid': an unknown persisted field fails to load with ValidationError.
    snapshot = _FakeSnapshot(
        exists=True,
        data={'workflow_mode': 'write', 'account_generation': 1, 'legacy_extra': True},
    )

    # Falls back to the default (account_generation=0), so it fails the generation check -- a handled
    # mismatch, not a ValidationError bubbling out of the recurrence handoff.
    with pytest.raises(RecurrenceGenerationMismatchError):
        _validate_generation(snapshot, account_generation=1)


def test_valid_matching_control_passes():
    snapshot = _FakeSnapshot(exists=True, data={'workflow_mode': 'write', 'account_generation': 1})
    assert _validate_generation(snapshot, account_generation=1) is None


def test_unexpected_error_propagates(monkeypatch):
    snapshot = _FakeSnapshot(exists=True, data={'workflow_mode': 'write', 'account_generation': 1})

    def _boom(*_args, **_kwargs):
        raise RuntimeError('unexpected non-validation failure')

    # The guard catches only ValidationError; anything else must still surface.
    monkeypatch.setattr(recurrence_inbox_db.TaskWorkflowControl, 'model_validate', _boom)

    with pytest.raises(RuntimeError, match='unexpected non-validation failure'):
        _validate_generation(snapshot, account_generation=1)
