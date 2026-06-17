import sys
import types
from unittest.mock import MagicMock

import pytest

google_stub = sys.modules.setdefault('google', types.ModuleType('google'))
cloud_stub = sys.modules.setdefault('google.cloud', types.ModuleType('google.cloud'))
firestore_v1_stub = sys.modules.setdefault('google.cloud.firestore_v1', types.ModuleType('google.cloud.firestore_v1'))
firestore_v1_stub.transactional = lambda func: func
google_stub.cloud = cloud_stub

client_stub = types.ModuleType('database._client')
client_stub.db = MagicMock()
client_stub.document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
sys.modules['database._client'] = client_stub

from database.memory_ledger import HeadConflict
from models.v17_memory_contracts import DurableMemoryPatch
from utils.memory.v17_patch_adapter import apply_v17_patch_to_ledger_state, patch_to_ledger_mutations


def _patch(decision, **overrides):
    payload = {
        "patch_id": f"patch_{decision}",
        "packet_id": "pkt_1",
        "run_id": "v17_test",
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


def test_v17_patch_adapter_adds_fact_with_deterministic_fact_and_evidence_ids():
    patch = _patch("add")

    mutations = patch_to_ledger_mutations(patch)

    assert mutations[0]["type"] == "add_fact"
    fact = mutations[0]["fact"]
    assert fact["id"].startswith("mem_")
    assert fact["content"] == "User prefers automatic memory capture."
    assert fact["predicate"] == "prefers"
    assert fact["evidence_set"][0]["evidence_id"] == "ev_1"
    assert fact["idempotency_key"] == "idem_add"


def test_v17_patch_adapter_add_evidence_dedupes_by_evidence_id():
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


def test_v17_patch_adapter_update_adds_new_fact_and_supersedes_target():
    patch = _patch("update", target_memory_id="mem_old", new_memory_id="mem_new")

    mutations = patch_to_ledger_mutations(patch)

    assert [mutation["type"] for mutation in mutations] == ["add_fact", "supersede_fact"]
    assert mutations[0]["fact"]["id"] == "mem_new"
    assert mutations[1]["fact_id"] == "mem_old"
    assert mutations[1]["by"] == "mem_new"


def test_v17_patch_adapter_skip_duplicate_has_no_ledger_mutations():
    assert patch_to_ledger_mutations(_patch("skip_duplicate", target_memory_id="mem_1")) == []


def test_v17_patch_adapter_repeat_apply_is_idempotent_and_checks_head():
    patch = _patch("add")
    state = {"current_head_commit_id": "head_0"}
    commits = {}

    first = apply_v17_patch_to_ledger_state(state, commits, patch)
    second = apply_v17_patch_to_ledger_state(state, commits, patch)

    assert first["applied"] is True
    assert second["applied"] is False
    assert len(commits) == 1


def test_v17_patch_adapter_rejects_stale_head():
    patch = _patch("add", observed_head_commit_id="stale_head")
    state = {"current_head_commit_id": "head_0"}

    with pytest.raises(HeadConflict):
        apply_v17_patch_to_ledger_state(state, {}, patch)
