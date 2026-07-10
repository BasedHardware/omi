from unittest.mock import MagicMock

import pytest

from database.memory_ledger import HeadConflict
from models.memory_contracts import DurableMemoryPatch
from utils.memory.patch_adapter import (
    apply_memory_patch_to_ledger_state,
    patch_to_ledger_mutations,
    persist_non_active_route_for_patch,
)


def _patch(decision, **overrides):
    payload = {
        "patch_id": f"patch_{decision}",
        "packet_id": "pkt_1",
        "run_id": "memory_test",
        "observed_head_commit_id": "head_0",
        "idempotency_key": f"idem_{decision}",
        "decision": decision,
        "result_status": "active",
        "evidence_ids": ["ev_1"],
        "evidence_refs": [{"evidence_id": "ev_1", "quote": "I want automatic memory capture."}],
        "target_memory_id": "mem_1" if decision in {"add_evidence", "update", "merge", "skip_duplicate"} else None,
        "memory_text": "User prefers automatic memory capture.",
        "predicate": "prefers",
        "arguments": {"object": "automatic memory capture"},
        "rationale": "direct quote",
    }
    payload.update(overrides)
    return DurableMemoryPatch(**payload)


def test_memory_patch_adapter_adds_fact_with_deterministic_fact_and_evidence_ids():
    patch = _patch("add")

    mutations = patch_to_ledger_mutations(patch)

    assert mutations[0]["type"] == "add_fact"
    fact = mutations[0]["fact"]
    assert fact["id"].startswith("mem_")
    assert fact["content"] == "User prefers automatic memory capture."
    assert fact["predicate"] == "prefers"
    assert fact["evidence_set"][0]["evidence_id"] == "ev_1"
    assert fact["idempotency_key"] == "idem_add"


def test_memory_patch_adapter_add_evidence_dedupes_by_evidence_id():
    patch = _patch(
        "add_evidence",
        evidence_ids=["ev_1", "ev_1"],
        evidence_refs=[
            {"evidence_id": "ev_1", "quote": "I want automatic memory capture."},
            {"evidence_id": "ev_1", "quote": "duplicate"},
        ],
    )

    mutations = patch_to_ledger_mutations(patch)

    assert len(mutations) == 1
    assert mutations[0]["type"] == "add_evidence"
    assert mutations[0]["fact_id"] == "mem_1"
    assert mutations[0]["evidence"]["evidence_id"] == "ev_1"


def test_memory_patch_adapter_update_adds_new_fact_and_supersedes_target():
    patch = _patch("update", target_memory_id="mem_old", new_memory_id="mem_new")

    mutations = patch_to_ledger_mutations(patch)

    assert [mutation["type"] for mutation in mutations] == ["add_fact", "supersede_fact"]
    assert mutations[0]["fact"]["id"] == "mem_new"
    assert mutations[1]["fact_id"] == "mem_old"
    assert mutations[1]["by"] == "mem_new"


def test_memory_patch_adapter_skip_duplicate_has_no_ledger_mutations():
    assert patch_to_ledger_mutations(_patch("skip_duplicate", target_memory_id="mem_1")) == []


def test_memory_patch_adapter_persists_non_active_patch_decisions_through_route_store(monkeypatch):
    captured = []

    def fake_persist(outcome, *, db_client=None):
        captured.append((outcome, db_client))
        return outcome

    fake_db = object()
    import utils.memory.patch_adapter as adapter

    monkeypatch.setattr(adapter, "persist_non_active_route_outcome", fake_persist)
    patch = _patch(
        "review",
        result_status="review",
        evidence_refs=[
            {"evidence_id": "ev_1", "source_id": "conv_1", "source_type": "conversation"},
            {"evidence_id": "ev_2", "source_id": "conv_1", "source_type": "conversation"},
        ],
        evidence_ids=["ev_1", "ev_2"],
        rationale="low confidence conflict needs human review",
    )

    persisted = persist_non_active_route_for_patch("u1", patch, audit_metadata={"actor": "unit"}, db_client=fake_db)

    assert persisted is captured[0][0]
    outcome, used_db = captured[0]
    assert used_db is fake_db
    assert outcome.uid == "u1"
    assert outcome.route == "review"
    assert outcome.idempotency_key == "memory_patch:idem_review"
    assert outcome.source_ids == ["conv_1", "ev_1", "ev_2", "pkt_1"]
    assert outcome.reason == "low confidence conflict needs human review"
    assert outcome.run_id == "memory_test"
    assert outcome.patch_id == "patch_review"
    assert outcome.audit_metadata["actor"] == "unit"
    assert outcome.audit_metadata["decision"] == "review"
    assert outcome.audit_metadata["result_status"] == "review"
    assert outcome.audit_metadata["route_store_source"] == "memory_patch_adapter"


def test_memory_patch_adapter_does_not_persist_active_patch_decisions(monkeypatch):
    import utils.memory.patch_adapter as adapter

    persist_mock = MagicMock()
    monkeypatch.setattr(adapter, "persist_non_active_route_outcome", persist_mock)

    assert persist_non_active_route_for_patch("u1", _patch("add")) is None
    persist_mock.assert_not_called()


def test_memory_patch_adapter_repeat_apply_is_idempotent_and_checks_head():
    patch = _patch("add")
    state = {"current_head_commit_id": "head_0"}
    commits = {}

    first = apply_memory_patch_to_ledger_state(state, commits, patch)
    second = apply_memory_patch_to_ledger_state(state, commits, patch)

    assert first["applied"] is True
    assert second["applied"] is False
    assert len(commits) == 1


def test_memory_patch_adapter_rejects_stale_head():
    patch = _patch("add", observed_head_commit_id="stale_head")
    state = {"current_head_commit_id": "head_0"}

    with pytest.raises(HeadConflict):
        apply_memory_patch_to_ledger_state(state, {}, patch)
