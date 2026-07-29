"""Shared Firestore fakes for non-active route unit tests.

The route-store persistence path now runs through the neutral storage port (ADR-0002); its
tests use ``tests.store_fakes.FakeDocumentStore`` instead of a Firestore-shaped transactional
fake. The query fakes below remain for the audit-report reader tests that still exercise a
Firestore ``db_client`` seam.
"""

from __future__ import annotations


class QuerySnapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class FakeQuery:
    def __init__(self, docs, db, filters=None):
        self._docs = docs
        self._db = db
        self._filters = filters or []

    def where(self, field, op, value):
        self._db.where_calls.append((field, op, value))
        return FakeQuery(self._docs, self._db, self._filters + [(field, op, value)])

    def stream(self):
        self._db.streamed = True
        docs = list(self._docs)
        for field, op, value in self._filters:
            assert op == "=="
            docs = [doc for doc in docs if doc.get(field) == value]
        return [QuerySnapshot(doc) for doc in docs]


class QueryFakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.collection_paths = []
        self.where_calls = []
        self.streamed = False

    def collection(self, path):
        self.collection_paths.append(path)
        return FakeQuery(self.docs, self)
