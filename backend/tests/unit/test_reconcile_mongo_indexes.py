"""The Mongo index reconcile (ADR-0046) must map Firestore composite indexes to the neutral store's
Mongo schema: COLLECTION scope -> ``_parent`` prefix, ``__name__`` -> ``_id``, ASC/DESC -> 1/-1,
COLLECTION_GROUP -> no ``_parent``. This mirrors firestore.indexes.json so Mongo queries hit an index
instead of a collection scan; the mapping is pure and tested here without a live Mongo.
"""

from scripts.reconcile_mongo_indexes import firestore_index_to_mongo_keys, load_manifest, planned_indexes


def test_collection_scope_prefixes_parent_and_maps_name_to_id():
    index = {
        "collectionGroup": "conversations",
        "queryScope": "COLLECTION",
        "fields": [
            {"fieldPath": "source", "order": "ASCENDING"},
            {"fieldPath": "status", "order": "ASCENDING"},
            {"fieldPath": "created_at", "order": "DESCENDING"},
            {"fieldPath": "__name__", "order": "DESCENDING"},
        ],
    }
    collection, keys = firestore_index_to_mongo_keys(index)
    assert collection == "conversations"
    assert keys == [
        ("_parent", 1),
        ("d.source", 1),
        ("d.status", 1),
        ("d.created_at", -1),
        ("_id", -1),
    ]


def test_collection_group_scope_has_no_parent_prefix():
    index = {
        "collectionGroup": "memory_items",
        "queryScope": "COLLECTION_GROUP",
        "fields": [
            {"fieldPath": "uid", "order": "ASCENDING"},
            {"fieldPath": "generation", "order": "ASCENDING"},
            {"fieldPath": "updated_at", "order": "DESCENDING"},
            {"fieldPath": "__name__", "order": "ASCENDING"},
        ],
    }
    collection, keys = firestore_index_to_mongo_keys(index)
    assert collection == "memory_items"
    assert keys == [("d.uid", 1), ("d.generation", 1), ("d.updated_at", -1), ("_id", 1)]  # no _parent


def test_nested_field_path_maps_under_d():
    index = {
        "collectionGroup": "conversations",
        "queryScope": "COLLECTION",
        "fields": [{"fieldPath": "structured.category", "order": "ASCENDING"}],
    }
    _, keys = firestore_index_to_mongo_keys(index)
    assert ("d.structured.category", 1) in keys


def test_plan_covers_every_manifest_index_plus_parent_baseline():
    manifest = load_manifest()
    plan = planned_indexes(manifest)
    collections = {c for c, _, _ in plan}
    # every collectionGroup in the manifest gets at least a _parent baseline index
    manifest_collections = {i["collectionGroup"] for i in manifest["indexes"]}
    assert manifest_collections <= collections
    for collection in manifest_collections:
        assert any(c == collection and keys == [("_parent", 1)] for c, keys, _ in plan)
    # names are unique (idempotent create_index keys)
    names = [(c, n) for c, _, n in plan]
    assert len(names) == len(set(names))
