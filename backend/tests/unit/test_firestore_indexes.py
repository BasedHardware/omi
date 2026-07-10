import json
from pathlib import Path


def _index_signature(index):
    return (
        index["collectionGroup"],
        index["queryScope"],
        tuple((field["fieldPath"], field.get("order") or field.get("arrayConfig")) for field in index["fields"]),
    )


def test_memory_firestore_indexes_are_checked_in_for_unified_memory_store():
    root = Path(__file__).resolve().parents[2]
    index_path = root.parent / "firestore.indexes.json"
    assert index_path.exists()
    data = json.loads(index_path.read_text())
    signatures = {_index_signature(idx) for idx in data["indexes"]}
    collection_groups = {idx["collectionGroup"] for idx in data["indexes"]}

    assert "memory_items" in collection_groups
    assert "memory_operations" in collection_groups
    assert "memory_outbox" in collection_groups
    assert "memory_short_term" not in collection_groups
    assert "memory_archive" not in collection_groups

    assert (
        "memory_items",
        "COLLECTION",
        (("tier", "ASCENDING"), ("status", "ASCENDING"), ("updated_at", "DESCENDING"), ("__name__", "ASCENDING")),
    ) in signatures
    assert (
        "memory_items",
        "COLLECTION",
        (("tier", "ASCENDING"), ("status", "ASCENDING"), ("expires_at", "ASCENDING"), ("__name__", "ASCENDING")),
    ) in signatures
    assert (
        "memory_operations",
        "COLLECTION",
        (("status", "ASCENDING"), ("created_at", "DESCENDING"), ("__name__", "ASCENDING")),
    ) in signatures
    assert (
        "memory_outbox",
        "COLLECTION",
        (("status", "ASCENDING"), ("available_at", "ASCENDING"), ("__name__", "ASCENDING")),
    ) in signatures
    assert (
        "memory_outbox",
        "COLLECTION",
        (
            ("event_type", "ASCENDING"),
            ("status", "ASCENDING"),
            ("lease_expires_at", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ),
    ) in signatures
