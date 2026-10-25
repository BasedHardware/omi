"""A tiny in-memory Firestore fake for open-loop store tests.

Supports exactly the surface ``database/open_loops.py`` uses:
``collection(...).document(...).collection(...).document(...).{set,get,delete}``
plus ``.stream()`` over one collection level. No queries, no transactions.
"""

from __future__ import annotations

import copy
from typing import Dict, Optional, Tuple


class _Snapshot:
    def __init__(self, doc_id: str, data: Optional[Dict]):
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Optional[Dict]:
        return copy.deepcopy(self._data)


class _DocumentRef:
    def __init__(self, docs: Dict[Tuple[str, ...], Dict], path: Tuple[str, ...]):
        self._docs = docs
        self._path = path

    def set(self, data: Dict) -> None:
        self._docs[self._path] = copy.deepcopy(data)

    def get(self) -> _Snapshot:
        return _Snapshot(self._path[-1], self._docs.get(self._path))

    def delete(self) -> None:
        self._docs.pop(self._path, None)

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self._docs, self._path + (name,))


class _CollectionRef:
    def __init__(self, docs: Dict[Tuple[str, ...], Dict], prefix: Tuple[str, ...]):
        self._docs = docs
        self._prefix = prefix

    def document(self, doc_id: str) -> _DocumentRef:
        return _DocumentRef(self._docs, self._prefix + (doc_id,))

    def stream(self):
        for path in sorted(
            p for p in self._docs if p[: len(self._prefix)] == self._prefix and len(p) == len(self._prefix) + 1
        ):
            yield _Snapshot(path[-1], self._docs[path])


class FakeFirestore:
    def __init__(self):
        self.docs: Dict[Tuple[str, ...], Dict] = {}

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self.docs, (name,))

    def raw_doc(self, *path: str) -> Optional[Dict]:
        return self.docs.get(path)
