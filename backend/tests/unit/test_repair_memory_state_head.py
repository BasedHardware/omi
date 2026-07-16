from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/repair_memory_state_head.py"


def load_script():
    spec = importlib.util.spec_from_file_location("repair_memory_state_head", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _control(uid: str = "u1"):
    return {
        "uid": uid,
        "account_generation": 7,
        "head_commit_id": "canonical-head-7",
        "commit_sequence": 11,
    }


class _StrictDocumentClient:
    def __init__(self, database):
        self.database = database

    def document(self, path):
        parts = path.split("/")
        assert len(parts) % 2 == 0
        ref = self.database.collection(parts[0]).document(parts[1])
        for index in range(2, len(parts), 2):
            ref = ref.collection(parts[index]).document(parts[index + 1])
        return ref

    def transaction(self):
        return self.database.transaction()


def test_repair_plan_rejects_control_without_trusted_fields():
    script = load_script()

    plan = script.build_state_head_repair_plan(
        uid="u1", head={"current_head_commit_id": "legacy"}, control={"uid": "u1", "account_generation": 7}
    )

    assert plan.status == "blocked_invalid_apply_control"
    assert plan.trusted_fields is None


def test_repair_transaction_preserves_legacy_fields_and_restores_v3_trusted_head():
    script = load_script()
    db = StrictFirestore(
        {
            ("users", "u1", "memory_state", "head"): {
                "current_head_commit_id": "legacy-ledger-head",
                "projection_version": 1,
            },
            ("users", "u1", "memory_state", "apply_control"): _control(),
        }
    )

    client = _StrictDocumentClient(db)
    plan = script._apply_state_head_repair_transaction_body(client.transaction(), client, uid="u1")

    assert plan.status == "repair_required"
    assert plan.write_mode == "update"
    state_head = db.rows[("users", "u1", "memory_state", "head")]
    assert state_head["current_head_commit_id"] == "legacy-ledger-head"
    assert state_head["projection_version"] == 1
    assert state_head["schema_version"] == 1
    assert state_head["uid"] == "u1"
    assert state_head["source"] == "memory_state_head"
    assert state_head["account_generation"] == 7
    assert state_head["head_commit_id"] == "canonical-head-7"
    assert state_head["commit_sequence"] == 11

    trusted = read_memory_v3_trusted_account_generation(uid="u1", db_client=client)
    assert trusted.read_error_reason is None
    assert trusted.account_generation == 7


def test_repair_transaction_creates_missing_state_head_from_trusted_apply_control():
    script = load_script()
    db = StrictFirestore({("users", "u1", "memory_state", "apply_control"): _control()})

    client = _StrictDocumentClient(db)
    plan = script._apply_state_head_repair_transaction_body(client.transaction(), client, uid="u1")

    assert plan.status == "repair_required"
    assert plan.write_mode == "create"
    assert db.rows[("users", "u1", "memory_state", "head")]["head_commit_id"] == "canonical-head-7"


def test_repair_transaction_is_noop_for_an_already_trusted_head():
    script = load_script()
    trusted_head = {
        **_control(),
        "schema_version": 1,
        "source": "memory_state_head",
        "current_head_commit_id": "legacy-ledger-head",
    }
    db = StrictFirestore(
        {
            ("users", "u1", "memory_state", "head"): trusted_head,
            ("users", "u1", "memory_state", "apply_control"): _control(),
        }
    )

    client = _StrictDocumentClient(db)
    plan = script._apply_state_head_repair_transaction_body(client.transaction(), client, uid="u1")

    assert plan.status == "already_trusted"
    assert db.rows[("users", "u1", "memory_state", "head")] == trusted_head


def test_repair_transaction_reads_before_writing_under_strict_firestore_rules():
    script = load_script()
    db = StrictFirestore(
        {
            ("users", "u1", "memory_state", "head"): {"current_head_commit_id": "legacy"},
            ("users", "u1", "memory_state", "apply_control"): _control(),
        }
    )

    client = _StrictDocumentClient(db)
    script._apply_state_head_repair_transaction_body(client.transaction(), client, uid="u1")

    assert db.rows[("users", "u1", "memory_state", "head")]["account_generation"] == 7
