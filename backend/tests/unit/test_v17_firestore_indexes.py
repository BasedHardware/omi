import json
from pathlib import Path


def test_v17_firestore_indexes_are_checked_in_for_unified_memory_store():
    root = Path(__file__).resolve().parents[2]
    index_path = root.parent / "firestore.indexes.json"
    assert index_path.exists()
    data = json.loads(index_path.read_text())
    collection_groups = {idx["collectionGroup"] for idx in data["indexes"]}

    assert "memory_items" in collection_groups
    assert "memory_operations" in collection_groups
    assert "memory_outbox" in collection_groups
    assert "memory_short_term" not in collection_groups
    assert "memory_archive" not in collection_groups

    memory_item_indexes = [idx for idx in data["indexes"] if idx["collectionGroup"] == "memory_items"]
    field_sets = [{field["fieldPath"] for field in idx["fields"]} for idx in memory_item_indexes]
    assert {"tier", "status", "updated_at", "__name__"} in field_sets
    assert {"tier", "status", "expires_at", "__name__"} in field_sets
