"""database.candidates.get_candidate returns None on a malformed candidate doc instead of 500ing.

get_candidate built CandidateRecord.from_storage(_snapshot_dict(snapshot)) with no try/except, so one
legacy or schema-drifted candidate doc raised ValidationError and 500'd GET /v1/candidates/{id} (and
the staged-task read paths that fetch a candidate). The sibling list_candidates already skips such a
doc; get_candidate now does the same and returns None (the router maps None -> 404). database.candidates
is light (module-level db proxy), so the test drives it directly.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, ValidationError

import database.candidates as candidates


class _Probe(BaseModel):
    x: int


def _a_validation_error() -> ValidationError:
    try:
        _Probe.model_validate({})  # missing required field -> a real ValidationError
    except ValidationError as exc:
        return exc
    raise AssertionError('expected a ValidationError')


def _snap(exists, data=None, doc_id='c1'):
    s = MagicMock()
    s.exists = exists
    s.id = doc_id
    s.to_dict.return_value = data
    return s


def _patch_db(monkeypatch, snapshot):
    fake = MagicMock()
    for attr in ('collection', 'document'):
        getattr(fake, attr).return_value = fake
    fake.get.return_value = snapshot
    monkeypatch.setattr(candidates, 'db', fake)


def test_get_candidate_skips_malformed(monkeypatch):
    err = _a_validation_error()

    def raise_err(data):
        raise err

    monkeypatch.setattr(candidates.CandidateRecord, 'from_storage', staticmethod(raise_err))
    _patch_db(monkeypatch, _snap(True, {'bad': 'doc'}))
    assert candidates.get_candidate('u1', 'c1') is None  # malformed -> None (router 404s), not a 500


def test_get_candidate_missing_returns_none(monkeypatch):
    _patch_db(monkeypatch, _snap(False))
    assert candidates.get_candidate('u1', 'c1') is None


def test_get_candidate_unexpected_error_propagates(monkeypatch):
    # Only ValidationError is swallowed; an unexpected error must surface, not be hidden as a skip.
    def boom(data):
        raise RuntimeError('unexpected')

    monkeypatch.setattr(candidates.CandidateRecord, 'from_storage', staticmethod(boom))
    _patch_db(monkeypatch, _snap(True, {'x': 1}))
    with pytest.raises(RuntimeError):
        candidates.get_candidate('u1', 'c1')
