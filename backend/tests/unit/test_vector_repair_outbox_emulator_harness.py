import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend" / "scripts" / "vector_repair_outbox_emulator_test.py"
PACKAGE_JSON = ROOT / "package.json"


def test_vector_repair_outbox_emulator_harness_is_wired_to_real_writer_and_rules_gate():
    assert SCRIPT.exists(), "missing memory vector repair outbox emulator harness"
    script = SCRIPT.read_text()
    assert "write_vector_repair_purge_outbox_records" in script
    assert "build_vector_repair_purge_outbox_records" in script
    assert "FIRESTORE_EMULATOR_HOST" in script
    assert "google.cloud.firestore" in script
    assert "users/{uid}/memory_outbox/{record_id}" in script
    assert "idempotent" in script
    assert "write failure propagated" in script

    package = json.loads(PACKAGE_JSON.read_text())
    assert package["scripts"]["test:memory-vector-repair-outbox:emulator"] == (
        "firebase emulators:exec --only firestore --project demo-memory "
        '"python3 backend/scripts/vector_repair_outbox_emulator_test.py"'
    )
    assert package["scripts"]["test:memory-vector-repair-outbox-rules:emulator"] == (
        "firebase emulators:exec --only firestore --project demo-memory "
        '"node backend/scripts/firestore_rules_emulator_test.mjs"'
    )
    assert package["scripts"]["test:memory-vector-repair-outbox-lease:emulator"] == (
        "firebase emulators:exec --only firestore --project demo-memory "
        '"python3 backend/scripts/vector_repair_outbox_lease_emulator_test.py"'
    )


def test_vector_repair_outbox_lease_emulator_harness_is_wired_to_transactional_reader():
    script = ROOT / "backend" / "scripts" / "vector_repair_outbox_lease_emulator_test.py"

    assert script.exists(), "missing memory vector repair outbox lease contention emulator harness"
    content = script.read_text()
    assert "lease_vector_repair_purge_outbox_records" in content
    assert "ThreadPoolExecutor" in content
    assert "FIRESTORE_EMULATOR_HOST" in content
    assert "at most one" in content
    assert "PASS: memory vector repair/purge outbox transactional lease contention" in content
