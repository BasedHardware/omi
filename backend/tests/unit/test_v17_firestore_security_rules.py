from pathlib import Path

V17_PROTECTED_COLLECTIONS = [
    "memory_items",
    "memory_operations",
    "memory_outbox",
    "memory_control",
    "memory_state",
    "memory_commits",
    "memory_evidence",
    "short_term_lifecycle_transitions",
]


def test_v17_firestore_security_rules_are_checked_in_and_deny_client_bypass_writes():
    root = Path(__file__).resolve().parents[2].parent
    firebase_config = root / "firebase.json"
    rules_path = root / "firestore.rules"

    assert firebase_config.exists()
    assert rules_path.exists()
    assert '"rules": "firestore.rules"' in firebase_config.read_text()

    rules = rules_path.read_text()
    assert "function isServerOwnedV17MemoryPath" in rules
    assert "allow read, create, update, delete: if false" in rules
    assert "allow read: if isServerOwnedV17MemoryPath" not in rules
    for collection in V17_PROTECTED_COLLECTIONS:
        assert collection in rules
