"""Firestore emulator harness wiring smoke tests (consolidated)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.test_firestore_security_rules import MEMORY_PROTECTED_COLLECTIONS

_REPO_ROOT = Path(__file__).resolve().parents[2].parent
_PYTHON_APPLY_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "firestore_python_apply_emulator_test.py"
_KNOWLEDGE_LEDGER_MIGRATION_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "knowledge_ledger_migration_emulator_test.py"
_KNOWLEDGE_LEDGER_WRITER_TRANSITION_SCRIPT = (
    _REPO_ROOT / "backend" / "scripts" / "knowledge_ledger_writer_transition_emulator_test.py"
)
_KNOWLEDGE_LEDGER_CORRECTION_SCRIPT = (
    _REPO_ROOT / "backend" / "scripts" / "knowledge_ledger_correction_emulator_test.py"
)


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
        "MEMORY_ENABLED=on npx --no-install firebase emulators:exec --only firestore --project demo-memory "
        '"backend/.venv/bin/python backend/scripts/firestore_python_apply_emulator_test.py"'
    )
    assert package["scripts"]["test:memory-v3-state-head:emulator"] == (
        "MEMORY_ENABLED=on npx --no-install firebase emulators:exec --only firestore --project demo-memory "
        '"node backend/scripts/firestore_rules_emulator_test.mjs && '
        'PYTHONPATH=backend backend/.venv/bin/python backend/scripts/firestore_python_apply_emulator_test.py"'
    )


def test_knowledge_ledger_migration_emulator_harness_is_wired_to_real_migration() -> None:
    assert _KNOWLEDGE_LEDGER_MIGRATION_SCRIPT.exists(), "missing knowledge-ledger migration emulator harness"
    script = _KNOWLEDGE_LEDGER_MIGRATION_SCRIPT.read_text()
    for required in (
        "plan_ledger_migration",
        "apply_ledger_migration_plan",
        "FIRESTORE_EMULATOR_HOST",
        "render_profile",
        "read_ledger_migration_completion",
        "memory_operations",
        "memory_commits",
        "memory_state_head",
        "memory_outbox",
        "PASS: Firestore emulator migration proof",
    ):
        assert required in script

    package = json.loads((_REPO_ROOT / "package.json").read_text())
    command = package["scripts"]["test:memory-knowledge-ledger-migration:emulator"]
    assert command.startswith("MEMORY_ENABLED=on npx --no-install firebase emulators:exec")
    assert "backend/.venv/bin/python backend/scripts/knowledge_ledger_migration_emulator_test.py" in command


def test_knowledge_ledger_writer_transition_emulator_harness_is_wired_to_real_transition() -> None:
    assert _KNOWLEDGE_LEDGER_WRITER_TRANSITION_SCRIPT.exists(), "missing writer-transition emulator harness"
    script = _KNOWLEDGE_LEDGER_WRITER_TRANSITION_SCRIPT.read_text()
    for required in (
        "FIRESTORE_EMULATOR_HOST",
        "publish_ledger_migration_cutover",
        "rollback_ledger_writer_to_compatibility",
        "read_ledger_migration_completion",
        "knowledge_ledger_writer_transition_receipt",
        "PASS: writer transition emulator proof",
    ):
        assert required in script

    package = json.loads((_REPO_ROOT / "package.json").read_text())
    command = package["scripts"]["test:memory-knowledge-ledger-writer-transition:emulator"]
    assert command.startswith("MEMORY_ENABLED=on npx --no-install firebase emulators:exec")
    assert "backend/.venv/bin/python backend/scripts/knowledge_ledger_writer_transition_emulator_test.py" in command


def test_knowledge_ledger_correction_emulator_harness_is_wired_to_real_service() -> None:
    assert _KNOWLEDGE_LEDGER_CORRECTION_SCRIPT.exists(), "missing knowledge-ledger correction emulator harness"
    script = _KNOWLEDGE_LEDGER_CORRECTION_SCRIPT.read_text()
    for required in (
        "FIRESTORE_EMULATOR_HOST",
        "MemoryService",
        "service.update_content",
        "service.revert_superseded_ledger_fact",
        "explicit_user_correction",
        "explicit_user_revert",
        "memory_operations",
        "memory_commits",
        "memory_outbox",
        "item_revision",
        "tombstone_memory_items_firestore",
        "privacy_race=blocked",
        "PASS: Firestore emulator explicit ledger correction and revert proof",
    ):
        assert required in script

    package = json.loads((_REPO_ROOT / "package.json").read_text())
    assert package["scripts"]["test:memory-knowledge-ledger-correction:emulator"] == (
        "MEMORY_ENABLED=on npx --no-install firebase emulators:exec --only firestore --project demo-memory "
        '"backend/.venv/bin/python backend/scripts/knowledge_ledger_correction_emulator_test.py"'
    )
