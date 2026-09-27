"""Narrow Firestore transaction fixture for ordering-sensitive unit tests.

This fixture models document-reference ``get(transaction=...)`` plus transaction
``create``, ``set``, and ``update``. It enforces Firestore's rule that every
transactional read must occur before the first transactional write.

It also supports the direct-document is_locked projection used at dispatch,
and equality-only, document-id projections with a positive limit,
proven by daily_memory_sweep_emulator_test.py for legacy window fence admission.
It deliberately does not model other queries, deletes, commit/rollback visibility,
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


_SUPPORTED_OPERATIONS = (
    'document get/create, transaction-bound document get, transaction create/set/update, bounded equality id queries'
)


class StrictFirestoreSnapshot:
    def __init__(self, data: dict[str, Any] | None):
        self._data = deepcopy(data)
        self.exists = data is not None
        self.reference: Any = None

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._data)


class StrictFirestoreDocument:
    def __init__(self, database: StrictFirestore, path: tuple[str, ...]):
        self._database = database
        self.path = path

    def collection(self, name: str) -> StrictFirestoreCollection:
        return StrictFirestoreCollection(self._database, (*self.path, name))

    def get(
        self, transaction: StrictFirestoreTransaction | None = None, *, field_paths: list[str] | None = None
    ) -> StrictFirestoreSnapshot:
        if transaction is not None:
            transaction._assert_reference_belongs(self)
            transaction._assert_read_allowed()
        data = self._database.rows.get(self.path)
        if field_paths is not None and data is not None:
            if field_paths != ["is_locked"]:
                raise UnsupportedFirestoreOperationError("only the sweep privacy projection is supported")
            data = {key: value for key, value in data.items() if key in field_paths}
        return StrictFirestoreSnapshot(data)

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

    def where(self, *args: Any, filter: Any = None) -> StrictFirestoreIdQuery:
        if args or filter is None:
            raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')
        return StrictFirestoreIdQuery(self._database, self._path).where(filter=filter)

    def stream(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')


class StrictFirestoreIdQuery:
    """Narrow existence query; no ordering, content projections, or unbounded scans."""

    def __init__(self, database: StrictFirestore, path: tuple[str, ...]):
        self._database = database
        self._path = path
        self._filters: tuple[tuple[str, Any], ...] = ()
        self._ids_only = False
        self._limit: int | None = None

    def _copy(self) -> StrictFirestoreIdQuery:
        result = StrictFirestoreIdQuery(self._database, self._path)
        result._filters = self._filters
        result._ids_only = self._ids_only
        result._limit = self._limit
        return result

    def where(self, *, filter: Any) -> StrictFirestoreIdQuery:
        if filter.op_string != '==':
            raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')
        result = self._copy()
        result._filters += ((filter.field_path, filter.value),)
        return result

    def select(self, fields: tuple[str, ...]) -> StrictFirestoreIdQuery:
        if fields:
            raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')
        result = self._copy()
        result._ids_only = True
        return result

    def limit(self, count: int) -> StrictFirestoreIdQuery:
        if type(count) is not int or count <= 0:
            raise ValueError('query limit must be a positive integer')
        result = self._copy()
        result._limit = count
        return result

    def stream(self, *, transaction: StrictFirestoreTransaction):
        if not self._filters or not self._ids_only or self._limit is None:
            raise UnsupportedFirestoreOperationError(f'StrictFirestore supports only {_SUPPORTED_OPERATIONS}')
        if transaction._database is not self._database:
            raise ForeignTransactionError('Firestore transaction and query must belong to the same store')
        transaction._assert_read_allowed()
        rows = []
        for path, value in sorted(self._database.rows.items()):
            if path[:-1] == self._path and all(
                field in value and value[field] == expected for field, expected in self._filters
            ):
                snapshot = StrictFirestoreSnapshot({})
                snapshot.reference = StrictFirestoreDocument(self._database, path)
                rows.append(snapshot)
        return iter(rows[: self._limit])


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

    def document(self, path: str) -> StrictFirestoreDocument:
        segments = tuple(segment for segment in path.split('/') if segment)
        if len(segments) < 2 or len(segments) % 2 != 0:
            raise ValueError('Firestore document paths require an even number of non-empty segments')
        return StrictFirestoreDocument(self, segments)

    def transaction(self) -> StrictFirestoreTransaction:
        transaction = StrictFirestoreTransaction(self, allow_reads_after_writes=self._allow_reads_after_writes)
        self.transactions.append(transaction)
        return transaction
