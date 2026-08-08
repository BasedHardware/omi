"""Minimal in-memory Firestore fakes shared by memory unit tests."""

from __future__ import annotations

from typing import Any


class FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None, *, exists: bool = True):
        self._data = data
        self.exists = exists

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class FakeDocumentReference:
    def __init__(self, path: str, db: "FakeFirestore"):
        self.path = path
        self._db = db

    def get(self, transaction=None) -> FakeSnapshot:
        if self.path not in self._db.docs:
            return FakeSnapshot(None, exists=False)
        value = self._db.docs[self.path]
        if isinstance(value, BaseException):
            raise value
        return FakeSnapshot(value, exists=True)


class FakeFirestore:
    def __init__(self, docs: dict[str, Any] | None = None):
        self.docs = dict(docs or {})
        self.document_reads: list[str] = []

    def document(self, path: str) -> FakeDocumentReference:
        self.document_reads.append(path)
        return FakeDocumentReference(path, self)

    def collection(self, path: str) -> "FakeQuery":
        return FakeQuery()


class FakeQuery:
    def where(self, *args, **kwargs) -> "FakeQuery":
        return self

    def order_by(self, *args, **kwargs) -> "FakeQuery":
        return self

    def start_after(self, *args, **kwargs) -> "FakeQuery":
        return self

    def limit(self, *args, **kwargs) -> "FakeQuery":
        return self

    def stream(self):
        return []


class MockSnapshot:
    """In-memory Firestore document snapshot backed by a ``MockFirestore`` ``docs`` dict."""

    def __init__(self, data: dict[str, Any] | None, *, exists: bool | None = None):
        self._data = data
        self.exists = exists if exists is not None else data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class MockDocumentReference:
    """A reference into a ``MockFirestore`` document keyed by ``collection/path``."""

    def __init__(self, path: str, db: "MockFirestore"):
        self.path = path
        self._db = db

    @property
    def reference(self) -> "MockDocumentReference":
        return self

    def get(self, transaction=None) -> MockSnapshot:
        if self.path not in self._db.docs:
            return MockSnapshot(None, exists=False)
        value = self._db.docs[self.path]
        if isinstance(value, BaseException):
            raise value
        return MockSnapshot(value, exists=True)

    def create(self, data: dict[str, Any]) -> None:
        if self.path in self._db.docs:
            from google.api_core.exceptions import AlreadyExists

            raise AlreadyExists(f"document {self.path} already exists")
        self._db.docs[self.path] = dict(data)

    def set(self, data: dict[str, Any]) -> None:
        self._db.docs[self.path] = dict(data)

    def update(self, data: dict[str, Any]) -> None:
        if self.path not in self._db.docs:
            self._db.docs[self.path] = {}
        self._db.docs[self.path].update(data)


class MockQuery:
    """A filterable stream over the documents of a ``MockFirestore`` collection."""

    def __init__(self, db: "MockFirestore", collection_path: str):
        self._db = db
        self._collection_path = collection_path
        self._predicates: list[tuple[str, str, Any]] = []

    def where(self, field: str, op: str, value: Any) -> "MockQuery":
        self._predicates.append((field, op, value))
        return self

    def order_by(self, *args, **kwargs) -> "MockQuery":
        return self

    def start_after(self, *args, **kwargs) -> "MockQuery":
        return self

    def limit(self, *args, **kwargs) -> "MockQuery":
        return self

    def stream(self):
        prefix = f"{self._collection_path}/"
        rows = [
            MockSnapshot(data)
            for path, data in self._db.docs.items()
            if path.startswith(prefix)
        ]
        for field, op, value in self._predicates:
            if op != "==":
                continue
            rows = [row for row in rows if (row.to_dict() or {}).get(field) == value]
        return rows


class MockCollectionReference:
    def __init__(self, db: "MockFirestore", collection_path: str):
        self._db = db
        self._collection_path = collection_path

    def document(self, document_id: str) -> MockDocumentReference:
        return MockDocumentReference(f"{self._collection_path}/{document_id}", self._db)

    def where(self, field: str, op: str, value: Any) -> MockQuery:
        return MockQuery(self._db, self._collection_path).where(field, op, value)

    def stream(self) -> list[MockSnapshot]:
        return MockQuery(self._db, self._collection_path).stream()


class MockBatch:
    def __init__(self, db: "MockFirestore"):
        self._db = db
        self._ops: list[tuple[str, MockDocumentReference, dict[str, Any]]] = []

    def update(self, ref: MockDocumentReference, data: dict[str, Any]) -> None:
        self._ops.append(("update", ref, data))

    def set(self, ref: MockDocumentReference, data: dict[str, Any]) -> None:
        self._ops.append(("set", ref, data))

    def commit(self) -> None:
        for kind, ref, data in self._ops:
            if kind == "update":
                ref.update(data)
            else:
                ref.set(data)


class MockTransaction(MockBatch):
    """A fake Firestore transaction with the surface the SDK's ``transactional`` drives."""

    def __init__(self, db: "MockFirestore"):
        super().__init__(db)

    def _begin(self, retry_id=None) -> None:
        pass

    def get(self, ref: MockDocumentReference) -> MockSnapshot:
        return ref.get()

    def _commit(self, retry_id=None) -> None:
        self.commit()

    def _rollback(self) -> None:
        self._ops.clear()

    def _clean_up(self) -> None:
        pass


class MockFirestore:
    """In-memory Firestore client for unit tests with document writes and transactions."""

    def __init__(self, docs: dict[str, Any] | None = None):
        self.docs = {path: dict(data) for path, data in (docs or {}).items()}
        self.document_reads: list[str] = []

    def document(self, path: str) -> MockDocumentReference:
        self.document_reads.append(path)
        return MockDocumentReference(path, self)

    def collection(self, path: str) -> MockCollectionReference:
        return MockCollectionReference(self, path)

    def batch(self) -> MockBatch:
        return MockBatch(self)

    def transaction(self) -> MockTransaction:
        return MockTransaction(self)
