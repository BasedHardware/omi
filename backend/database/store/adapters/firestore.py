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

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter, transactional

from google.api_core.exceptions import AlreadyExists as _FirestoreAlreadyExists, Conflict as _FirestoreConflict

from ..._client import db as _boundary_db, delete_collection_recursive, run_transactional
from ..errors import AlreadyExists
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


def _revision(snapshot: Any) -> Any:
    """Neutral last-write revision from the Firestore snapshot ``update_time`` (a datetime subclass)."""
    update_time = getattr(snapshot, "update_time", None)
    return update_time if isinstance(update_time, datetime) else None


def _snapshot_to_record(snapshot: Any, path: str) -> StoredDocument:
    if not getattr(snapshot, "exists", False):
        return StoredDocument.missing(path)
    return StoredDocument(
        id=snapshot.id, path=path, exists=True, data=snapshot.to_dict(), updated_at=_revision(snapshot)
    )


def _record_from_query(snapshot: Any) -> StoredDocument:
    reference = getattr(snapshot, "reference", None)
    path = getattr(reference, "path", None) or snapshot.id
    return StoredDocument(
        id=snapshot.id, path=path, exists=True, data=snapshot.to_dict(), updated_at=_revision(snapshot)
    )


class _FirestoreBatch:
    """Neutral batched-write accumulator over a Firestore WriteBatch (atomic per commit)."""

    def __init__(self, client: Any):
        self._client = client
        self._batch = client.batch()

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._batch.set(self._client.document(path), _translate(data), merge=merge)

    def update(self, path: str, data: Dict[str, Any]) -> None:
        self._batch.update(self._client.document(path), _translate(data))

    def delete(self, path: str) -> None:
        self._batch.delete(self._client.document(path))

    def commit(self) -> None:
        self._batch.commit()


class _FirestoreTransaction:
    """Neutral transaction handle over a Firestore transaction. Reads/writes are path-based."""

    def __init__(self, transaction: Any, client: Any):
        self._transaction = transaction
        self._client = client

    def get(self, path: str) -> StoredDocument:
        snapshot = self._client.document(path).get(transaction=self._transaction)
        return _snapshot_to_record(snapshot, path)

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._transaction.set(self._client.document(path), _translate(data), merge=merge)

    def update(self, path: str, data: Dict[str, Any]) -> None:
        self._transaction.update(self._client.document(path), _translate(data))

    def delete(self, path: str) -> None:
        self._transaction.delete(self._client.document(path))


class FirestoreDocumentStore:
    """``DocumentStore`` backed by Google Cloud Firestore."""

    def __init__(self, client: Any = None):
        # Default to the lazy boundary handle so the conftest global patch that swaps ``db`` keeps
        # reaching these ops, matching the WP1 document_store contract.
        self._client = client if client is not None else _boundary_db

    # --- point ops ---
    def get(self, path: str, *, fields: Optional[Sequence[str]] = None) -> StoredDocument:
        ref = self._client.document(path)
        snapshot = ref.get(list(fields)) if fields is not None else ref.get()
        return _snapshot_to_record(snapshot, path)

    def exists(self, path: str) -> bool:
        return bool(getattr(self._client.document(path).get(), "exists", False))

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._client.document(path).set(_translate(data), merge=merge)

    def update(self, path: str, data: Dict[str, Any]) -> None:
        self._client.document(path).update(_translate(data))

    def create(self, path: str, data: Dict[str, Any]) -> None:
        try:
            self._client.document(path).create(_translate(data))
        except (_FirestoreAlreadyExists, _FirestoreConflict) as exc:
            raise AlreadyExists(path) from exc

    def delete(self, path: str) -> None:
        self._client.document(path).delete()

    # --- collection ops ---
    def query(
        self,
        collection: str,
        *,
        filters: Optional[Iterable[Filter]] = None,
        order_by: Optional[str] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> List[StoredDocument]:
        query: Any = self._client.collection(collection)
        for field, op, value in filters or ():
            query = query.where(filter=FieldFilter(field, op, value))
        if order_by is not None:
            query = query.order_by(order_by, direction=_DIRECTION[direction])
        if fields is not None:
            query = query.select(list(fields))
        if limit is not None:
            query = query.limit(limit)
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
            return fn(_FirestoreTransaction(transaction, client))

        # run_transactional restarts on an expired-transaction 400; @transactional retries contention.
        return run_transactional(client, _runner, attempts=attempts)

    def batch(self) -> _FirestoreBatch:
        return _FirestoreBatch(self._client)


__all__ = ["FirestoreDocumentStore"]
