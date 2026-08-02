from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from database import document_store
from tests.store_fakes import FakeDocumentStore
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/repair_memory_state_head.py"

HEAD_PATH = "users/u1/memory_state/head"
CONTROL_PATH = "users/u1/memory_state/apply_control"


def load_script():
    spec = importlib.util.spec_from_file_location("repair_memory_state_head", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script()


def _control(uid: str = "u1"):
    return {
        "uid": uid,
        "account_generation": 7,
        "head_commit_id": "canonical-head-7",
        "commit_sequence": 11,
    }


def test_repair_plan_rejects_control_without_trusted_fields(script):
    plan = script.build_state_head_repair_plan(
        uid="u1", head={"current_head_commit_id": "legacy"}, control={"uid": "u1", "account_generation": 7}
    )

    assert plan.status == "blocked_invalid_apply_control"
    assert plan.trusted_fields is None


def test_repair_transaction_preserves_legacy_fields_and_restores_v3_trusted_head(script, monkeypatch):
    store = FakeDocumentStore()
    store.set(
        HEAD_PATH,
        {
            "current_head_commit_id": "legacy-ledger-head",
            "projection_version": 1,
        },
    )
    store.set(CONTROL_PATH, _control())

    plan = script.apply_state_head_repair(store, uid="u1")

    assert plan.status == "repair_required"
    assert plan.write_mode == "update"
    state_head = store.get(HEAD_PATH).to_dict()
    assert state_head["current_head_commit_id"] == "legacy-ledger-head"
    assert state_head["projection_version"] == 1
    assert state_head["schema_version"] == 1
    assert state_head["uid"] == "u1"
    assert state_head["source"] == "memory_state_head"
    assert state_head["account_generation"] == 7
    assert state_head["head_commit_id"] == "canonical-head-7"
    assert state_head["commit_sequence"] == 11

    # ``read_memory_v3_trusted_account_generation`` reads via ``document_store`` (the neutral port,
    # ADR-0022). Point it at the same fake store so the post-apply V3 trust check sees the repair.
    monkeypatch.setattr(document_store, "_store", lambda: store)

    trusted = read_memory_v3_trusted_account_generation(uid="u1")
    assert trusted.read_error_reason is None
    assert trusted.account_generation == 7


def test_repair_transaction_creates_missing_state_head_from_trusted_apply_control(script):
    store = FakeDocumentStore()
    store.set(CONTROL_PATH, _control())

    plan = script.apply_state_head_repair(store, uid="u1")

    assert plan.status == "repair_required"
    assert plan.write_mode == "create"
    assert store.get(HEAD_PATH).to_dict()["head_commit_id"] == "canonical-head-7"


def test_repair_transaction_is_noop_for_an_already_trusted_head(script):
    trusted_head = {
        **_control(),
        "schema_version": 1,
        "source": "memory_state_head",
        "current_head_commit_id": "legacy-ledger-head",
    }
    store = FakeDocumentStore()
    store.set(HEAD_PATH, trusted_head)
    store.set(CONTROL_PATH, _control())

    plan = script.apply_state_head_repair(store, uid="u1")

    assert plan.status == "already_trusted"
    assert store.get(HEAD_PATH).to_dict() == trusted_head


def test_inspect_reports_repair_required_without_writing(script):
    store = FakeDocumentStore()
    store.set(HEAD_PATH, {"current_head_commit_id": "legacy"})
    store.set(CONTROL_PATH, _control())

    plan = script.inspect_state_head_repair(store, uid="u1")

    assert plan.status == "repair_required"
    assert plan.write_mode == "update"
    # Inspect is a dry-run: the head document must be untouched.
    assert store.get(HEAD_PATH).to_dict() == {"current_head_commit_id": "legacy"}


def test_repair_is_idempotent_across_repeated_apply(script):
    store = FakeDocumentStore()
    store.set(HEAD_PATH, {"current_head_commit_id": "legacy"})
    store.set(CONTROL_PATH, _control())

    first = script.apply_state_head_repair(store, uid="u1")
    assert first.status == "repair_required"
    repaired = store.get(HEAD_PATH).to_dict()
    assert repaired["account_generation"] == 7

    second = script.apply_state_head_repair(store, uid="u1")
    assert second.status == "already_trusted"
    assert store.get(HEAD_PATH).to_dict() == repaired
