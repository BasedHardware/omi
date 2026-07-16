"""database.task_recommendations._decision_records skips a malformed decision record, not 500s.

get_decisions built [DecisionRecord.model_validate(r) for r in raw_records] with no guard, inside a
Firestore transaction. DecisionRecord is extra='forbid', so a legacy or schema-drifted stored audit
record raised ValidationError and 500'd the recommendation read (utils/task_intelligence/
recommendations.py get_decisions callers). The decode is now the pure _decision_records helper, which
skips a malformed record and sorts by subject_id; the test drives that helper directly.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

import database.task_recommendations as tr


class _Probe(BaseModel):
    x: int


def _a_validation_error() -> ValidationError:
    try:
        _Probe.model_validate({})  # missing required field -> a real ValidationError
    except ValidationError as exc:
        return exc
    raise AssertionError('expected a ValidationError')


def _stub_validate(monkeypatch):
    err = _a_validation_error()

    def fake_validate(record):
        if record.get('_bad'):
            raise err
        return SimpleNamespace(subject_id=record['subject_id'])

    monkeypatch.setattr(tr.DecisionRecord, 'model_validate', staticmethod(fake_validate))


def test_decision_records_skips_malformed_and_sorts(monkeypatch):
    _stub_validate(monkeypatch)
    raw = [{'subject_id': 'b'}, {'_bad': True, 'subject_id': 'x'}, {'subject_id': 'a'}]
    out = tr._decision_records(raw, 'eval1')
    assert [r.subject_id for r in out] == ['a', 'b']  # malformed skipped, remainder sorted by subject_id


def test_decision_records_unexpected_error_propagates(monkeypatch):
    # Only ValidationError is skipped; an unexpected error must surface, not be hidden as a skip.
    def boom(record):
        raise RuntimeError('unexpected')

    monkeypatch.setattr(tr.DecisionRecord, 'model_validate', staticmethod(boom))
    with pytest.raises(RuntimeError):
        tr._decision_records([{'subject_id': 'a'}], 'eval1')
