from __future__ import annotations

import json
from pathlib import Path


def test_memory_firestore_transaction_emulator_harness_is_wired() -> None:
    root = Path(__file__).resolve().parents[3]
    harness_path = root / "backend" / "scripts" / "firestore_transaction_emulator_test.mjs"
    package_path = root / "package.json"
    script = harness_path.read_text()
    package_config = json.loads(package_path.read_text())

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
    assert "memory_control/state" in script
    assert "memory_operations" in script
    assert "memory_items" in script
    assert "memory_outbox" in script
    assert "PASS: Firestore emulator transaction contention serialized memory apply layout" in script
