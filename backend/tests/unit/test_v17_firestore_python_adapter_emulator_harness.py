import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend" / "scripts" / "v17_firestore_python_apply_emulator_test.py"
PACKAGE_JSON = ROOT / "package.json"


def test_python_apply_adapter_emulator_harness_is_wired_to_real_adapter():
    assert SCRIPT.exists(), "missing Python Firestore apply adapter emulator harness"
    script = SCRIPT.read_text()
    assert "apply_long_term_patch_firestore" in script
    assert "FIRESTORE_EMULATOR_HOST" in script
    assert "google.cloud.firestore" in script
    assert "memory_items" in script
    assert "memory_outbox" in script

    package = json.loads(PACKAGE_JSON.read_text())
    assert package["scripts"]["test:v17-firestore-python-apply:emulator"] == (
        "firebase emulators:exec --only firestore --project demo-v17-memory "
        '"python3 backend/scripts/v17_firestore_python_apply_emulator_test.py"'
    )
