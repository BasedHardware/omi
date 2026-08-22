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
        start_after: Optional[Dict[str, Any]] = None,
    ) -> List[StoredDocument]:
        """``DocumentStore.query`` executed inside this transaction (BACKLOG L24).

        Upstream reads collections inside ``@firestore.transactional`` bodies — the idempotency-key
        de-dup in ``database/action_items.py``, the relationship detach in ``goals.py``, the photo probe
        in ``conversation_finalization_jobs.py`` — and the facade used to accept that transaction and
        drop it, so on Mongo those reads ran outside the session.

        What the two backends promise here is NOT the same, and the difference is measured rather than
        assumed (ADR-0070): Firestore takes a LOCK on what a transaction reads (a competing writer gets
        409) and refuses read-after-write outright; Mongo gives a consistent snapshot, allows
        read-after-write, and takes no read lock — so a concurrent write to a row this query returned
        does not stop the commit. The contract is therefore only "the read runs in the transaction's own
        view of committed state". A caller that needs read-set conflict detection must not rely on this.
        """


@runtime_checkable
class WriteBatch(Protocol):
    """A neutral batched-write accumulator: queue path-based writes, then ``commit`` them.

    For bulk throughput (the domain already chunks large writes). Firestore commits each batch
    atomically; the Mongo adapter groups by collection and bulk-writes. Not a cross-backend
    atomicity guarantee — use ``run_transaction`` when read-modify-write atomicity is required.
    """

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None: ...
    def create(self, path: str, data: Dict[str, Any]) -> None: ...
    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Optional[datetime] = None) -> None: ...
    def delete(self, path: str, *, if_updated_at: Optional[datetime] = None) -> None: ...
    def commit(self) -> None: ...


@runtime_checkable
class DocumentStore(Protocol):
    """Backend-neutral document store. Implemented per backend (Firestore | Mongo | ArcadeDB)."""

    # --- point ops ---
    # ``timeout`` (seconds) bounds the read so a slow backend fails instead of holding a request
    # worker: the Firestore adapter passes it to the RPC, the Mongo adapter maps it to ``maxTimeMS``.
    # ``None`` means no deadline. The in-memory fake ignores it (a local dict read cannot block).
    def get(
        self, path: str, *, fields: Optional[Sequence[str]] = None, timeout: Optional[float] = None
    ) -> StoredDocument: ...
    def exists(self, path: str) -> bool: ...
    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None: ...

    # ``if_updated_at`` is an optimistic-concurrency precondition: apply the write only if the stored
    # document's revision (its ``StoredDocument.updated_at``) still equals the passed value; otherwise
    # raise ``errors.PreconditionFailed``. It is the neutral form of a Firestore ``LastUpdateOption``.
    def update(
        self, path: str, data: Dict[str, Any], *, if_updated_at: Optional[datetime] = None
    ) -> None: ...  # dotted keys + neutral sentinels
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
        # Two cursor forms, and they are not interchangeable:
        #   str  — the document-path keyset, for the implicit document-name order (no order_by)
        #   dict — {"value": <order-field value>, "id": <full path>}, a FIELD keyset that positions an
        #          explicit order_by. Needed because a range filter forces the ordering onto the
        #          filtered field, so a name cursor cannot resume it (BACKLOG L39): "everything changed
        #          since X, in change order, resumable" is only expressible with this form.
        # Each adapter refuses the mismatched pairing rather than building an invalid cursor.
        start_after: Optional[Any] = None,
    ) -> List[StoredDocument]: ...  # cross-parent collection-group query; results carry full paths
    def get_many(self, collection: str, ids: Sequence[str]) -> List[StoredDocument]: ...
    def list_ids(self, collection: str) -> List[str]: ...
    def list_subcollections(self, doc_path: str) -> List[str]: ...  # immediate child collection names
    def delete_recursive(self, path: str) -> None: ...

    # --- transactions & batches ---
    def run_transaction(self, fn: Callable[[Transaction], Any], *, attempts: int = 3) -> Any: ...
    def batch(self) -> WriteBatch: ...


@runtime_checkable
class FacadeSessionStore(Protocol):
    """The extra surface a store MUST implement to sit behind the ADR-0044 facade.

    ``NeutralFirestoreClient`` is not a domain caller: it impersonates a Firestore ``Client`` so
    upstream code that threads ``db_client`` runs unchanged. Upstream's ``@transactional`` bodies
    interleave reads and writes on one handle, so the facade needs to run each op **inside a specific
    session** — something the domain-facing ``DocumentStore`` above deliberately does not express
    (``run_transaction`` takes a callback and owns the session itself).

    This protocol is that requirement, written down. It used to be an unwritten convention: the facade
    reached for ``store._get(..., session=...)`` and friends, which exist on ``MongoDocumentStore`` and
    the in-memory test fake and nowhere else. An adapter author implementing the documented port in
    full got ``AttributeError`` deep inside a transaction — and, worse, a ``_begin`` that silently fell
    back to no session at all, so every transaction in the product would have run **without
    atomicity, without an error**. Fixing the loud half while shipping the silent half was the real
    hazard (BACKLOG L31).

    The names keep their leading underscore on purpose: they are a facade-internal extension, not part
    of the neutral surface domain modules are allowed to call. ``session`` is opaque to the facade's
    callers but not yet neutral — ``_FacadeTransaction`` drives it with the **Mongo session protocol**
    (``commit_transaction`` / ``abort_transaction`` / ``end_session``). Making that neutral too is the
    open half of L31, to be done together with a third adapter and not before.
    """

    # Same semantics as the DocumentStore ops of the same name, executed inside ``session``.
    def _get(self, path: str, *, fields: Optional[Sequence[str]] = None, session: Any = None) -> StoredDocument: ...
    def _set(self, path: str, data: Dict[str, Any], *, merge: bool = False, session: Any = None) -> None: ...
    def _update(
        self, path: str, data: Dict[str, Any], *, if_updated_at: Optional[datetime] = None, session: Any = None
    ) -> None: ...
    def _create(self, path: str, data: Dict[str, Any], *, session: Any = None) -> None: ...
    def _delete(self, path: str, *, if_updated_at: Optional[datetime] = None, session: Any = None) -> None: ...

    def _query(self, collection: str, *, session: Any = None, **kwargs: Any) -> List[StoredDocument]:
        """``query`` inside ``session``. Upstream's transactional bodies read COLLECTIONS, not just
        documents (``query.stream(transaction=tx)``), and the facade used to accept that transaction and
        drop it — so on Mongo the de-dup read in ``database/action_items.py`` ran outside the session
        (BACKLOG L24)."""

    def _begin_session(self) -> Any:
        """Open a session with an active transaction, or return ``None`` to declare session-less.

        ``None`` is a **declaration**, not an absence: "this store applies writes directly and offers
        no atomicity" — what the in-memory unit-test fake wants, since a unit test asserts domain
        logic and the live contract suite owns atomicity. A real adapter must return a session; if it
        cannot, it must say so here rather than let the facade infer it from a missing attribute.
        """


# Every name the facade needs beyond DocumentStore, in one place so the error message can list what
# is missing instead of surfacing whichever attribute happened to be touched first.
FACADE_SESSION_OPS = ("_get", "_set", "_update", "_create", "_delete", "_query", "_begin_session")


def missing_facade_session_ops(store: Any) -> tuple[str, ...]:
    """The FACADE_SESSION_OPS ``store`` does not implement (empty tuple = usable behind the facade)."""
    return tuple(name for name in FACADE_SESSION_OPS if not callable(getattr(store, name, None)))


__all__ = [
    "DocumentStore",
    "FacadeSessionStore",
    "FACADE_SESSION_OPS",
    "Filter",
    "Transaction",
    "WriteBatch",
    "missing_facade_session_ops",
]
