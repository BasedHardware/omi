"""Regression: list_candidates skips a malformed candidate instead of 500ing the whole list.

CandidateRecord.from_storage is model_validate with extra='forbid', so a single legacy or malformed
candidate doc raised ValidationError and crashed the entire GET /v1/candidates list. It is now skipped
(and logged) so the rest of the user's candidates still return. The catch is narrowed to ValidationError
so an unexpected runtime error still surfaces instead of being hidden as a skip. No live services.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.candidates as candidates_db  # noqa: E402


class _Probe(BaseModel):
    x: int


def _fake_candidates_db(stream):
    fake_db = MagicMock()
    q = fake_db.collection.return_value.document.return_value.collection.return_value
    for method in ("where", "order_by", "offset", "limit"):
        getattr(q, method).return_value = q
    q.stream.return_value = stream
    return fake_db


def test_list_candidates_skips_malformed_without_logging_private_input(monkeypatch, caplog):
    secret = "private launch description 8427"
    good = MagicMock()
    good.id = "good"
    good.to_dict.return_value = {"ok": True}
    bad = MagicMock()
    bad.id = "bad"
    bad.to_dict.return_value = {"bad": True, "description": secret, secret: "private-value"}

    def fake_validate(data):
        if data.get("bad"):
            _Probe(x=data)  # a dict is not an int -> raises a genuine pydantic ValidationError
        return data  # stand-in for a parsed CandidateRecord

    monkeypatch.setattr(candidates_db.CandidateRecord, "model_validate", staticmethod(fake_validate))

    with patch.object(candidates_db, "db", _fake_candidates_db([good, bad])):
        result = candidates_db.list_candidates("u1")

    assert result == [{"ok": True}]  # malformed candidate skipped, good one kept
    assert "bad" in caplog.text
    assert "validation_types=" in caplog.text
    assert secret not in caplog.text


def test_list_candidates_does_not_swallow_unexpected_error(monkeypatch):
    # An unexpected (non-validation) error must propagate, not be hidden as a skipped candidate.
    good = MagicMock()
    good.id = "x"
    good.to_dict.return_value = {"ok": True}

    def boom(_data):
        raise RuntimeError("unexpected parsing failure")

    monkeypatch.setattr(candidates_db.CandidateRecord, "model_validate", staticmethod(boom))

    with patch.object(candidates_db, "db", _fake_candidates_db([good])):
        with pytest.raises(RuntimeError):
            candidates_db.list_candidates("u1")
