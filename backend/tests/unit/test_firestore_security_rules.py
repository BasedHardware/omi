from pathlib import Path


def test_memory_firestore_security_rules_are_checked_in_and_deny_client_bypass_writes():
    root = Path(__file__).resolve().parents[2].parent
    firebase_config = root / "firebase.json"
    rules_path = root / "firestore.rules"

    assert firebase_config.exists()
    assert rules_path.exists()
    assert '"rules": "firestore.rules"' in firebase_config.read_text()

    rules = rules_path.read_text()
    assert "allow read, create, update, delete: if false" in rules
    assert "allow read, write: if false" in rules
