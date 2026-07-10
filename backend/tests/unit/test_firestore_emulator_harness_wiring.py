"""Firestore emulator harness wiring smoke tests (consolidated)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.test_firestore_security_rules import MEMORY_PROTECTED_COLLECTIONS

_REPO_ROOT = Path(__file__).resolve().parents[2].parent
_PYTHON_APPLY_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "firestore_python_apply_emulator_test.py"


def test_memory_firestore_rules_emulator_harness_is_wired_to_all_protected_collections():
    firebase_config = json.loads((_REPO_ROOT / "firebase.json").read_text())
    package_config = json.loads((_REPO_ROOT / "package.json").read_text())
    harness_path = _REPO_ROOT / "backend" / "scripts" / "firestore_rules_emulator_test.mjs"

    assert harness_path.exists()
    assert firebase_config["firestore"]["rules"] == "firestore.rules"
    assert firebase_config["emulators"]["firestore"]["port"] == 8085

    emulator_script = package_config["scripts"]["test:memory-firestore-rules:emulator"]
    assert "firebase emulators:exec" in emulator_script
    assert "--only firestore" in emulator_script
    assert "backend/scripts/firestore_rules_emulator_test.mjs" in emulator_script

    harness = harness_path.read_text()
    for collection in MEMORY_PROTECTED_COLLECTIONS:
        assert collection in harness
    for assertion in ["assertFails(getDoc", "assertFails(setDoc", "assertFails(updateDoc", "assertFails(deleteDoc"]:
        assert assertion in harness


def test_memory_firestore_rules_emulator_harness_denies_app_key_self_grant_path():
    harness = (_REPO_ROOT / "backend" / "scripts" / "firestore_rules_emulator_test.mjs").read_text()
    package_config = json.loads((_REPO_ROOT / "package.json").read_text())

    assert "users/memory-emulator-user/memory_control/app_key_memory_grants" in harness
    assert "client-self-grant" in harness
    assert "grants.developer_api.apps.client-app.keys.client-key" in harness
    assert "test:memory-app-key-grants-rules:emulator" in package_config["scripts"]
    assert (
        "backend/scripts/firestore_rules_emulator_test.mjs"
        in package_config["scripts"]["test:memory-app-key-grants-rules:emulator"]
    )


def test_memory_firestore_transaction_emulator_harness_is_wired() -> None:
    harness_path = _REPO_ROOT / "backend" / "scripts" / "firestore_transaction_emulator_test.mjs"
    script = harness_path.read_text()
    package_config = json.loads((_REPO_ROOT / "package.json").read_text())

    emulator_script = package_config["scripts"]["test:memory-firestore-transactions:emulator"]

    assert "firebase emulators:exec" in emulator_script
    assert "--only firestore" in emulator_script
    assert "backend/scripts/firestore_transaction_emulator_test.mjs" in emulator_script
    assert ":beginTransaction" in script
    assert ":commit" in script
    assert ":batchGet" in script
    assert "assertConcurrentTransactionContentionSerializesMemoryApply" in script
    assert "MAX_CONTENTION_ROUNDS" in script
    assert "assertNoAttemptDocsWerePartiallyCommitted" in script
    assert "exactly one concurrent apply transaction commits after bounded retry" in script
    assert "memory_state/apply_control" in script
    assert "memory_operations" in script
    assert "memory_items" in script
    assert "memory_outbox" in script
    assert "PASS: Firestore emulator transaction contention serialized memory apply layout" in script


def test_python_apply_adapter_emulator_harness_is_wired_to_real_adapter():
    assert _PYTHON_APPLY_SCRIPT.exists(), "missing Python Firestore apply adapter emulator harness"
    script = _PYTHON_APPLY_SCRIPT.read_text()
    assert "apply_long_term_patch_firestore" in script
    assert "FIRESTORE_EMULATOR_HOST" in script
    assert "google.cloud.firestore" in script
    assert "memory_items" in script
    assert "memory_outbox" in script

    package = json.loads((_REPO_ROOT / "package.json").read_text())
    assert package["scripts"]["test:memory-firestore-python-apply:emulator"] == (
        "firebase emulators:exec --only firestore --project demo-memory "
        '"python3 backend/scripts/firestore_python_apply_emulator_test.py"'
    )
