"""A small in-memory Firestore fake shared by the day-3 re-engagement tests.

Unlike ``tests/unit/fake_firestore.py`` (which no-ops every filter) this fake
actually evaluates ``==`` / ``>=`` / ``<`` / ``<=`` / ``in`` predicates against
a flat ``{path: data}`` store, so query-shape bugs (wrong operator, wrong
field, wrong window) show up as wrong test results instead of passing
trivially. It supports the same recursive
``collection(...).document(...).collection(...)`` chaining production code
uses, and ``create()``/``set(merge=...)``/``delete()`` so the same store can
back ``utils.experiments`` and ``utils.email.lifecycle`` calls in the same
test.

Deliberately not a generic Firestore emulator: unsupported query shapes raise
``AssertionError`` rather than silently returning something plausible.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional


class FakeSnapshot:
    def __init__(self, path: str, data: Optional[Dict[str, Any]]):
        self.reference = FakeDocumentReference(path, None)
        self.id = path.rsplit('/', 1)[-1]
        self.exists = data is not None
        self._data = copy.deepcopy(data)

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return copy.deepcopy(self._data)


class FakeDocumentReference:
    def __init__(self, path: str, db: Optional['FakeFirestore']):
        self.path = path
        self._db = db

    def get(self, transaction=None, field_paths=None) -> FakeSnapshot:
        assert self._db is not None
        return FakeSnapshot(self.path, self._db.docs.get(self.path))

    def collection(self, name: str) -> 'FakeQuery':
        assert self._db is not None
        return FakeQuery(self._db, f'{self.path}/{name}')

    def set(self, value: Dict[str, Any], merge: bool = False) -> None:
        assert self._db is not None
        current = dict(self._db.docs.get(self.path) or {}) if merge else {}
        current.update(value)
        self._db.docs[self.path] = current

    def create(self, value: Dict[str, Any]) -> None:
        assert self._db is not None
        if self.path in self._db.docs:
            raise RuntimeError(f'fake firestore: document already exists at {self.path}')
        self._db.docs[self.path] = dict(value)

    def delete(self) -> None:
        assert self._db is not None
        self._db.docs.pop(self.path, None)


class FakeQuery:
    def __init__(
        self,
        db: 'FakeFirestore',
        collection_path: str,
        filters=None,
        limit_count: Optional[int] = None,
        order_field: Optional[str] = None,
    ):
        self._db = db
        self._collection_path = collection_path
        self._filters = list(filters or [])
        self._limit_count = limit_count
        self._order_field = order_field

    def where(
        self, field: Optional[str] = None, operation: Optional[str] = None, value: Any = None, *, filter: Any = None
    ):
        if filter is not None:
            field, operation, value = filter.field_path, filter.op_string, filter.value
        assert field is not None and operation is not None
        return FakeQuery(
            self._db,
            self._collection_path,
            self._filters + [(field, operation, value)],
            self._limit_count,
            self._order_field,
        )

    def order_by(self, field: str, direction: Any = None) -> 'FakeQuery':
        return FakeQuery(self._db, self._collection_path, self._filters, self._limit_count, field)

    def limit(self, count: int) -> 'FakeQuery':
        return FakeQuery(self._db, self._collection_path, self._filters, count, self._order_field)

    def document(self, document_id: str) -> FakeDocumentReference:
        return FakeDocumentReference(f'{self._collection_path}/{document_id}', self._db)

    def stream(self):
        prefix = f'{self._collection_path}/'
        matches = []
        for path, data in self._db.docs.items():
            if not path.startswith(prefix):
                continue
            remainder = path[len(prefix) :]
            if '/' in remainder:
                continue  # belongs to a deeper subcollection, not this one
            if all(self._matches(data, field, operation, value) for field, operation, value in self._filters):
                matches.append(FakeSnapshot(path, data))
        matches.sort(key=lambda snap: (snap.to_dict() or {}).get(self._order_field) if self._order_field else snap.id)
        return matches[: self._limit_count] if self._limit_count is not None else matches

    @staticmethod
    def _matches(data: Optional[Dict[str, Any]], field: str, operation: str, value: Any) -> bool:
        actual = (data or {}).get(field)
        if operation == '==':
            return actual == value
        if operation == '>=':
            return actual is not None and actual >= value
        if operation == '<':
            return actual is not None and actual < value
        if operation == '<=':
            return actual is not None and actual <= value
        if operation == 'in':
            return actual in value
        raise AssertionError(f'fake firestore: unsupported query operation {operation!r}')


class FakeFirestore:
    def __init__(self, docs: Optional[Dict[str, Any]] = None):
        self.docs: Dict[str, Any] = dict(docs or {})

    def collection(self, path: str) -> FakeQuery:
        return FakeQuery(self, path)

    def document(self, path: str) -> FakeDocumentReference:
        return FakeDocumentReference(path, self)
