"""Neutral ``db_client`` adapter — a Firestore-Client-shaped facade over the storage port (ADR-0044).

Upstream threads ``db_client`` (a ``google.cloud.firestore.Client``) through the memory/task
subsystem (``db_client.document(path)`` / ``.collection(path)`` / ``.transaction()`` / ``.get_all``).
Our on-prem port replaces raw Firestore with the neutral store port, but hand-rewriting every injected
call site is unsustainable across merges. Instead this facade exposes the small Firestore-Client
surface upstream uses, backed by ``get_document_store()`` (Mongo on-prem), so upstream code runs
verbatim. It is installed at ``database/_client.py::get_firestore_client()`` only when
``STORAGE_BACKEND != firestore``; the Firestore backend keeps the real SDK client.

Scope: this is the ONE place the port is allowed to speak Firestore's client shape (ADR-0044 amends
ADR-0004 for this injection surface); everywhere else the rule stays "use the neutral store, don't
emulate Firestore". Paths are logical ("users/{uid}/people/{pid}"); payloads are plain dicts.
"""

from __future__ import annotations

import contextlib
from typing import Any, Dict, Iterable, List, Optional

from google.api_core import exceptions as _gexc

from database.store import sentinels as _neutral
from database.store.errors import AlreadyExists as _StoreAlreadyExists
from database.store.errors import NotFound as _StoreNotFound
from database.store.records import StoredDocument

# Google sentinels/types are only needed to RECOGNISE values upstream passes in; importing them here
# keeps the recognition in one place. Absent SDK (stubbed test env) -> the identity checks simply
# never match, which is correct for a pure-neutral payload.
try:  # pragma: no cover - import shape depends on the installed SDK
    from google.cloud import firestore as _fs
    from google.cloud.firestore_v1.transforms import ArrayRemove as _FsArrayRemove
    from google.cloud.firestore_v1.transforms import ArrayUnion as _FsArrayUnion
    from google.cloud.firestore_v1.transforms import Increment as _FsIncrement
except Exception:  # pragma: no cover
    _fs = None
    _FsArrayUnion = _FsArrayRemove = _FsIncrement = ()  # type: ignore[assignment]

# Firestore query direction constants, resolved defensively.
_DESCENDING = getattr(getattr(_fs, "Query", None), "DESCENDING", "DESCENDING") if _fs else "DESCENDING"

# Firestore comparison op strings -> neutral store ops (ports.Filter). The store's Mongo adapter
# accepts these directly; unsupported ops surface as a clear error rather than silently mis-querying.
_OP_MAP = {
    "==": "==",
    "!=": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
    "in": "in",
    "not-in": "not-in",
    "array_contains": "array_contains",
    "array_contains_any": "array_contains_any",
}


def _to_neutral(value: Any) -> Any:
    """Translate google Firestore sentinels/transforms in a payload into neutral store sentinels."""
    if _fs is not None:
        if value is _fs.SERVER_TIMESTAMP:
            return _neutral.SERVER_TIMESTAMP
        if value is _fs.DELETE_FIELD:
            return _neutral.DELETE
    if _FsArrayUnion and isinstance(value, _FsArrayUnion):
        return _neutral.ArrayUnion(list(value.values))
    if _FsArrayRemove and isinstance(value, _FsArrayRemove):
        return _neutral.ArrayRemove(list(value.values))
    if _FsIncrement and isinstance(value, _FsIncrement):
        return _neutral.Increment(value.value)
    if isinstance(value, dict):
        return {k: _to_neutral(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_neutral(v) for v in value]
    return value


def _neutral_data(data: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _to_neutral(v) for k, v in data.items()}


def _is_transient_mongo_txn_error(exc: Exception) -> bool:
    """True for a Mongo transaction error the transaction machinery should retry (write conflict /
    unknown-commit-result), surfaced via PyMongo's error labels."""
    has_label = getattr(exc, "has_error_label", None)
    if not callable(has_label):
        return False
    return bool(has_label("TransientTransactionError") or has_label("UnknownTransactionCommitResult"))


@contextlib.contextmanager
def _firestore_errors():
    """Re-raise neutral store errors as the ``google.api_core`` errors upstream code catches, so
    ``except NotFound`` / ``except AlreadyExists`` around a ``db_client`` write behave identically on
    the Mongo-backed facade as on real Firestore (ADR-0044). Without this an ``update`` on a missing
    doc raises the neutral ``NotFound`` and escapes an upstream ``except FirestoreNotFound``."""
    try:
        yield
    except _StoreNotFound as exc:
        raise _gexc.NotFound(str(exc)) from exc
    except _StoreAlreadyExists as exc:
        raise _gexc.AlreadyExists(str(exc)) from exc


class _Snapshot:
    """Firestore ``DocumentSnapshot`` shape over a neutral :class:`StoredDocument`."""

    def __init__(self, doc_ref: "_DocRef", stored: StoredDocument) -> None:
        self.reference = doc_ref
        self.id = doc_ref.id
        self._stored = stored

    @property
    def exists(self) -> bool:
        return self._stored.exists

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return self._stored.to_dict()

    def get(self, field_path: str) -> Any:
        data = self._stored.to_dict() or {}
        # Firestore supports dotted field paths; walk them.
        cur: Any = data
        for part in field_path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    @property
    def create_time(self) -> Any:
        return self._stored.updated_at

    @property
    def update_time(self) -> Any:
        return self._stored.updated_at


class _DocRef:
    """Firestore ``DocumentReference`` shape. Addressed by full logical path."""

    def __init__(self, client: "NeutralFirestoreClient", path: str) -> None:
        self._client = client
        self.path = path.strip("/")
        self.id = self.path.rsplit("/", 1)[-1]

    @property
    def reference(self) -> "_DocRef":
        return self

    def collection(self, sub: str) -> "_CollRef":
        return _CollRef(self._client, f"{self.path}/{sub}")

    def collections(self) -> Iterable["_CollRef"]:
        # Subcollections are not enumerable from a document in the neutral port; the domain addresses
        # them by known name. Return empty so recursive-delete helpers terminate rather than crash.
        return []

    def get(self, transaction: Optional["_FacadeTransaction"] = None, *, timeout: Any = None, **_: Any) -> _Snapshot:
        # ``timeout``/other Firestore read kwargs (retry, ...) are network-RPC concerns; a Mongo point
        # read through the store port is local, so they are accepted and ignored.
        del timeout
        if transaction is not None:
            return _Snapshot(self, transaction._read(self.path))
        return _Snapshot(self, self._client._store.get(self.path))

    def set(self, data: Dict[str, Any], merge: bool = False) -> None:
        self._client._store.set(self.path, _neutral_data(data), merge=merge)

    def update(self, data: Dict[str, Any], option: Any = None) -> None:
        # ``option`` (Firestore LastUpdateOption) is an optimistic-concurrency precondition ("only
        # write if the doc's revision is unchanged"). The neutral store port has no revision-
        # precondition primitive yet, so it is accepted but not enforced on Mongo (D37 debt). Callers
        # that pass it (review_queue self-heal) already gate the write on a status check, so a rare
        # lost-update is bounded, not silent corruption.
        del option
        with _firestore_errors():
            self._client._store.update(self.path, _neutral_data(data))

    def create(self, data: Dict[str, Any]) -> None:
        with _firestore_errors():
            self._client._store.create(self.path, _neutral_data(data))

    def delete(self) -> None:
        with _firestore_errors():
            self._client._store.delete(self.path)


class _Query:
    """Firestore ``Query`` shape: immutable builder that materialises via the neutral store."""

    def __init__(
        self,
        client: "NeutralFirestoreClient",
        collection: str,
        *,
        filters: Optional[List[Any]] = None,
        order_by: Optional[List[Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        start_after: Optional[Any] = None,
    ) -> None:
        self._client = client
        self._collection = collection.strip("/")
        self._filters = list(filters or [])
        self._order_by = list(order_by or [])
        self._limit = limit
        self._offset = offset
        self._start_after = start_after

    def _clone(self, **kw: Any) -> "_Query":
        base = dict(
            filters=self._filters,
            order_by=self._order_by,
            limit=self._limit,
            offset=self._offset,
            start_after=self._start_after,
        )
        base.update(kw)
        return _Query(self._client, self._collection, **base)

    def where(self, field_path: Any = None, op_string: Any = None, value: Any = None, *, filter: Any = None) -> "_Query":
        if filter is not None:  # modern FieldFilter form
            field_path = getattr(filter, "field_path", None)
            op_string = getattr(filter, "op_string", None)
            value = getattr(filter, "value", None)
        op = _OP_MAP.get(op_string)
        if op is None:
            raise NotImplementedError(f"unsupported query operator: {op_string!r}")
        return self._clone(filters=self._filters + [(field_path, op, value)])

    def order_by(self, field_path: str, direction: Any = "ASCENDING") -> "_Query":
        d = "desc" if direction == _DESCENDING or str(direction).lower().startswith("desc") else "asc"
        return self._clone(order_by=self._order_by + [(field_path, d)])

    def limit(self, count: int) -> "_Query":
        return self._clone(limit=count)

    def offset(self, count: int) -> "_Query":
        return self._clone(offset=count)

    def start_after(self, snapshot_or_values: Any) -> "_Query":
        return self._clone(start_after=snapshot_or_values)

    def select(self, field_paths: Any) -> "_Query":
        # Projection is a read optimisation; the neutral store returns full docs. Safe to ignore.
        return self

    def _run(self) -> List[StoredDocument]:
        order = None
        direction = "asc"
        if self._order_by:
            if len(self._order_by) == 1:
                order, direction = self._order_by[0]
            else:
                order = self._order_by  # multi-field: (field, dir) pairs
        return self._client._store.query(
            self._collection,
            filters=self._filters or None,
            order_by=order,
            direction=direction,
            limit=self._limit,
            offset=self._offset,
        )

    def stream(self, transaction: Optional["_FacadeTransaction"] = None) -> Iterable[_Snapshot]:
        for stored in self._run():
            yield _Snapshot(_DocRef(self._client, stored.path), stored)

    def get(self) -> List[_Snapshot]:
        return list(self.stream())


class _CollRef(_Query):
    """Firestore ``CollectionReference``: a query plus document addressing."""

    def document(self, doc_id: Optional[str] = None) -> _DocRef:
        if doc_id is None:
            from database.document_ids import document_id_from_seed  # local: avoids import cycle

            doc_id = document_id_from_seed(self._collection)
        return _DocRef(self._client, f"{self._collection}/{doc_id}")

    def list_documents(self) -> List[_DocRef]:
        return [_DocRef(self._client, s.path) for s in self._run()]

    def add(self, data: Dict[str, Any]) -> _DocRef:
        ref = self.document()
        ref.create(data)
        return ref


class _FacadeTransaction:
    """A Firestore ``Transaction`` shape over one open Mongo session transaction.

    Satisfies both upstream's ``transactional`` fallback (``_begin``/``_commit``/``_rollback``/
    ``_clean_up``) and google's real decorator (which calls the same lifecycle plus reads ``_id``).
    Reads and writes share one session so read-modify-write stays atomic (optimistic concurrency).
    """

    _max_attempts = 5
    _read_only = False  # google's @transactional reads this to decide whether Aborted is retryable

    def __init__(self, client: "NeutralFirestoreClient") -> None:
        self._client = client
        self._session: Any = None
        self._id: Any = None

    # --- lifecycle (driven by the decorator/wrapper) ---
    def _begin(self, retry_id: Any = None) -> None:
        mongo = self._client._store._mongo_client  # facade is Mongo-only (Firestore keeps the SDK client)
        self._session = mongo.start_session()
        self._session.start_transaction()
        self._id = id(self._session)

    def _commit(self) -> Any:
        if self._session is None:
            return []
        try:
            self._session.commit_transaction()
        except Exception as exc:  # translate a Mongo write-conflict into the retry signal the decorator expects
            if _is_transient_mongo_txn_error(exc):
                from google.api_core.exceptions import Aborted

                raise Aborted(str(exc)) from exc
            raise
        return []

    def _rollback(self) -> None:
        if self._session is not None:
            try:
                self._session.abort_transaction()
            except Exception:  # already terminated
                pass

    def _clean_up(self) -> None:
        if self._session is not None:
            self._session.end_session()
        self._session = None
        self._id = None

    # --- read/write within the transaction (upstream calls these with a _DocRef) ---
    def _read(self, path: str) -> StoredDocument:
        return self._client._store._get(path, session=self._session)

    def get(self, ref: _DocRef, **_: Any) -> _Snapshot:
        return _Snapshot(ref, self._read(ref.path))

    def set(self, ref: _DocRef, data: Dict[str, Any], merge: bool = False) -> None:
        self._client._store._set(ref.path, _neutral_data(data), merge=merge, session=self._session)

    def update(self, ref: _DocRef, data: Dict[str, Any]) -> None:
        with _firestore_errors():
            self._client._store._update(ref.path, _neutral_data(data), session=self._session)

    def create(self, ref: _DocRef, data: Dict[str, Any]) -> None:
        with _firestore_errors():
            self._client._store._create(ref.path, _neutral_data(data), session=self._session)

    def delete(self, ref: _DocRef) -> None:
        with _firestore_errors():
            self._client._store._delete(ref.path, session=self._session)


class _FacadeBatch:
    """Firestore ``WriteBatch`` shape over the neutral store batch (ref -> path)."""

    def __init__(self, client: "NeutralFirestoreClient") -> None:
        self._batch = client._store.batch()

    def set(self, ref: _DocRef, data: Dict[str, Any], merge: bool = False, option: Any = None) -> None:
        del option  # LastUpdateOption precondition: accepted, not enforced on Mongo (D37 debt)
        self._batch.set(ref.path, _neutral_data(data), merge=merge)

    def update(self, ref: _DocRef, data: Dict[str, Any], option: Any = None) -> None:
        del option
        self._batch.update(ref.path, _neutral_data(data))

    def delete(self, ref: _DocRef, option: Any = None) -> None:
        del option
        self._batch.delete(ref.path)

    def commit(self) -> None:
        self._batch.commit()


class NeutralFirestoreClient:
    """The ``db_client`` upstream threads, backed by the neutral store port (ADR-0044).

    Only the surface upstream actually calls is implemented: ``document`` / ``collection`` /
    ``transaction`` / ``get_all`` / ``batch``. Extend here (and the boundary guard) if a merge starts
    using a new client method — that is the one maintenance point instead of hundreds of call sites.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    def document(self, path: str) -> _DocRef:
        return _DocRef(self, path)

    def collection(self, path: str) -> _CollRef:
        return _CollRef(self, path)

    def transaction(self, *_: Any, **__: Any) -> _FacadeTransaction:
        return _FacadeTransaction(self)

    def batch(self) -> _FacadeBatch:
        return _FacadeBatch(self)

    def get_all(self, references: Iterable[_DocRef], *_: Any, **__: Any) -> Iterable[_Snapshot]:
        for ref in references:
            yield ref.get()

    def collection_group(self, group_id: str) -> "_GroupQuery":
        return _GroupQuery(self, group_id)


class _GroupQuery:
    """Firestore ``collection_group`` shape over the neutral ``query_group`` (cross-parent sweep)."""

    def __init__(self, client: "NeutralFirestoreClient", group: str, **kw: Any) -> None:
        self._client = client
        self._group = group
        self._filters: List[Any] = kw.get("filters", [])
        self._limit = kw.get("limit")

    def where(self, field_path: Any = None, op_string: Any = None, value: Any = None, *, filter: Any = None) -> "_GroupQuery":
        if filter is not None:
            field_path = getattr(filter, "field_path", None)
            op_string = getattr(filter, "op_string", None)
            value = getattr(filter, "value", None)
        op = _OP_MAP.get(op_string)
        if op is None:
            raise NotImplementedError(f"unsupported query operator: {op_string!r}")
        return _GroupQuery(self._client, self._group, filters=self._filters + [(field_path, op, value)], limit=self._limit)

    def limit(self, count: int) -> "_GroupQuery":
        return _GroupQuery(self._client, self._group, filters=self._filters, limit=count)

    def stream(self, transaction: Optional[_FacadeTransaction] = None) -> Iterable[_Snapshot]:
        for stored in self._client._store.query_group(self._group, filters=self._filters or None, limit=self._limit):
            yield _Snapshot(_DocRef(self._client, stored.path), stored)


__all__ = ["NeutralFirestoreClient"]
