"""Document-store port — a backend-neutral, path-based persistence primitive.

This is the seam that lets code outside ``database/`` (today: the memory subsystem) read and
write documents WITHOUT importing the Firestore SDK or the client. Callers speak only in
document/collection *path strings* and a ``db_client`` (a real client, a test fake, or ``None``);
they never hold the client or run a raw ``.document()/.collection()`` op themselves.

Contract (deliberately backend-agnostic so WP2 can put adapters under it):
  * ``db_client=None`` resolves to the injected boundary client ``db`` — so the conftest global
    patch that swaps ``db`` keeps reaching these ops through the port.
  * Reads return a **document handle** exposing ``.exists`` and ``.to_dict()``. Today this is a
    Firestore ``DocumentSnapshot``; a Mongo/ArcadeDB adapter (WP2) returns an equivalent handle.
  * Callers must NOT reach into a returned handle's ``.reference`` — use the write verbs.

ROLE IN THE ROADMAP: this is the WP1 seal — the single Firestore-touching primitive for the
memory subsystem. In WP2 (ADR-0002) it grows real backend adapters (Firestore | Mongo | ArcadeDB)
underneath and/or the domain repositories sit on top of it. It is an evolving port, not a
throwaway: the Firestore-specific implementation here becomes the "firestore adapter" of the port.

Transaction helpers are added here (mirroring the SDK ``@firestore.transactional`` pattern) when
the first transaction-heavy caller is migrated.
"""

from typing import Any, Iterable, Optional

from ._client import db


def _resolve(db_client: Any) -> Any:
    return db_client if db_client is not None else db


# --- single-document ops --------------------------------------------------------------

def get_document(db_client: Any, path: str, *, timeout: Optional[float] = None) -> Any:
    """Return the document handle at ``path`` (optionally with a read timeout).

    ``timeout`` guards latency-sensitive reads (e.g. rollout gates). Backends that do not accept
    a ``timeout`` kwarg (some test fakes) fall back to an untimed read.
    """
    ref = _resolve(db_client).document(path)
    if timeout is None:
        return ref.get()
    try:
        return ref.get(timeout=timeout)
    except TypeError as exc:
        if 'timeout' not in str(exc):
            raise
        return ref.get()


def document_exists(db_client: Any, path: str) -> bool:
    return bool(getattr(_resolve(db_client).document(path).get(), "exists", False))


def set_document(db_client: Any, path: str, data: dict, *, merge: bool = False) -> None:
    _resolve(db_client).document(path).set(data, merge=merge)


def update_document(db_client: Any, path: str, data: dict) -> None:
    _resolve(db_client).document(path).update(data)


def delete_document(db_client: Any, path: str) -> None:
    _resolve(db_client).document(path).delete()


# --- collection reads -----------------------------------------------------------------

def stream_collection(db_client: Any, path: str) -> Iterable[Any]:
    """Stream every DocumentSnapshot under the collection at ``path``."""
    return _resolve(db_client).collection(path).stream()


def stream_collection_where(
    db_client: Any,
    path: str,
    field: str,
    op: str,
    value: Any,
    *,
    limit: Optional[int] = None,
) -> Iterable[Any]:
    query: Any = _resolve(db_client).collection(path).where(field, op, value)
    if limit is not None:
        query = query.limit(limit)
    return query.stream()


# --- transactions ---------------------------------------------------------------------
# The ``@transactional`` decorator that wraps the transaction body stays with the caller
# (imported from database.memory_apply_store, itself inside the boundary). These helpers keep
# transaction creation and per-document ops off the raw client: the body receives the
# write-transaction handle and uses tx_get/tx_set with path strings only.

def new_transaction(db_client: Any) -> Any:
    """Create a transaction bound to the resolved client."""
    return _resolve(db_client).transaction()


def tx_get(transaction: Any, db_client: Any, path: str) -> Any:
    """Read a document handle inside a transaction."""
    return _resolve(db_client).document(path).get(transaction=transaction)


def tx_set(transaction: Any, db_client: Any, path: str, data: dict) -> None:
    transaction.set(_resolve(db_client).document(path), data)


def tx_update(transaction: Any, db_client: Any, path: str, data: dict) -> None:
    transaction.update(_resolve(db_client).document(path), data)


def tx_delete(transaction: Any, db_client: Any, path: str) -> None:
    transaction.delete(_resolve(db_client).document(path))
