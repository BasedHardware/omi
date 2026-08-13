"""database.workstreams list endpoints skip a malformed doc instead of 500ing the whole page.

list_artifact_descriptors and list_continuation_checkpoints validated each Firestore doc with no
try/except, so one malformed/legacy doc raised ValidationError and 500'd the whole list
(GET /v1/workstreams/{id}/artifacts and /checkpoints). This mirrors the skip-malformed guard the
sibling list endpoints already carry. database.workstreams is light (firestore_client injectable),
so the test drives it directly with a fake client.

The same gap existed in the get_goal_detail / get_workstream_detail tasks loops (per-item
ActionItemResponse.model_validate with no guard -> 500 on GET /v1/goals/{id}/detail and
GET /v1/workstreams/{id}); both now route tasks through the shared _task_responses_from_snapshots
helper, which is exercised directly here.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

import database.workstreams as ws


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
    snap.to_dict.return_value = doc
    return snap


def _fake_client(snapshots):
    fake = MagicMock()
    for attr in ('collection', 'document', 'order_by', 'limit', 'where'):
        getattr(fake, attr).return_value = fake
    fake.stream.return_value = snapshots
    return fake


@pytest.fixture(autouse=True)
def _direct_snapshot_dict(monkeypatch):
    # Bypass the real _snapshot_dict decrypt/normalize; the test controls the dicts directly.
    monkeypatch.setattr(ws, '_snapshot_dict', lambda snap: snap.to_dict())


def _stub_validate(monkeypatch, model_name):
    err = _a_validation_error()

    def fake_validate(doc):
        if doc.get('_bad'):
            raise err
        return doc

    monkeypatch.setattr(getattr(ws, model_name), 'model_validate', staticmethod(fake_validate))


def test_list_artifact_descriptors_skips_malformed(monkeypatch):
    _stub_validate(monkeypatch, 'ArtifactDescriptor')
    client = _fake_client([_snapshot({'id': 'a1'}), _snapshot({'id': 'bad', '_bad': True}), _snapshot({'id': 'a2'})])
    result = ws.list_artifact_descriptors('u1', 'w1', firestore_client=client)
    assert result == [{'id': 'a1'}, {'id': 'a2'}]


def test_list_continuation_checkpoints_skips_malformed(monkeypatch):
    _stub_validate(monkeypatch, 'ContinuationCheckpoint')
    client = _fake_client([_snapshot({'id': 'c1'}), _snapshot({'id': 'bad', '_bad': True})])
    result = ws.list_continuation_checkpoints('u1', 'w1', firestore_client=client)
    assert result == [{'id': 'c1'}]


def test_unexpected_error_is_not_swallowed(monkeypatch):
    # Only ValidationError is skipped; an unexpected error must propagate, not be hidden as a skip.
    def boom(doc):
        raise RuntimeError('unexpected')

    monkeypatch.setattr(ws.ArtifactDescriptor, 'model_validate', staticmethod(boom))
    client = _fake_client([_snapshot({'id': 'a1'})])
    with pytest.raises(RuntimeError):
        ws.list_artifact_descriptors('u1', 'w1', firestore_client=client)


def test_task_responses_from_snapshots_skips_malformed(monkeypatch):
    _stub_validate(monkeypatch, 'ActionItemResponse')
    snaps = [_snapshot({'id': 't1'}), _snapshot({'id': 'bad', '_bad': True}), _snapshot({'id': 't2'})]
    result = ws._task_responses_from_snapshots(snaps, context='goal_detail')
    assert result == [{'id': 't1'}, {'id': 't2'}]  # one malformed task must not 500 the detail page


def test_task_responses_from_snapshots_skips_deleted(monkeypatch):
    _stub_validate(monkeypatch, 'ActionItemResponse')
    snaps = [_snapshot({'id': 't1'}), _snapshot({'id': 't2', 'deleted': True})]
    result = ws._task_responses_from_snapshots(snaps, context='workstream_detail')
    assert result == [{'id': 't1'}]  # a soft-deleted task is filtered before validation


def test_task_responses_unexpected_error_propagates(monkeypatch):
    # Only ValidationError is skipped; an unexpected error must surface, not be hidden as a skip.
    def boom(doc):
        raise RuntimeError('unexpected')

    monkeypatch.setattr(ws.ActionItemResponse, 'model_validate', staticmethod(boom))
    with pytest.raises(RuntimeError):
        ws._task_responses_from_snapshots([_snapshot({'id': 't1'})], context='goal_detail')


def test_workstream_presentation_read_skips_malformed_snapshot(monkeypatch):
    _stub_validate(monkeypatch, 'Workstream')
    snapshot = _snapshot({'id': 'bad', '_bad': True})
    snapshot.exists = True
    client = _fake_client([])
    client.get.return_value = snapshot

    with patch('database.read_boundary.record_fallback') as fallback:
        result = ws.get_workstream('u1', 'bad', firestore_client=client)

    assert result is None
    fallback.assert_called_once()
