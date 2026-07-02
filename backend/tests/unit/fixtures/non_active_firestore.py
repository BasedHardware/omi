"""Shared Firestore fakes for non-active route unit tests."""

from __future__ import annotations


class FakeSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class TransactionalDocumentRef:
    def __init__(self, path, db):
        self.path = path
        self._db = db

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return FakeSnapshot(None, exists=False)
        return FakeSnapshot(self._db.docs[self.path], exists=True)


class FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        self.sets.append((ref.path, data))

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"
        self.sets = []

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data

    def _rollback(self):
        self._id = None


class TransactionalFakeDb:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.transaction_obj = FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return TransactionalDocumentRef(path, self)


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
