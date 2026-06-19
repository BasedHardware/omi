import json
from pathlib import Path

from test_v17_firestore_security_rules import V17_PROTECTED_COLLECTIONS


def test_v17_firestore_rules_emulator_harness_is_wired_to_all_protected_collections():
    root = Path(__file__).resolve().parents[2].parent
    firebase_config = json.loads((root / "firebase.json").read_text())
    package_config = json.loads((root / "package.json").read_text())
    harness_path = root / "backend" / "scripts" / "v17_firestore_rules_emulator_test.mjs"

    assert harness_path.exists()
    assert firebase_config["firestore"]["rules"] == "firestore.rules"
    assert firebase_config["emulators"]["firestore"]["port"] == 8085

    emulator_script = package_config["scripts"]["test:v17-firestore-rules:emulator"]
    assert "firebase emulators:exec" in emulator_script
    assert "--only firestore" in emulator_script
    assert "backend/scripts/v17_firestore_rules_emulator_test.mjs" in emulator_script

    harness = harness_path.read_text()
    for collection in V17_PROTECTED_COLLECTIONS:
        assert collection in harness
    for assertion in ["assertFails(getDoc", "assertFails(setDoc", "assertFails(updateDoc", "assertFails(deleteDoc"]:
        assert assertion in harness


def test_v17_firestore_rules_emulator_harness_denies_app_key_self_grant_path():
    root = Path(__file__).resolve().parents[2].parent
    harness = (root / "backend" / "scripts" / "v17_firestore_rules_emulator_test.mjs").read_text()
    package_config = json.loads((root / "package.json").read_text())

    assert "users/v17-emulator-user/memory_control/v17_app_key_memory_grants" in harness
    assert "client-self-grant" in harness
    assert "grants.developer_api.apps.client-app.keys.client-key" in harness
    assert "test:v17-app-key-grants-rules:emulator" in package_config["scripts"]
    assert (
        "backend/scripts/v17_firestore_rules_emulator_test.mjs"
        in package_config["scripts"]["test:v17-app-key-grants-rules:emulator"]
    )
