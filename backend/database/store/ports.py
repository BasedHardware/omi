"""The storage port interface — the backend-neutral contract every implementation satisfies.

Firestore, MongoDB and ArcadeDB adapters implement ``DocumentStore`` identically; the domain
depends only on this Protocol, never on a concrete backend. Addressing is by logical path string
(``"users/{uid}/people/{pid}"``) and payloads are plain ``dict``s — no Firestore paths, filters or
snapshots cross this boundary.

Query filters are neutral ``(field, op, value)`` tuples with ``op`` in {"==", "!=", "in", "not-in",
"<", "<=", ">", ">=", "array_contains", "array_contains_any"}. ``array_contains`` matches documents
whose array-valued ``field`` contains ``value``; ``array_contains_any`` matches when the array shares
any element with a ``value`` list; ``not-in`` matches when ``field`` is none of a ``value`` list.
Field transforms use the neutral sentinels in ``database.store.sentinels``.

``query`` scopes to one containing collection (a single parent); ``query_group`` scopes to every
collection sharing a leaf name across all parents (a Firestore collection-group query), returning
records whose ``path`` is the full logical path so callers can recover the parent (e.g. the uid).
``query_group``'s ``start_after`` is a document-name keyset (a full logical path): results are
ordered by document name ascending and resume strictly after that path — the portable form of a
Firestore collection-group cursor, for bounded resumable cross-parent sweeps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from .records import StoredDocument

# (field, op, value) — op is a neutral comparison operator, not a Firestore FieldFilter.
Filter = Tuple[str, str, Any]

# order_by is either a single field name (sorted per ``direction``) or, for multi-field ordering, a
# sequence of (field, direction) pairs applied most-significant first. Keyset (``start_after``) is
# single-field only.
OrderBy = Any  # Union[str, Sequence[Tuple[str, str]]] — kept loose to avoid over-constraining callers.


@runtime_checkable
class Transaction(Protocol):
    """A neutral transaction handle. Reads/writes are path-based, like the store itself."""

    def get(self, path: str) -> StoredDocument: ...
    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None: ...
    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Optional[datetime] = None) -> None: ...
    def create(self, path: str, data: Dict[str, Any]) -> None: ...
    def delete(self, path: str, *, if_updated_at: Optional[datetime] = None) -> None: ...


@runtime_checkable
class WriteBatch(Protocol):
    """A neutral batched-write accumulator: queue path-based writes, then ``commit`` them.

    For bulk throughput (the domain already chunks large writes). Firestore commits each batch
    atomically; the Mongo adapter groups by collection and bulk-writes. Not a cross-backend
    atomicity guarantee — use ``run_transaction`` when read-modify-write atomicity is required.
    """

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None: ...
    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Optional[datetime] = None) -> None: ...
    def delete(self, path: str, *, if_updated_at: Optional[datetime] = None) -> None: ...
    def commit(self) -> None: ...


@runtime_checkable
class DocumentStore(Protocol):
    """Backend-neutral document store. Implemented per backend (Firestore | Mongo | ArcadeDB)."""

    # --- point ops ---
    def get(self, path: str, *, fields: Optional[Sequence[str]] = None) -> StoredDocument: ...
    def exists(self, path: str) -> bool: ...
    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None: ...
    # ``if_updated_at`` is an optimistic-concurrency precondition: apply the write only if the stored
    # document's revision (its ``StoredDocument.updated_at``) still equals the passed value; otherwise
    # raise ``errors.PreconditionFailed``. It is the neutral form of a Firestore ``LastUpdateOption``.
    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Optional[datetime] = None) -> None: ...  # dotted keys + neutral sentinels
    def create(self, path: str, data: Dict[str, Any]) -> None: ...  # raises errors.AlreadyExists on conflict
    def delete(self, path: str, *, if_updated_at: Optional[datetime] = None) -> None: ...

    # --- collection ops ---
    def query(
        self,
        collection: str,
        *,
        filters: Optional[Iterable[Filter]] = None,
        order_by: Optional[OrderBy] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        fields: Optional[Sequence[str]] = None,
        # start_after is a single-field keyset cursor: {"value": <order-field value>, "id": <document
        # id>} — ``value`` bounds the ``order_by`` field, ``id`` is the document-id tiebreak. Combining
        # a multi-field ``order_by`` with ``start_after`` is unsupported (see the module note).
        start_after: Optional[Dict[str, Any]] = None,
    ) -> List[StoredDocument]: ...
    def count(self, collection: str, *, filters: Optional[Iterable[Filter]] = None) -> int: ...
    def query_group(
        self,
        group: str,
        *,
        filters: Optional[Iterable[Filter]] = None,
        order_by: Optional[OrderBy] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        start_after: Optional[str] = None,
    ) -> List[StoredDocument]: ...  # cross-parent collection-group query; results carry full paths
    def get_many(self, collection: str, ids: Sequence[str]) -> List[StoredDocument]: ...
    def list_ids(self, collection: str) -> List[str]: ...
    def list_subcollections(self, doc_path: str) -> List[str]: ...  # immediate child collection names
    def delete_recursive(self, path: str) -> None: ...

    # --- transactions & batches ---
    def run_transaction(self, fn: Callable[[Transaction], Any], *, attempts: int = 3) -> Any: ...
    def batch(self) -> WriteBatch: ...


__all__ = ["DocumentStore", "Transaction", "WriteBatch", "Filter"]
