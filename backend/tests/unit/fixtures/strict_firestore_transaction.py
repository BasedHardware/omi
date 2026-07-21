"""Narrow Firestore transaction fixture for ordering-sensitive unit tests.

This fixture models document-reference ``get(transaction=...)`` plus transaction
``create``, ``set``, and ``update``. It enforces Firestore's rule that every
transactional read must occur before the first transactional write.

It deliberately does not model queries, deletes, commit/rollback visibility,
or retry and contention semantics. Extend it only when an incident proves that
one of those boundaries needs a hermetic guard.

As fixture-integrity policy, a transaction accepts references created by its
own ``StrictFirestore`` instance only. This prevents accidental mixing of
unrelated in-memory stores; it is not a claim about Firestore client identity.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any


class ReadAfterWriteError(RuntimeError):
    """Raised when a transaction performs a read after staging a write."""


class ForeignTransactionError(ValueError):
    """Raised when fixture policy forbids mixing transaction and reference stores."""


class UnsupportedFirestoreOperationError(NotImplementedError):
    """Raised for a Firestore operation this narrow fixture does not model."""


_SUPPORTED_OPERATIONS = 'document get/create, transaction-bound document get, transaction create/set/update'


class StrictFirestoreSnapshot:
    def __init__(self, data: dict[str, Any] | None):
        self._data = deepcopy(data)
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._data)


class StrictFirestoreDocument:
    def __init__(self, database: StrictFirestore, path: tuple[str, ...]):
        self._database = database
        self.path = path

    def collection(self, name: str) -> StrictFirestoreCollection:
        return StrictFirestoreCollection(self._database, (*self.path, name))

    def get(self, transaction: StrictFirestoreTransaction | None = None) -> StrictFirestoreSnapshot:
        if transaction is not None:
            transaction._assert_reference_belongs(self)
            transaction._assert_read_allowed()
        return StrictFirestoreSnapshot(self._database.rows.get(self.path))

    def create(self, data: dict[str, Any]) -> None:
        if self.path in self._database.rows:
            raise RuntimeError('document already exists')
        self._database.rows[self.path] = deepcopy(data)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')


class StrictFirestoreCollection:
    def __init__(self, database: StrictFirestore, path: tuple[str, ...]):
        self._database = database
        self._path = path

    def document(self, name: str) -> StrictFirestoreDocument:
        return StrictFirestoreDocument(self._database, (*self._path, name))

    def where(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')

    def stream(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')


class StrictFirestoreTransaction:
    def __init__(self, database: StrictFirestore, *, allow_reads_after_writes: bool = False):
        self._database = database
        self._allow_reads_after_writes = allow_reads_after_writes
        self.lock = database.lock
        self.creates: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.sets: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.updates: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.has_written = False
        self._read_only = False
        self._max_attempts = 1
        self._id: bytes | None = None

    # The Firestore ``@transactional`` decorator drives these lifecycle hooks.
    # They deliberately keep this fixture single-attempt: it guards production
    # read-before-write ordering without pretending to model contention retries.
    def _clean_up(self) -> None:
        self._id = None

    def _begin(self, retry_id: bytes | None = None) -> None:
        self._id = retry_id or b'strict-firestore-transaction'

    def _commit(self) -> None:
        return None

    def _rollback(self) -> None:
        return None

    def _assert_read_allowed(self) -> None:
        if self.has_written and not self._allow_reads_after_writes:
            raise ReadAfterWriteError('Firestore transactions must complete all reads before the first write')

    def _assert_reference_belongs(self, ref: StrictFirestoreDocument) -> None:
        if ref._database is not self._database:
            raise ForeignTransactionError('Firestore transaction and document reference must belong to the same store')

    def set(self, ref: StrictFirestoreDocument, data: dict[str, Any]) -> None:
        self._assert_reference_belongs(ref)
        self.has_written = True
        payload = deepcopy(data)
        self.sets.append((ref.path, payload))
        self._database.rows[ref.path] = payload

    def create(self, ref: StrictFirestoreDocument, data: dict[str, Any]) -> None:
        self._assert_reference_belongs(ref)
        self.has_written = True
        if ref.path in self._database.rows:
            raise RuntimeError('document already exists')
        payload = deepcopy(data)
        self.creates.append((ref.path, payload))
        self._database.rows[ref.path] = payload

    def update(self, ref: StrictFirestoreDocument, patch: dict[str, Any]) -> None:
        self._assert_reference_belongs(ref)
        self.has_written = True
        if ref.path not in self._database.rows:
            raise RuntimeError('missing row')
        payload = deepcopy(patch)
        self.updates.append((ref.path, payload))
        self._database.rows[ref.path].update(payload)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')

    def get(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')

    def get_all(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')


class StrictFirestore:
    """In-memory Firestore double with strict read-before-write transactions.

    ``allow_reads_after_writes`` is an explicit, greppable opt-out for tests
    that intentionally do not exercise Firestore transaction semantics. It
    defaults to ``False`` and must not be used by production-boundary tests.
    """

    def __init__(
        self,
        rows: dict[tuple[str, ...], dict[str, Any]] | None = None,
        *,
        allow_reads_after_writes: bool = False,
    ):
        self.rows = deepcopy(rows or {})
        self.lock = RLock()
        self._allow_reads_after_writes = allow_reads_after_writes
        self.transactions: list[StrictFirestoreTransaction] = []

    def collection(self, name: str) -> StrictFirestoreCollection:
        return StrictFirestoreCollection(self, (name,))

    def transaction(self) -> StrictFirestoreTransaction:
        transaction = StrictFirestoreTransaction(self, allow_reads_after_writes=self._allow_reads_after_writes)
        self.transactions.append(transaction)
        return transaction
