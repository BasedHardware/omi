"""Regression: list_candidates skips a malformed candidate instead of 500ing the whole list.

CandidateRecord.from_storage is model_validate with extra='forbid', so a single legacy or malformed
candidate doc raised ValidationError and crashed the entire GET /v1/candidates list. It is now skipped
(and logged) so the rest of the user's candidates still return. The catch is narrowed to ValidationError
so an unexpected runtime error still surfaces instead of being hidden as a skip. No live services.
"""

import os

import pytest
from pydantic import BaseModel, ValidationError

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.candidates as candidates_db  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


class _Probe(BaseModel):
    x: int


def _store_with(monkeypatch, docs):
    """Seed a FakeDocumentStore with candidate docs and route ``list_candidates`` through it."""
    store = FakeDocumentStore()
    for doc_id, data in docs:
        store.set(f"users/u1/candidates/{doc_id}", data)
    monkeypatch.setattr(candidates_db, "_store", lambda: store)
    return store


def test_list_candidates_skips_malformed_without_logging_private_input(monkeypatch, caplog):
    secret = "private launch description 8427"

    def fake_validate(data):
        if data.get("bad"):
            _Probe(x=data)  # a dict is not an int -> raises a genuine pydantic ValidationError
        return data  # stand-in for a parsed CandidateRecord

    monkeypatch.setattr(candidates_db.CandidateRecord, "model_validate", staticmethod(fake_validate))

    _store_with(
        monkeypatch,
        [
            ("good", {"ok": True}),
            ("bad", {"bad": True, "description": secret, secret: "private-value"}),
        ],
    )
    result = candidates_db.list_candidates("u1")

    assert result == [{"ok": True}]  # malformed candidate skipped, good one kept
    assert "bad" in caplog.text
    assert "validation_types=" in caplog.text
    assert secret not in caplog.text


def test_list_candidates_does_not_swallow_unexpected_error(monkeypatch):
    # An unexpected (non-validation) error must propagate, not be hidden as a skipped candidate.
    def boom(_data):
        raise RuntimeError("unexpected parsing failure")

    monkeypatch.setattr(candidates_db.CandidateRecord, "model_validate", staticmethod(boom))

    _store_with(monkeypatch, [("x", {"ok": True})])
    with pytest.raises(RuntimeError):
        candidates_db.list_candidates("u1")
