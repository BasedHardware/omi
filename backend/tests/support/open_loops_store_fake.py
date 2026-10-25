"""A tiny in-memory Firestore fake for open-loop store tests.

Supports exactly the surface ``database/open_loops.py`` uses:
``collection(...).document(...).collection(...).document(...).{set,get,create,update,delete}``
plus ``.stream()`` over one collection level. ``create`` enforces Firestore's
compare-and-insert semantics (the open-loops day-claim atomicity); no queries,
no transactions.
"""

from __future__ import annotations

import copy
import threading
from typing import Dict, Optional, Tuple


class DocumentAlreadyExistsError(Exception):
    """The fake's stand-in for Firestore's AlreadyExists on ``create``."""


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
    def __init__(self, docs: Dict[Tuple[str, ...], Dict], lock: threading.Lock, path: Tuple[str, ...]):
        self._docs = docs
        self._lock = lock
        self._path = path

    def set(self, data: Dict) -> None:
        with self._lock:
            self._docs[self._path] = copy.deepcopy(data)

    def create(self, data: Dict) -> None:
        with self._lock:
            if self._path in self._docs:
                raise DocumentAlreadyExistsError(f'{"/".join(self._path)} already exists')
            self._docs[self._path] = copy.deepcopy(data)

    def update(self, data: Dict) -> None:
        with self._lock:
            if self._path not in self._docs:
                raise KeyError(f'{"/".join(self._path)} missing')
            merged = dict(self._docs[self._path])
            merged.update(copy.deepcopy(data))
            self._docs[self._path] = merged

    def get(self) -> _Snapshot:
        with self._lock:
            return _Snapshot(self._path[-1], copy.deepcopy(self._docs.get(self._path)))

    def delete(self) -> None:
        with self._lock:
            self._docs.pop(self._path, None)

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self._docs, self._lock, self._path + (name,))


class _CollectionRef:
    def __init__(self, docs: Dict[Tuple[str, ...], Dict], lock: threading.Lock, prefix: Tuple[str, ...]):
        self._docs = docs
        self._lock = lock
        self._prefix = prefix

    def document(self, doc_id: str) -> _DocumentRef:
        return _DocumentRef(self._docs, self._lock, self._prefix + (doc_id,))

    def stream(self):
        with self._lock:
            paths = sorted(
                p for p in self._docs if p[: len(self._prefix)] == self._prefix and len(p) == len(self._prefix) + 1
            )
        for path in paths:
            with self._lock:
                data = copy.deepcopy(self._docs.get(path))
            yield _Snapshot(path[-1], data)


class FakeFirestore:
    def __init__(self):
        self.docs: Dict[Tuple[str, ...], Dict] = {}
        self._lock = threading.Lock()

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self.docs, self._lock, (name,))

    def raw_doc(self, *path: str) -> Optional[Dict]:
        with self._lock:
            return copy.deepcopy(self.docs.get(path))
