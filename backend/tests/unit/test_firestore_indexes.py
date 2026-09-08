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
        "conversations",
        "COLLECTION",
        (("source", "ASCENDING"), ("status", "ASCENDING"), ("created_at", "DESCENDING"), ("__name__", "DESCENDING")),
    ) in signatures
    assert (
        "conversations",
        "COLLECTION",
        (
            ("discarded", "ASCENDING"),
            ("source", "ASCENDING"),
            ("status", "ASCENDING"),
            ("created_at", "DESCENDING"),
            ("__name__", "DESCENDING"),
        ),
    ) in signatures

    assert (
        "memory_items",
        "COLLECTION",
        (
            ("tier", "ASCENDING"),
            ("status", "ASCENDING"),
            ("processing_state", "ASCENDING"),
            ("promotion.required", "ASCENDING"),
            ("promotion.processing_status", "ASCENDING"),
            ("captured_at", "ASCENDING"),
            ("memory_id", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ),
    ) in signatures
    assert (
        "memory_items",
        "COLLECTION",
        (
            ("account_generation", "ASCENDING"),
            ("tier", "ASCENDING"),
            ("status", "ASCENDING"),
            ("processing_state", "ASCENDING"),
            ("graph_ready", "ASCENDING"),
            ("updated_at", "DESCENDING"),
            ("__name__", "DESCENDING"),
        ),
    ) in signatures
    # Live firestore_readiness on based-hardware-dev failed this exact
    # composite (run 31666135748). Registry identifier:
    # memory_items_canonical_atlas_read. Keep it in the apply spec.
    assert (
        "memory_items",
        "COLLECTION",
        (
            ("account_generation", "ASCENDING"),
            ("tier", "ASCENDING"),
            ("status", "ASCENDING"),
            ("processing_state", "ASCENDING"),
            ("updated_at", "DESCENDING"),
            ("__name__", "DESCENDING"),
        ),
    ) in signatures
    assert (
        "memory_items",
        "COLLECTION",
        (("source_ids", "CONTAINS"), ("__name__", "ASCENDING")),
    ) not in signatures
    assert (
        "memory_items",
        "COLLECTION",
        (
            ("status", "ASCENDING"),
            ("canonical_memory_id", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ),
    ) in signatures
    assert (
        "memory_items",
        "COLLECTION",
        (
            ("status", "ASCENDING"),
            ("superseded_by", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ),
    ) in signatures
    assert (
        "memory_items",
        "COLLECTION",
        (
            ("tier", "ASCENDING"),
            ("status", "ASCENDING"),
            ("processing_state", "ASCENDING"),
            ("source_state", "ASCENDING"),
            ("captured_at", "ASCENDING"),
            ("memory_id", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ),
    ) in signatures
    assert (
        "memory_items",
        "COLLECTION",
        (
            ("tier", "ASCENDING"),
            ("status", "ASCENDING"),
            ("processing_state", "ASCENDING"),
            ("expires_at", "ASCENDING"),
            ("memory_id", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ),
    ) in signatures
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
    assert (
        "memory_review_queue",
        "COLLECTION",
        (
            ("fact_id", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ),
    ) not in signatures
    assert (
        "memory_review_queue",
        "COLLECTION",
        (
            ("conflict_with", "CONTAINS"),
            ("__name__", "ASCENDING"),
        ),
    ) not in signatures
    assert (
        "memory_review_queue",
        "COLLECTION",
        (
            ("status", "ASCENDING"),
            ("impact", "DESCENDING"),
            ("created_at", "DESCENDING"),
            ("__name__", "DESCENDING"),
        ),
    ) in signatures
