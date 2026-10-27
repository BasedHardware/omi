"""Tests for KG citation pruning and dangling-edge cleanup."""

from __future__ import annotations

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch
from google.api_core.exceptions import FailedPrecondition

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


class _DocRef:
    def __init__(self, db, path: str):
        self._db = db
        self.path = path
        self.id = path.rsplit("/", 1)[-1]

    def set(self, data, merge=False):
        if merge and self.path in self._db.docs:
            self._db.docs[self.path] = {**self._db.docs[self.path], **data}
        else:
            self._db.docs[self.path] = data

    def delete(self):
        self._db.docs.pop(self.path, None)

    def collection(self, name: str):
        return _CollectionRef(self._db, f"{self.path}/{name}")


class _StreamDoc:
    def __init__(self, db, path: str):
        self.id = path.rsplit("/", 1)[-1]
        self._db = db
        self._path = path
        self.reference = _DocRef(db, path)

    def to_dict(self):
        return self._db.docs.get(self._path)


class _CollectionRef:
    def __init__(self, db, path: str):
        self._db = db
        self.path = path

    def document(self, doc_id: str):
        return _DocRef(self._db, f"{self.path}/{doc_id}")

    def where(self, *, filter):
        return _Query(self._db, self.path, filter)

    def stream(self):
        prefix = f"{self.path}/"
        depth = self.path.count("/")
        for path in sorted(self._db.docs):
            if not path.startswith(prefix):
                continue
            if path.count("/") != depth + 1:
                continue
            self._db.reads += 1
            yield _StreamDoc(self._db, path)


class _Query(_CollectionRef):
    def __init__(self, db, path, filter):
        super().__init__(db, path)
        self.filter = filter

    def stream(self):
        self._db.query_count += 1
        if self._db.fail_query_at == self._db.query_count:
            raise FailedPrecondition('query requires an index')
        assert self.filter.field_path == 'memory_ids'
        assert self.filter.op_string == 'array_contains_any'
        assert len(self.filter.value) <= 30
        for path, row in sorted(self._db.docs.items()):
            if path.startswith(self.path + '/') and path.count('/') == self.path.count('/') + 1:
                if set(row.get('memory_ids') or []).intersection(self.filter.value):
                    self._db.reads += 1
                    yield _StreamDoc(self._db, path)


class _KgFakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.reads = 0
        self.query_count = 0
        self.fail_query_at = None

    def collection(self, name: str):
        return _CollectionRef(self, name)


@pytest.fixture
def kg_module():
    saved_modules = dict(sys.modules)
    database_pkg = sys.modules.setdefault("database", types.ModuleType("database"))
    database_pkg.__path__ = [os.path.join(_BACKEND_DIR, "database")]

    google_mod = types.ModuleType("google")
    cloud_mod = types.ModuleType("google.cloud")
    firestore_mod = types.ModuleType("google.cloud.firestore")
    firestore_v1_mod = types.ModuleType("google.cloud.firestore_v1")
    google_mod.cloud = cloud_mod
    cloud_mod.firestore = firestore_mod
    cloud_mod.firestore_v1 = firestore_v1_mod
    firestore_mod.Client = MagicMock()
    firestore_v1_mod.FieldFilter = lambda field, op, value: types.SimpleNamespace(
        field_path=field, op_string=op, value=value
    )

    def transactional(func):
        return func

    firestore_v1_mod.transactional = transactional
    sys.modules["google"] = google_mod
    sys.modules["google.cloud"] = cloud_mod
    sys.modules["google.cloud.firestore"] = firestore_mod
    sys.modules["google.cloud.firestore_v1"] = firestore_v1_mod

    for module_name in ("database.knowledge_graph", "database._client"):
        sys.modules.pop(module_name, None)

    fake_db = _KgFakeDb()
    with patch("google.cloud.firestore.Client", return_value=MagicMock()):
        sys.modules["database._client"] = types.ModuleType("database._client")
        sys.modules["database._client"].db = fake_db
        import database.knowledge_graph as kg_mod

        importlib.reload(kg_mod)

    yield kg_mod, fake_db

    sys.modules.clear()
    sys.modules.update(saved_modules)


def test_prune_memory_citations_removes_dangling_edges_when_node_deleted(kg_module):
    kg_mod, fake_db = kg_module
    uid = "uid-kg-prune"
    node_path = f"users/{uid}/knowledge_nodes/node_a"
    edge_path = f"users/{uid}/knowledge_edges/edge_ab"
    fake_db.docs.update(
        {
            node_path: {
                "id": "node_a",
                "label": "Entity A",
                "memory_ids": ["mem_old"],
            },
            edge_path: {
                "id": "edge_ab",
                "source_id": "node_a",
                "target_id": "node_b",
                "label": "related_to",
                "memory_ids": ["mem_old", "mem_other"],
            },
        }
    )

    pruned = kg_mod.prune_memory_citations_from_kg(uid, ["mem_old"])

    assert node_path not in fake_db.docs
    assert edge_path not in fake_db.docs
    assert pruned >= 2


def test_reverse_index_reduces_reads_and_preserves_global_orphan_cleanup(kg_module, monkeypatch):
    kg_mod, indexed = kg_module
    uid = 'synthetic-kg'
    prefix = f'users/{uid}'
    indexed.docs.update(
        {f'{prefix}/knowledge_nodes/node-{i}': {'id': f'node-{i}', 'memory_ids': ['keep']} for i in range(100)}
    )
    indexed.docs[f'{prefix}/knowledge_nodes/removed'] = {'id': 'removed', 'memory_ids': ['old']}
    indexed.docs[f'{prefix}/knowledge_nodes/partial'] = {'id': 'partial', 'memory_ids': ['old', 'keep']}
    indexed.docs[f'{prefix}/knowledge_edges/incident'] = {
        'source_id': 'removed',
        'target_id': 'node-1',
        'memory_ids': ['keep'],
    }
    indexed.docs[f'{prefix}/knowledge_edges/unrelated-orphan'] = {
        'source_id': 'never-existed',
        'target_id': 'node-1',
        'memory_ids': ['keep'],
    }
    indexed.docs[f'{prefix}/knowledge_edges/survives'] = {
        'source_id': 'node-1',
        'target_id': 'node-2',
        'memory_ids': ['keep', 'old'],
    }
    legacy = _KgFakeDb({path: dict(row) for path, row in indexed.docs.items()})
    assert kg_mod.prune_memory_citations_from_kg(uid, ['old'], db_client=indexed) == 5
    monkeypatch.setenv('FSR_KG_CITATION_INDEX', 'off')
    assert kg_mod.prune_memory_citations_from_kg(uid, ['old'], db_client=legacy) == 5
    # updated_at is intentionally current in each call.
    for store in (indexed, legacy):
        for row in store.docs.values():
            row.pop('updated_at', None)
    assert indexed.docs == legacy.docs
    assert indexed.reads == 106
    assert legacy.reads == 206


def test_bulk_citations_retain_legacy_scan_without_read_amplification(kg_module, monkeypatch):
    kg_mod, store = kg_module
    uid = 'synthetic-kg'
    prefix = f'users/{uid}/knowledge_nodes'
    path = f'{prefix}/node'
    ids = [f'memory-{i:02d}' for i in range(65)]
    store.docs[path] = {'id': 'node', 'memory_ids': ids + ['keep']}
    store.docs[f'{prefix}/unrelated'] = {'id': 'unrelated', 'memory_ids': ['keep']}
    legacy = _KgFakeDb({path: dict(row) for path, row in store.docs.items()})
    assert kg_mod.prune_memory_citations_from_kg(uid, ids, db_client=store) == 1
    monkeypatch.setenv('FSR_KG_CITATION_INDEX', 'off')
    assert kg_mod.prune_memory_citations_from_kg(uid, ids, db_client=legacy) == 1
    for db in (store, legacy):
        for row in db.docs.values():
            row.pop('updated_at', None)
    assert store.docs == legacy.docs
    assert store.query_count == 0
    assert store.reads == legacy.reads == 4


def test_thirty_distinct_citations_use_one_query_even_with_duplicate_inputs(kg_module):
    kg_mod, store = kg_module
    uid = 'synthetic-kg'
    path = f'users/{uid}/knowledge_nodes/node'
    ids = [f'memory-{i:02d}' for i in range(30)]
    store.docs[path] = {'id': 'node', 'memory_ids': ids + ['keep']}
    assert kg_mod.prune_memory_citations_from_kg(uid, ids + ids, db_client=store) == 1
    assert store.query_count == 1
    assert store.docs[path]['memory_ids'] == ['keep']


def test_missing_native_index_falls_back_before_writes(kg_module):
    kg_mod, store = kg_module
    uid = 'synthetic-kg'
    path = f'users/{uid}/knowledge_nodes/node'
    store.docs[path] = {'id': 'node', 'memory_ids': ['old']}
    store.fail_query_at = 1
    assert kg_mod.prune_memory_citations_from_kg(uid, ['old'], db_client=store) == 1
    assert store.query_count == 1
    assert path not in store.docs


@pytest.mark.parametrize('memory_id', ['a' * 1501, '\u00e9' * 751])
def test_oversized_citation_id_retains_legacy_pruning_without_index_truncation(kg_module, memory_id):
    kg_mod, store = kg_module
    uid = 'synthetic-kg'
    path = f'users/{uid}/knowledge_nodes/node'
    store.docs[path] = {'id': 'node', 'memory_ids': [memory_id, 'keep']}
    assert kg_mod.prune_memory_citations_from_kg(uid, [memory_id], db_client=store) == 1
    assert store.query_count == 0
    assert store.docs[path]['memory_ids'] == ['keep']
