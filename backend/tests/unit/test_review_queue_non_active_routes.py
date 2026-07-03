"""review_queue.resolve_review_conflict persists non-active-route outcomes and skip-route drops.

``database.review_queue`` binds its sibling submodule imports (``memories``, ``memory_ledger``,
``short_term_memories``) at import time, and ``resolve_review_conflict`` calls into them at
runtime (e.g. ``short_term_db.mark_consolidated``). The tests exercise only ``review_queue``'s
own logic and must not touch Firestore, so those sibling refs are replaced with no-op fakes for
the duration of the module. This is the sanctioned Tier-2 "fake must precede import" case: see
backend/docs/test_isolation.md and testing.import_isolation.load_module_fresh.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

from database.memory_non_active_routes import NonActiveRoute

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def review_queue():
    """Load a fresh database.review_queue against no-op sibling submodule fakes."""
    fakes = {
        "database._client": AutoMockModule("database._client"),
        "database.memories": AutoMockModule("database.memories"),
        "database.memory_ledger": AutoMockModule("database.memory_ledger"),
        "database.short_term_memories": AutoMockModule("database.short_term_memories"),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.review_queue",
            os.path.join(str(_BACKEND), "database", "review_queue.py"),
        )
        yield module


class _Doc:
    def __init__(self):
        self.updates = []

    def update(self, data):
        self.updates.append(data)


class _Collection:
    def __init__(self, doc):
        self._doc = doc

    def document(self, doc_id):
        return self._doc


class _UserDoc:
    def __init__(self, doc):
        self._doc = doc

    def collection(self, name):
        return _Collection(self._doc)


class _Db:
    def __init__(self, doc):
        self._doc = doc

    def collection(self, name):
        return _Collection(_UserDoc(self._doc))


def _item(**overrides):
    item = {
        "review_id": "review_1",
        "fact_id": "fact_1",
        "candidate": {"id": "fact_1", "evidence": [{"evidence_id": "ev_1", "source_id": "conv_1"}]},
        "conflict_with": ["fact_old"],
        "status": "pending",
        "source_commit_id": "commit_src",
        "source_short_term_id": "stm_1",
        "veracity": 0.2,
    }
    item.update(overrides)
    return item


def test_review_queue_reject_persists_non_active_route_store_outcome(review_queue, monkeypatch):
    captured = []
    doc = _Doc()

    def fake_persist(outcome):
        captured.append(outcome)
        return outcome

    monkeypatch.setattr(review_queue, "db", _Db(doc))
    monkeypatch.setattr(review_queue, "get_review_conflict", lambda uid, review_id: _item())
    monkeypatch.setattr(
        review_queue,
        "append_resolution_commit",
        lambda uid, item, decision, correction, mutations: {"commit": {"commit_id": "commit_reject"}},
    )
    monkeypatch.setattr(review_queue, "record_correction", lambda uid, **kwargs: {"correction_id": "correction_1"})
    monkeypatch.setattr(review_queue.short_term_db, "mark_consolidated", MagicMock())
    monkeypatch.setattr(review_queue, "persist_non_active_route_outcome", fake_persist)

    result = review_queue.resolve_review_conflict("u1", "review_1", "reject", reason="not true")

    assert result["status"] == "resolved"
    assert len(captured) == 1
    outcome = captured[0]
    assert outcome.uid == "u1"
    assert outcome.route == NonActiveRoute.reject
    assert outcome.idempotency_key == "review_queue:review_1:reject"
    assert outcome.source_ids == ["commit_src", "conv_1", "ev_1", "fact_1", "review_1", "stm_1"]
    assert outcome.reason == "not true"
    assert outcome.run_id == "review_queue:review_1"
    assert outcome.patch_id is None
    assert outcome.audit_metadata["route_store_source"] == "review_queue"
    assert outcome.audit_metadata["decision"] == "reject"
    assert outcome.audit_metadata["resolution_commit_id"] == "commit_reject"


def test_review_queue_timeout_drop_persists_skip_route_without_memory_commit(review_queue, monkeypatch):
    captured = []
    doc = _Doc()
    append_mock = MagicMock(return_value=None)

    monkeypatch.setattr(review_queue, "db", _Db(doc))
    monkeypatch.setattr(review_queue, "get_review_conflict", lambda uid, review_id: _item(veracity=0.1))
    monkeypatch.setattr(review_queue, "append_resolution_commit", append_mock)
    monkeypatch.setattr(
        review_queue, "persist_non_active_route_outcome", lambda outcome: captured.append(outcome) or outcome
    )

    result = review_queue.resolve_review_conflict("u1", "review_1", "timeout", reason="review_timeout")

    assert result["decision"] == "drop"
    append_mock.assert_called_once()
    assert len(captured) == 1
    outcome = captured[0]
    assert outcome.route == NonActiveRoute.skip
    assert outcome.idempotency_key == "review_queue:review_1:drop"
    assert outcome.reason == "review_timeout"
    assert outcome.audit_metadata["decision"] == "drop"
    assert outcome.audit_metadata["route_store_source"] == "review_queue"
