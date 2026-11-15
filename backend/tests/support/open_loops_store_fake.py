"""A tiny in-memory Firestore fake for open-loop store tests.

Supports exactly the surface ``database/open_loops.py`` uses:
``collection(...).document(...).collection(...).document(...).{set,get,create,update,delete}``
plus ``.stream()`` over one collection level, and single-document
optimistic-concurrency transactions (``client.transaction()`` driven by the
Firestore ``@transactional`` wrapper: staged writes, read-set validation at
commit, immediate retry on contention). ``create`` enforces Firestore's
compare-and-insert semantics (the open-loops day-claim atomicity); no queries
beyond ``stream()``.
"""

from __future__ import annotations

import copy
import threading
from typing import Callable, Dict, Optional, Tuple

from google.api_core.exceptions import Aborted


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
    def __init__(
        self,
        docs: Dict[Tuple[str, ...], Dict],
        lock: threading.Lock,
        versions: Dict[Tuple[str, ...], int],
        path: Tuple[str, ...],
    ):
        self._docs = docs
        self._lock = lock
        self._versions = versions
        self._path = path

    @property
    def path_tuple(self) -> Tuple[str, ...]:
        return self._path

    def _bump(self) -> None:
        self._versions[self._path] = self._versions.get(self._path, 0) + 1

    def set(self, data: Dict, transaction: Optional['_FakeTransaction'] = None) -> None:
        if transaction is not None:
            transaction.set(self, data)
            return
        with self._lock:
            self._docs[self._path] = copy.deepcopy(data)
            self._bump()

    def create(self, data: Dict) -> None:
        with self._lock:
            if self._path in self._docs:
                raise DocumentAlreadyExistsError(f'{"/".join(self._path)} already exists')
            self._docs[self._path] = copy.deepcopy(data)
            self._bump()

    def update(self, data: Dict) -> None:
        with self._lock:
            if self._path not in self._docs:
                raise KeyError(f'{"/".join(self._path)} missing')
            merged = dict(self._docs[self._path])
            merged.update(copy.deepcopy(data))
            self._docs[self._path] = merged
            self._bump()

    def get(self, transaction: Optional['_FakeTransaction'] = None) -> _Snapshot:
        if transaction is not None:
            return transaction.get(self)
        with self._lock:
            return _Snapshot(self._path[-1], copy.deepcopy(self._docs.get(self._path)))

    def delete(self) -> None:
        with self._lock:
            self._docs.pop(self._path, None)
            self._bump()

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self._docs, self._lock, self._versions, self._path + (name,))


class _CollectionRef:
    def __init__(
        self,
        docs: Dict[Tuple[str, ...], Dict],
        lock: threading.Lock,
        versions: Dict[Tuple[str, ...], int],
        prefix: Tuple[str, ...],
    ):
        self._docs = docs
        self._lock = lock
        self._versions = versions
        self._prefix = prefix

    def document(self, doc_id: str) -> _DocumentRef:
        return _DocumentRef(self._docs, self._lock, self._versions, self._prefix + (doc_id,))

    def stream(self):
        with self._lock:
            paths = sorted(
                p for p in self._docs if p[: len(self._prefix)] == self._prefix and len(p) == len(self._prefix) + 1
            )
        for path in paths:
            with self._lock:
                data = copy.deepcopy(self._docs.get(path))
            yield _Snapshot(path[-1], data)


class _FakeTransaction:
    """Staged single-store transaction with Firestore's commit-time contention rule.

    Writes are staged and applied atomically at ``_commit``; a commit raises
    ``Aborted`` when any document the transaction read changed underneath it —
    the serialization Firestore provides — and the ``@firestore.transactional``
    wrapper answers that by re-running the body against fresh state (no sleep:
    the SDK preserves the transaction's "spot in line"). Lifecycle hooks and
    the ``_read_only``/``_max_attempts`` attributes are the ones that wrapper
    drives.
    """

    def __init__(self, store: 'FakeFirestore'):
        self._store = store
        self._id: Optional[bytes] = None
        self._read_versions: Dict[Tuple[str, ...], int] = {}
        self._staged: Dict[Tuple[str, ...], Dict] = {}
        self._read_only = False
        self._max_attempts = 5

    def _clean_up(self) -> None:
        self._id = None
        self._read_versions = {}
        self._staged = {}

    def _begin(self, retry_id: Optional[bytes] = None) -> None:
        self._id = retry_id or b'fake-transaction'

    def _commit(self) -> None:
        with self._store._lock:
            for path, version in self._read_versions.items():
                if self._store.versions.get(path, 0) != version:
                    raise Aborted('transaction aborted: a read document changed')
            for path, data in self._staged.items():
                self._store.docs[path] = copy.deepcopy(data)
                self._store.versions[path] = self._store.versions.get(path, 0) + 1

    def _rollback(self) -> None:
        self._clean_up()

    def get(self, ref: _DocumentRef) -> _Snapshot:
        with self._store._lock:
            if self._id is None:
                raise RuntimeError('transaction read before begin')
            self._read_versions[ref.path_tuple] = self._store.versions.get(ref.path_tuple, 0)
            snapshot = _Snapshot(ref.path_tuple[-1], copy.deepcopy(self._store.docs.get(ref.path_tuple)))
        hook = self._store.on_transaction_read
        if hook is not None:
            hook(ref.path_tuple)
        return snapshot

    def set(self, ref: _DocumentRef, data: Dict) -> None:
        self._staged[ref.path_tuple] = copy.deepcopy(data)


class FakeFirestore:
    def __init__(self):
        self.docs: Dict[Tuple[str, ...], Dict] = {}
        # Per-path write counter backing the transactions' read-set validation.
        self.versions: Dict[Tuple[str, ...], int] = {}
        self._lock = threading.Lock()
        # Test hook: called synchronously inside a transaction's read, the
        # deterministic seam for "another answer committed while this one held
        # its read" (set by one test, cleared by that test).
        self.on_transaction_read: Optional[Callable[[Tuple[str, ...]], None]] = None

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self.docs, self._lock, self.versions, (name,))

    def raw_doc(self, *path: str) -> Optional[Dict]:
        with self._lock:
            return copy.deepcopy(self.docs.get(path))
