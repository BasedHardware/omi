from pathlib import Path

MEMORY_PROTECTED_COLLECTIONS = [
    "users/{uid}/memory_items/{memory_id}",
    "users/{uid}/memory_operations/{operation_id}",
    "users/{uid}/memory_outbox/{event_id}",
    "users/{uid}/memory_control/{doc_id}",
    "users/{uid}/memory_state/{doc_id}",
    "users/{uid}/memory_commits/{commit_id}",
    "users/{uid}/memory_evidence/{evidence_id}",
]

REQUIRED_TERMS = [
    "Admin SDK",
    "server-owned",
    "Firestore Security Rules",
    "clients denied",
    "service account",
    "roles/datastore.user",
    "least privilege",
    "no client SDK writes",
    "rollback",
    "Firebase emulator",
    "Java",
    "not a cloud IAM validation",
]


def test_memory_firestore_iam_deployment_doc_covers_service_account_boundary_and_gate():
    root = Path(__file__).resolve().parents[2].parent
    doc_path = root / "docs" / "epics" / "memory_firestore_iam_deployment.md"

    assert doc_path.exists()
    doc = doc_path.read_text()

    for collection_path in MEMORY_PROTECTED_COLLECTIONS:
        assert collection_path in doc
    for required_term in REQUIRED_TERMS:
        assert required_term in doc

    assert "MEMORY_MODE=off" in doc
    assert "MEMORY_MODE=write" in doc
    assert "MEMORY_MODE=read" in doc
