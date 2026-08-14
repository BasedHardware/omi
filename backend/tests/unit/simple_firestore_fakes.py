"""Minimal in-memory Firestore fakes shared by memory unit tests.

This module is deliberately not named ``fake_firestore``: that is the import
name of the installed ``fake_firestore`` distribution whose ``MockFirestore``
models the real Firestore surface (transactions, queries, snapshot
references). A same-named module under ``tests/unit`` shadows that package for
anyone running pytest with ``tests/unit`` on ``PYTHONPATH``.
"""

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
