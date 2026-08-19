"""Regression test: bulk Limitless deletion must only remove imported conversations.

``delete_limitless_conversations`` routes to the database helper
``delete_conversations_by_source``, which is the safety boundary for the
``DELETE /v1/import/limitless/conversations`` endpoint. It must query only
``source == 'limitless'`` rows that are also ``imported == True``, then delegate
to ``delete_conversation`` with the same injected client so every subcollection is
purged. Older Limitless imports (and native ``source='limitless'`` pendant
recordings) predate the ``imported`` flag and must intentionally survive; a
reversed predicate or a missed injected client would otherwise delete native
conversations or leave orphaned derived records behind.
"""

from __future__ import annotations

import pytest

from database import conversations as conversations_db


class _FakeBatch:
    def __init__(self, store: "_FakeFirestore"):
        self._store = store
        self._pending: list["_FakeDocumentReference"] = []

    def delete(self, doc_ref: "_FakeDocumentReference") -> None:
        self._pending.append(doc_ref)

    def commit(self) -> None:
        for doc_ref in self._pending:
            doc_ref.delete()
        self._pending = []


class _FakeQuery:
    def __init__(self, collection: "_FakeCollectionReference", limit: int | None = None):
        self._collection = collection
        self._limit = limit
        self.filters: list[tuple[str, str, object]] = []

    def where(self, filter) -> "_FakeQuery":
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        self._collection.applied_filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def limit(self, count: int) -> "_FakeQuery":
        return _FakeQuery(self._collection, count)

    def stream(self):
        docs = [doc for doc in self._collection.documents.values() if doc.exists and self._matches(doc)]
        return docs if self._limit is None else docs[: self._limit]

    def _matches(self, doc: "_FakeDocumentReference") -> bool:
        for field_path, op, value in self.filters:
            if op != "==":
                return False
            if doc.data.get(field_path) != value:
                return False
        return True


class _FakeDocumentReference:
    def __init__(self, path: str, store: "_FakeFirestore", data: dict | None = None):
        self.path = path
        self.id = path.rsplit("/", 1)[-1]
        self._store = store
        self.data = dict(data or {})
        self.exists = True
        self.subcollections: dict[str, _FakeCollectionReference] = {}

    # Snapshots streamed out of a query carry `.reference`; the fake document is
    # its own snapshot so the production loop reads the same attribute it does
    # against the real SDK.
    @property
    def reference(self) -> "_FakeDocumentReference":
        return self

    def collection(self, name: str) -> "_FakeCollectionReference":
        if name not in self.subcollections:
            self.subcollections[name] = _FakeCollectionReference(f"{self.path}/{name}", self._store)
        return self.subcollections[name]

    def collections(self):
        # Firestore only lists subcollections that still hold documents.
        return [sub for sub in self.subcollections.values() if any(d.exists for d in sub.documents.values())]

    def delete(self) -> None:
        self.exists = False
        self._store.deleted.append(self.path)


class _FakeCollectionReference:
    def __init__(self, path: str, store: "_FakeFirestore"):
        self.path = path
        self._store = store
        self.documents: dict[str, _FakeDocumentReference] = {}
        self.applied_filters: list[tuple[str, str, object]] = []

    def document(self, doc_id: str, data: dict | None = None) -> _FakeDocumentReference:
        if doc_id not in self.documents:
            self.documents[doc_id] = _FakeDocumentReference(f"{self.path}/{doc_id}", self._store, data)
        return self.documents[doc_id]

    def where(self, filter) -> _FakeQuery:
        return _FakeQuery(self).where(filter)

    def limit(self, count: int) -> _FakeQuery:
        return _FakeQuery(self, count)

    def stream(self):
        return _FakeQuery(self).stream()


class _FakeFirestore:
    def __init__(self):
        self.root: dict[str, _FakeCollectionReference] = {}
        self.deleted: list[str] = []

    def collection(self, name: str) -> _FakeCollectionReference:
        if name not in self.root:
            self.root[name] = _FakeCollectionReference(name, self)
        return self.root[name]

    def batch(self) -> _FakeBatch:
        return _FakeBatch(self)


@pytest.fixture
def store() -> _FakeFirestore:
    return _FakeFirestore()


def _seed(store: _FakeFirestore, uid: str = "u1") -> dict[str, _FakeDocumentReference]:
    convos = store.collection("users").document(uid).collection("conversations")
    imported_lifelog = convos.document("c-imported", {"source": "limitless", "imported": True})
    imported_lifelog.collection("photos").document("photo-1")
    legacy_lifelog = convos.document("c-legacy", {"source": "limitless"})
    native_pendant = convos.document("c-native", {"source": "limitless", "imported": False})
    unrelated = convos.document("c-other", {"source": "meeting", "imported": True})
    return {
        "imported": imported_lifelog,
        "legacy": legacy_lifelog,
        "native": native_pendant,
        "unrelated": unrelated,
    }


def test_delete_conversations_by_source_deletes_only_imported_limitless(store):
    """Imported Limitless rows are removed; legacy, native, and unrelated rows survive."""
    seeded = _seed(store)

    count = conversations_db.delete_conversations_by_source("u1", "limitless", firestore_client=store)

    assert count == 1
    assert not seeded["imported"].exists
    assert seeded["legacy"].exists
    assert seeded["native"].exists
    assert seeded["unrelated"].exists


def test_delete_conversations_by_source_purges_subcollections_with_injected_client(store):
    """The injected client is passed through so subcollections are purged too."""
    seeded = _seed(store)

    conversations_db.delete_conversations_by_source("u1", "limitless", firestore_client=store)

    # The imported conversation's photos subcollection is gone with its parent.
    assert not seeded["imported"].subcollections["photos"].documents["photo-1"].exists
    assert not seeded["imported"].exists
    # The legacy/native/unrelated rows and their documents are untouched.
    assert seeded["legacy"].exists
    assert seeded["native"].exists
    assert seeded["unrelated"].exists


def test_delete_conversations_by_source_queries_source_and_imported(store):
    """The query predicate is source == {source} AND imported == True."""
    _seed(store)

    conversations_db.delete_conversations_by_source("u1", "limitless", firestore_client=store)

    convos = store.collection("users").document("u1").collection("conversations")
    assert ("source", "==", "limitless") in convos.applied_filters
    assert ("imported", "==", True) in convos.applied_filters
