import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

sys.modules["database._client"] = MagicMock()
sys.modules["database.memories"] = MagicMock()
sys.modules["database.memory_ledger"] = MagicMock()
sys.modules["database.short_term_memories"] = MagicMock()

from database.memory_non_active_routes import NonActiveRoute
from database import review_queue

sys.modules.pop("database.memories", None)
sys.modules.pop("database.memory_ledger", None)
sys.modules.pop("database.short_term_memories", None)


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


def test_review_queue_reject_persists_non_active_route_store_outcome(monkeypatch):
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


def test_review_queue_timeout_drop_persists_skip_route_without_memory_commit(monkeypatch):
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
