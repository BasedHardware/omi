"""The Mongo index reconcile (ADR-0046) must map Firestore composite indexes to the neutral store's
Mongo schema: COLLECTION scope -> ``_parent`` prefix, ``__name__`` -> ``_id``, ASC/DESC -> 1/-1,
COLLECTION_GROUP -> no ``_parent``. This mirrors firestore.indexes.json so Mongo queries hit an index
instead of a collection scan; the mapping is pure and tested here without a live Mongo.
"""

import pytest

from scripts.reconcile_mongo_indexes import (
    create_planned_indexes,
    firestore_index_to_mongo_keys,
    load_manifest,
    planned_indexes,
    reconcile_mongo_indexes,
)


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


class _FakeCollection:
    def __init__(self, name, calls):
        self._name = name
        self._calls = calls

    def create_index(self, keys, name=None, background=None):
        self._calls.append((self._name, keys, name, background))


class _FakeDb:
    def __init__(self):
        self.calls = []

    def __getitem__(self, name):
        return _FakeCollection(name, self.calls)


def test_create_planned_indexes_issues_one_background_create_per_plan_item():
    # The boot-time hook (main.startup_event, STORAGE_BACKEND=mongo) provisions every planned index.
    # Assert create_index is called once per plan item with the mapped keys/name, background=True
    # (non-blocking on Mongo), and that the ensured list mirrors the plan (cubic PR 10887 #6).
    db = _FakeDb()
    plan = [
        ("conversations", [("_parent", 1), ("d.created_at", -1)], "conversations__parent_1__d.created_at_-1"),
        ("people", [("_parent", 1)], "people__parent_1"),
    ]
    ensured = create_planned_indexes(db, plan)
    assert ensured == ["conversations.conversations__parent_1__d.created_at_-1", "people.people__parent_1"]
    assert db.calls == [
        ("conversations", [("_parent", 1), ("d.created_at", -1)], "conversations__parent_1__d.created_at_-1", True),
        ("people", [("_parent", 1)], "people__parent_1", True),
    ]


def test_create_planned_indexes_defaults_to_the_full_manifest_plan():
    # Called with no explicit plan it must ensure every index planned_indexes() derives from the manifest.
    db = _FakeDb()
    ensured = create_planned_indexes(db)
    assert len(ensured) == len(planned_indexes(load_manifest()))
    assert len(db.calls) == len(ensured)


def test_plan_includes_supplementary_users_time_zone_index():
    # cubic PR 10887 reconcile_mongo_indexes.py:92: the hourly daily-summary/morning crons query the
    # top-level ``users`` collection by time_zone. That single-field scoped query is NOT in the composite
    # firestore.indexes.json, so the manifest-only plan left it collection-scanning on Mongo. The plan
    # must add a {_parent, d.time_zone} index (and a _parent baseline) for ``users``.
    plan = planned_indexes(load_manifest())
    users_keys = {tuple(keys) for c, keys, _ in plan if c == "users"}
    assert (("_parent", 1), ("d.time_zone", 1)) in users_keys
    assert (("_parent", 1),) in users_keys


def test_manifest_path_resolves_to_an_existing_file():
    # In the source tree the manifest sits at the repo root; the resolver must find it (and, in the
    # image, the Dockerfile-bundled copy at the WORKDIR) so load_manifest never fails at startup.
    from scripts.reconcile_mongo_indexes import MANIFEST_PATH

    assert MANIFEST_PATH.exists(), MANIFEST_PATH


def test_reconcile_mongo_indexes_requires_mongo_uri(monkeypatch):
    # The startup entry fails loud when MONGO_URI is unset; the boot hook (main) catches this so a
    # misconfigured/unavailable Mongo logs instead of blocking startup.
    monkeypatch.delenv("MONGO_URI", raising=False)
    with pytest.raises(RuntimeError, match="MONGO_URI"):
        reconcile_mongo_indexes()
