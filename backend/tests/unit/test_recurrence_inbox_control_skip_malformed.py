"""Regression: a malformed task_intelligence_control doc must fail closed in the recurrence transaction.

recurrence_inbox._validate_generation loads the per-user control document inside an idempotent
transaction. A malformed control must not be silently treated as a default: it now parses strictly
and translates the typed boundary error to the existing caller-facing generation-mismatch outcome.
"""

import pytest
from unittest.mock import patch

import database.recurrence_inbox as recurrence_inbox_db
import database.read_boundary as read_boundary
from database.recurrence_inbox import _validate_generation, RecurrenceGenerationMismatchError
from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort


@pytest.fixture(autouse=True)
def canonical_user(monkeypatch):
    set_canonical_cohort(monkeypatch, 'u1')


class _FakeSnapshot:
    def __init__(self, *, exists, data):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


def test_malformed_control_is_treated_as_generation_mismatch_without_fail_open():
    # extra='forbid': an unknown persisted field fails to load with ValidationError.
    snapshot = _FakeSnapshot(
        exists=True,
        data={'workflow_mode': 'write', 'account_generation': 1, 'legacy_extra': True},
    )

    with patch.object(read_boundary, 'record_fallback') as fallback:
        with pytest.raises(RecurrenceGenerationMismatchError, match='malformed'):
            _validate_generation(snapshot, account_generation=1, uid='u1')
    fallback.assert_not_called()


def test_valid_matching_control_passes():
    snapshot = _FakeSnapshot(exists=True, data={'workflow_mode': 'write', 'account_generation': 1})
    assert _validate_generation(snapshot, account_generation=1, uid='u1') is None


def test_unexpected_error_propagates(monkeypatch):
    snapshot = _FakeSnapshot(exists=True, data={'workflow_mode': 'write', 'account_generation': 1})

    def _boom(*_args, **_kwargs):
        raise RuntimeError('unexpected non-validation failure')

    # The guard catches only ValidationError; anything else must still surface.
    monkeypatch.setattr(recurrence_inbox_db.TaskWorkflowControl, 'model_validate', _boom)

    with pytest.raises(RuntimeError, match='unexpected non-validation failure'):
        _validate_generation(snapshot, account_generation=1, uid='u1')
