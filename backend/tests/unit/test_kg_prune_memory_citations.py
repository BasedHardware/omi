"""Tests for KG citation pruning and dangling-edge cleanup."""

from __future__ import annotations

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch

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

    def stream(self):
        prefix = f"{self.path}/"
        depth = self.path.count("/")
        for path in sorted(self._db.docs):
            if not path.startswith(prefix):
                continue
            if path.count("/") != depth + 1:
                continue
            yield _StreamDoc(self._db, path)


class _KgFakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

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
    firestore_v1_mod.FieldFilter = MagicMock()

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
