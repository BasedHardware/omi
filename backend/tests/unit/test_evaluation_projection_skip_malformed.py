"""database.task_recommendations._valid_evaluation_projection treats a malformed projection as absent.

get_evaluation_projection validated the stored projection with an unguarded
WhatMattersNowProjection.model_validate(raw_projection). A legacy or schema-drifted projection doc
raised ValidationError and 500'd the recommendation read (utils/task_intelligence/recommendations.py).
The validate plus freshness checks now live in the pure _valid_evaluation_projection helper, which
returns None on a malformed, non-dict, stale, or id-mismatched projection, consistent with the
reader's other None returns.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _stub_validate(monkeypatch):
    err = _a_validation_error()

    def fake_validate(raw):
        if raw.get('_bad'):
            raise err
        return SimpleNamespace(
            evaluation_id=raw.get('evaluation_id', 'eval1'),
            expires_at=raw.get('expires_at', NOW + timedelta(hours=1)),
        )

    monkeypatch.setattr(tr.WhatMattersNowProjection, 'model_validate', staticmethod(fake_validate))


def test_valid_projection_returned(monkeypatch):
    _stub_validate(monkeypatch)
    out = tr._valid_evaluation_projection({'evaluation_id': 'eval1'}, 'eval1', NOW)
    assert out is not None and out.evaluation_id == 'eval1'


def test_malformed_projection_is_none(monkeypatch):
    _stub_validate(monkeypatch)
    # ValidationError from a legacy/schema-drifted doc -> None, not a 500.
    assert tr._valid_evaluation_projection({'_bad': True}, 'eval1', NOW) is None


def test_non_dict_projection_is_none():
    assert tr._valid_evaluation_projection(None, 'eval1', NOW) is None


def test_mismatched_or_expired_is_none(monkeypatch):
    _stub_validate(monkeypatch)
    assert tr._valid_evaluation_projection({'evaluation_id': 'other'}, 'eval1', NOW) is None  # id mismatch
    expired = {'evaluation_id': 'eval1', 'expires_at': NOW - timedelta(hours=1)}
    assert tr._valid_evaluation_projection(expired, 'eval1', NOW) is None  # stale
