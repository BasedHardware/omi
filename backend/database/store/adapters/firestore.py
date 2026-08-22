"""Firestore implementation of the neutral ``DocumentStore`` port (ADR-0003, first-class default).

This is the **reference adapter**: it wraps the persistence-boundary client (``database._client``)
and the SDK primitives the codebase already relies on (``FieldFilter``, ``@transactional``,
``run_transactional`` for expired-transaction recovery, ``delete_collection_recursive`` for the
non-cascading delete). Its observable behavior defines the contract that every other adapter
(Mongo, ArcadeDB) must match — the dual-backend contract test asserts parity against it.

Addressing is by logical path string. Firestore paths already are that: an even number of segments
is a document (``users/{uid}``, ``users/{uid}/people/{pid}``); an odd number is a collection
(``users``, ``users/{uid}/people``). Neutral sentinels and ``(field, op, value)`` filters are
translated to their Firestore equivalents at this boundary and nowhere else.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter, LastUpdateOption, transactional
from google.cloud.firestore_v1.field_path import FieldPath as _FieldPath

from google.api_core.exceptions import (
    AlreadyExists as _FirestoreAlreadyExists,
    Conflict as _FirestoreConflict,
    FailedPrecondition as _FirestoreFailedPrecondition,
    NotFound as _FirestoreNotFound,
)

from ..._client import db as _boundary_db, delete_collection_recursive, run_transactional
from ..errors import AlreadyExists, NotFound, PreconditionFailed
from ..records import StoredDocument
from ..sentinels import DELETE, SERVER_TIMESTAMP, ArrayRemove, ArrayUnion, Increment
from ..ports import Filter

_DIRECTION = {
    "asc": firestore.Query.ASCENDING,
    "desc": firestore.Query.DESCENDING,
}


def _to_firestore_value(value: Any) -> Any:
    """Map a neutral field-transform sentinel to its Firestore primitive (values pass through)."""
    if value is DELETE:
        return firestore.DELETE_FIELD
    if value is SERVER_TIMESTAMP:
        return firestore.SERVER_TIMESTAMP
    if isinstance(value, ArrayUnion):
        return firestore.ArrayUnion(value.values)
    if isinstance(value, ArrayRemove):
        return firestore.ArrayRemove(value.values)
    if isinstance(value, Increment):
        return firestore.Increment(value.amount)
    return value


def _translate(data: Dict[str, Any]) -> Dict[str, Any]:
    """Translate neutral sentinels appearing as top-level field values.

    Firestore field transforms are only valid at a field path (top-level key or dotted key), never
    nested inside a map value — so translating the top level is complete and correct.
    """
    return {key: _to_firestore_value(value) for key, value in data.items()}


def _translate_update(data: Dict[str, Any]) -> Dict[Any, Any]:
    """Like ``_translate`` but for ``update()``, where a dotted key is a nested field PATH.

    Firestore's update() parses dotted string keys and mis-handles segments that are not simple
    identifiers (e.g. a raw UUID key id with hyphens embedded in ``grants...keys.<uuid>``). Rebuild
    each dotted key through FieldPath.to_api_repr(), which backtick-escapes such segments into a
    valid field-path string; simple keys pass through unchanged.
    """
    return {
        (_FieldPath(*key.split(".")).to_api_repr() if "." in key else key): _to_firestore_value(value)
        for key, value in data.items()
    }


def _ensure_timezone_aware(dt: datetime) -> datetime:
    """A naive datetime is assumed UTC (mirrors the pre-port database boundary)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _revision(snapshot: Any) -> Any:
    """Neutral last-write revision (ADR-0017) from the Firestore snapshot ``update_time``.

    The production client exposes ``DatetimeWithNanoseconds`` (a ``datetime`` subclass), while
    Firestore emulators and fakes may expose protobuf-like ``ToDatetime()`` or raw
    ``seconds``/``nanos`` values. This SDK variation is normalized here — at the adapter boundary —
    so the neutral ``updated_at`` is always an aware ``datetime`` or ``None``.
    """
    value = getattr(snapshot, "update_time", None)
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_timezone_aware(value)

    to_datetime = getattr(value, "ToDatetime", None)
    if callable(to_datetime):
        try:
            return _ensure_timezone_aware(to_datetime(tzinfo=timezone.utc))
        except (TypeError, ValueError, OverflowError):
            return None

    try:
        seconds = getattr(value, "seconds")
        nanos = getattr(value, "nanos")
        if isinstance(seconds, str) and isinstance(nanos, str):
            timestamp = float(f"{seconds}.{nanos}")
        else:
            timestamp = float(seconds) + (float(nanos) / 1_000_000_000)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
        return None


def _snapshot_to_record(snapshot: Any, path: str) -> StoredDocument:
    if not getattr(snapshot, "exists", False):
        return StoredDocument.missing(path)
    return StoredDocument(
        id=snapshot.id,
        path=path,
        exists=True,
        data=snapshot.to_dict(),
        updated_at=_revision(snapshot),
        created_at=getattr(snapshot, "create_time", None),
    )


def _record_from_query(snapshot: Any) -> StoredDocument:
    reference = getattr(snapshot, "reference", None)
    path = getattr(reference, "path", None) or snapshot.id
    return StoredDocument(
        id=snapshot.id,
        path=path,
        exists=True,
        data=snapshot.to_dict(),
        updated_at=_revision(snapshot),
        created_at=getattr(snapshot, "create_time", None),
    )


def _last_update_option(if_updated_at: Any) -> Any:
    """Neutral ``if_updated_at`` precondition -> Firestore ``LastUpdateOption`` (or ``None``)."""
    return LastUpdateOption(if_updated_at) if if_updated_at is not None else None


class _FirestoreBatch:
    """Neutral batched-write accumulator over a Firestore WriteBatch (atomic per commit)."""

    def __init__(self, client: Any):
        self._client = client
        self._batch = client.batch()

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._batch.set(self._client.document(path), _translate(data), merge=merge)

    def create(self, path: str, data: Dict[str, Any]) -> None:
        # Create-if-absent inside the atomic batch (staged-task recovery pairs it with a guarded
        # delete). A collision raises AlreadyExists at commit — mapped to the neutral error below.
        self._batch.create(self._client.document(path), _translate(data))

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        self._batch.update(
            self._client.document(path), _translate_update(data), option=_last_update_option(if_updated_at)
        )

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        self._batch.delete(self._client.document(path), option=_last_update_option(if_updated_at))

    def commit(self) -> None:
        # A LastUpdateOption that no longer holds fails the whole atomic batch here — map it to the
        # neutral PreconditionFailed so callers branch identically to the Mongo adapter.
        try:
            self._batch.commit()
        except _FirestoreFailedPrecondition as exc:
            raise PreconditionFailed("batch") from exc
        except _FirestoreNotFound as exc:
            # A batch update of a missing doc raises Firestore NotFound at commit — map to the neutral
            # NotFound so callers branch identically to the Mongo adapter (cubic PR 10887 #11b).
            raise NotFound("batch") from exc
        except (_FirestoreAlreadyExists, _FirestoreConflict) as exc:
            # A batch create of an existing doc raises AlreadyExists at commit — map to the neutral
            # AlreadyExists so create-if-absent recovery branches identically on both backends.
            raise AlreadyExists("batch") from exc


class _FirestoreTransaction:
    """Neutral transaction handle over a Firestore transaction. Reads/writes are path-based."""

    def __init__(self, transaction: Any, client: Any, store: Any = None):
        self._transaction = transaction
        self._client = client
        self._store = store

    def get(self, path: str) -> StoredDocument:
        snapshot = self._client.document(path).get(transaction=self._transaction)
        return _snapshot_to_record(snapshot, path)

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._transaction.set(self._client.document(path), _translate(data), merge=merge)

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        try:
            self._transaction.update(
                self._client.document(path), _translate_update(data), option=_last_update_option(if_updated_at)
            )
        except _FirestoreNotFound as exc:
            raise NotFound(path) from exc

    def create(self, path: str, data: Dict[str, Any]) -> None:
        # Firestore buffers the write with an exists=False precondition; the conflict surfaces at
        # commit (mapped to the neutral AlreadyExists in run_transaction), not from this call.
        self._transaction.create(self._client.document(path), _translate(data))

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        self._transaction.delete(self._client.document(path), option=_last_update_option(if_updated_at))

    def query(self, collection: str, **kw: Any) -> List[StoredDocument]:
        return self._store.query(collection, transaction=self._transaction, **kw)


class FirestoreDocumentStore:
    """``DocumentStore`` backed by Google Cloud Firestore."""

    def __init__(self, client: Any = None):
        # Default to the lazy boundary handle so the conftest global patch that swaps ``db`` keeps
        # reaching these ops, matching the WP1 document_store contract.
        self._client = client if client is not None else _boundary_db

    # --- point ops ---
    def get(
        self, path: str, *, fields: Optional[Sequence[str]] = None, timeout: Optional[float] = None
    ) -> StoredDocument:
        ref = self._client.document(path)
        # ``timeout`` (seconds) is the read-RPC deadline; omit the kwarg entirely when None so the
        # SDK default applies rather than passing ``timeout=None`` (which some retries treat as 0).
        kw: Dict[str, Any] = {} if timeout is None else {"timeout": timeout}
        snapshot = ref.get(list(fields), **kw) if fields is not None else ref.get(**kw)
        return _snapshot_to_record(snapshot, path)

    def exists(self, path: str) -> bool:
        return bool(getattr(self._client.document(path).get(), "exists", False))

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._client.document(path).set(_translate(data), merge=merge)

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        try:
            self._client.document(path).update(_translate_update(data), option=_last_update_option(if_updated_at))
        except _FirestoreNotFound as exc:
            raise NotFound(path) from exc
        except _FirestoreFailedPrecondition as exc:
            raise PreconditionFailed(path) from exc

    def create(self, path: str, data: Dict[str, Any]) -> None:
        try:
            self._client.document(path).create(_translate(data))
        except (_FirestoreAlreadyExists, _FirestoreConflict) as exc:
            raise AlreadyExists(path) from exc

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        try:
            self._client.document(path).delete(option=_last_update_option(if_updated_at))
        except _FirestoreFailedPrecondition as exc:
            raise PreconditionFailed(path) from exc

    # --- collection ops ---
    @staticmethod
    def _to_name_refs(resolver: Any, op: str, value: Any) -> Any:
        """Convert a neutral ``__name__`` filter value into the ``DocumentReference`` (or list of them)
        Firestore's ``__key__`` filter requires. A scoped query/count resolves ids relative to the
        collection (``collection.document``); a collection-group query resolves full paths
        (``client.document``). Membership ops (``in``/``not-in``/``array_contains_any``) carry a LIST of
        ids, so each element is converted — passing the whole list to one ``.document()`` raised
        ``TypeError`` (cubic PR 10887 firestore.py:276); ``count()`` skipped the conversion entirely, so
        Firestore rejected the bare-string ``__key__`` value (firestore.py:277)."""
        if op in ("in", "not-in", "array_contains_any"):
            return [resolver(v) for v in value]
        return resolver(value)

    def query(
        self,
        collection: str,
        *,
        filters: Optional[Iterable[Filter]] = None,
        order_by: Optional[str] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        fields: Optional[Sequence[str]] = None,
        start_after: Optional[Dict[str, Any]] = None,
        transaction: Any = None,
    ) -> List[StoredDocument]:
        """``transaction`` runs the read inside that Firestore transaction (BACKLOG L24).

        Firestore's own rule applies and is worth knowing at the call site: a transaction reads first
        and writes second, so a query after a write in the same transaction raises
        ``ReadAfterWriteError`` from the SDK — measured, not inferred (ADR-0070).
        """
        coll = self._client.collection(collection)
        query: Any = coll
        for field, op, value in filters or ():
            if field == "__name__":
                # Firestore's document-name filter compares against a DocumentReference, not the bare id
                # (cubic PR 10887 #3). The neutral value is the document id relative to this collection;
                # for in/not-in it is a LIST of ids -> one reference each.
                value = self._to_name_refs(coll.document, op, value)
            query = query.where(filter=FieldFilter(field, op, value))
        specs = [(order_by, direction)] if isinstance(order_by, str) else list(order_by or [])
        for _field, _dir in specs:
            query = query.order_by(_field, direction=_DIRECTION[_dir])
        if start_after is not None:
            # Composite keyset cursor (cubic PR 10887 #4): one value per REAL order field followed by the
            # document id for the __name__ tiebreak, so the cursor arity equals the number of order fields.
            # Append __name__ when the caller didn't (single/multi real fields) so ties never skip/dup.
            values = start_after.get("values")
            if values is None:
                values = [start_after["value"]] if "value" in start_after else []
            real = [f for f, _ in specs if f != "__name__"]
            if not any(_field == "__name__" for _field, _ in specs):
                query = query.order_by("__name__", direction=_DIRECTION[specs[-1][1]] if specs else _DIRECTION["asc"])
            # One cursor value per real order field (drop any extra from a legacy single-value cursor on a
            # no-order query), then the document id for the __name__ tiebreak.
            query = query.start_after(list(values)[: len(real)] + [start_after["id"]])
        if fields is not None:
            query = query.select(list(fields))
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return [_record_from_query(snapshot) for snapshot in query.stream(transaction=transaction)]

    def count(self, collection: str, *, filters: Optional[Iterable[Filter]] = None) -> int:
        coll = self._client.collection(collection)
        query: Any = coll
        for field, op, value in filters or ():
            if field == "__name__":
                # Same DocumentReference conversion as query() — Firestore's aggregation rejects a bare
                # __key__ string, so a __name__-filtered count() would fail/return zero without this
                # (cubic PR 10887 firestore.py:277).
                value = self._to_name_refs(coll.document, op, value)
            query = query.where(filter=FieldFilter(field, op, value))
        result = query.count().get()
        return int(result[0][0].value)

    def query_group(
        self,
        group: str,
        *,
        filters: Optional[Iterable[Filter]] = None,
        order_by: Optional[str] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        start_after: Optional[str] = None,
    ) -> List[StoredDocument]:
        query: Any = self._client.collection_group(group)
        for field, op, value in filters or ():
            if field == "__name__":
                # In a collection group the document name IS the full logical path (the neutral facade
                # sends the full path for a group __name__ filter), so resolve it with client.document,
                # not a collection-relative id. Firestore's __key__ filter needs a DocumentReference.
                value = self._to_name_refs(self._client.document, op, value)
            query = query.where(filter=FieldFilter(field, op, value))
        specs = [(order_by, direction)] if isinstance(order_by, str) else list(order_by or [])
        # A __name__ order on a collection group is the implicit document-name keyset (Firestore's
        # default order), so drop it — it's redundant and would otherwise be rejected below when combined
        # with start_after (cubic PR 10887 #2).
        specs = [(f, d) for f, d in specs if f != "__name__"]
        for _field, _dir in specs:
            query = query.order_by(_field, direction=_DIRECTION[_dir])
        if start_after is not None:
            # Document-name keyset: order by __name__ and resume after the cursor path's position. The
            # cursor is a DocumentReference — it positions by path even if the document no longer exists
            # (passing it bare, not in a list, breaks the SDK cursor normalization). This keyset supplies
            # a SINGLE cursor value, so it cannot combine with an explicit order_by (which would need a
            # value per order field) — reject that rather than build an invalid cursor (cubic 10887 A7).
            if specs:
                raise NotImplementedError(
                    "query_group start_after (document-name keyset) does not support combining with an explicit order_by"
                )
            query = query.order_by('__name__')
            query = query.start_after([self._client.document(start_after)])
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        # _record_from_query fills each record's path from the snapshot reference, so a
        # collection-group result carries its full logical path (parent recoverable by the caller).
        return [_record_from_query(snapshot) for snapshot in query.stream()]

    def get_many(self, collection: str, ids: Sequence[str]) -> List[StoredDocument]:
        if not ids:
            return []
        collection_ref = self._client.collection(collection)
        refs = [collection_ref.document(doc_id) for doc_id in ids]
        # get_all returns snapshots in arbitrary order; re-key so the contract is deterministic.
        by_id = {snapshot.id: snapshot for snapshot in self._client.get_all(refs)}
        records = []
        for doc_id in ids:
            snapshot = by_id.get(doc_id)
            if snapshot is not None and getattr(snapshot, "exists", False):
                records.append(_snapshot_to_record(snapshot, f"{collection}/{doc_id}"))
        return records

    def list_ids(self, collection: str) -> List[str]:
        return [snapshot.id for snapshot in self._client.collection(collection).stream()]

    def list_subcollections(self, doc_path: str) -> List[str]:
        return [sub.id for sub in self._client.document(doc_path).collections()]

    def delete_recursive(self, path: str) -> None:
        """Delete the document at ``path`` and every subcollection beneath it.

        Firestore does not cascade; deleting a parent leaves orphaned subcollection data. This
        descends first (via the boundary helper), then removes the parent document itself.
        """
        ref = self._client.document(path)
        for sub in ref.collections():
            delete_collection_recursive(sub, client=self._client)
        ref.delete()

    # --- transactions ---
    def run_transaction(self, fn: Callable[[_FirestoreTransaction], Any], *, attempts: int = 3) -> Any:
        client = self._client

        @transactional
        def _runner(transaction: Any) -> Any:
            return fn(_FirestoreTransaction(transaction, client, self))

        # run_transactional restarts on an expired-transaction 400; @transactional retries contention.
        # A tx.create()/tx.update() precondition failure surfaces here at COMMIT, after the write call
        # returned — map it to the neutral error so callers catch a backend-agnostic type. tx.update on
        # a missing doc raises NotFound at commit (the per-call except in _FirestoreTransaction.update
        # cannot see it), so catch it here too (cubic PR 10887 A5), mirroring the Mongo adapter which
        # raises the neutral NotFound synchronously.
        try:
            return run_transactional(client, _runner, attempts=attempts)
        except (_FirestoreAlreadyExists, _FirestoreConflict) as exc:
            raise AlreadyExists(str(exc)) from exc
        except _FirestoreNotFound as exc:
            raise NotFound(str(exc)) from exc
        except _FirestoreFailedPrecondition as exc:
            # A stale if_updated_at inside a transaction fails the precondition at commit — map to the
            # neutral PreconditionFailed, matching _MongoTransaction.update (cubic PR 10887 #11c).
            raise PreconditionFailed(str(exc)) from exc

    def batch(self) -> _FirestoreBatch:
        return _FirestoreBatch(self._client)


__all__ = ["FirestoreDocumentStore"]
