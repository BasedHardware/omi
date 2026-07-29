"""database.goals.list_goal_progress_events skips a malformed event instead of 500ing the detail page.

The function validated each Firestore doc with a bare comprehension
`[GoalProgressEvent.model_validate(_snapshot_dict(s)) for s in query.stream()]`, so one malformed or
legacy event doc (GoalProgressEvent is extra='forbid' with required event_id/goal_id/sequence>=1/
kind/summary/created_at) raised ValidationError and 500'd GET /v1/goals/{id}/detail (get_goal_detail
passes this list as progress_events=). Mirrors the skip-malformed guard the sibling workstreams list
loops carry. database.goals is light (firestore_client injectable), so the test drives it directly.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, ValidationError

import database.goals as goals


class _Probe(BaseModel):
    x: int


def _a_validation_error() -> ValidationError:
    try:
        _Probe.model_validate({})  # missing required field -> a real ValidationError
    except ValidationError as exc:
        return exc
    raise AssertionError('expected a ValidationError')


def _snapshot(doc):
    snap = MagicMock()
    snap.id = doc.get('id')
    snap.exists = True
    snap.to_dict.return_value = doc
    return snap


class _FakeStore:
    """Neutral store stub whose query() returns exactly the ordered snapshots under test.

    list_goal_progress_events reads the events collection through ``_store().query(...)`` and hands
    the results to the shared read boundary; the test controls that ordered result directly.
    """

    def __init__(self, snapshots):
        self._snapshots = list(snapshots)

    def query(self, collection, **kwargs):
        return list(self._snapshots)


def _bind_store(monkeypatch, snapshots):
    monkeypatch.setattr(goals, '_store', lambda: _FakeStore(snapshots))


def _stub_validate(monkeypatch):
    err = _a_validation_error()

    def fake_validate(doc):
        if doc.get('_bad'):
            raise err
        return doc

    monkeypatch.setattr(goals.GoalProgressEvent, 'model_validate', staticmethod(fake_validate))


def test_list_goal_progress_events_skips_malformed(monkeypatch):
    _stub_validate(monkeypatch)
    _bind_store(monkeypatch, [_snapshot({'id': 'e1'}), _snapshot({'id': 'bad', '_bad': True}), _snapshot({'id': 'e2'})])
    result = goals.list_goal_progress_events('u1', 'g1')
    assert result == [{'id': 'e1'}, {'id': 'e2'}]  # one malformed event must not 500 the detail page


def test_unexpected_error_is_not_swallowed(monkeypatch):
    # Only ValidationError is skipped; an unexpected error must surface, not be hidden as a skip.
    def boom(doc):
        raise RuntimeError('unexpected')

    monkeypatch.setattr(goals.GoalProgressEvent, 'model_validate', staticmethod(boom))
    _bind_store(monkeypatch, [_snapshot({'id': 'e1'})])
    with pytest.raises(RuntimeError):
        goals.list_goal_progress_events('u1', 'g1')
