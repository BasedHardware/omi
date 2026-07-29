"""Document-store shim over the neutral storage port (ADR-0022).

A thin, path-based wrapper over ``database.store.get_document_store()`` used by the memory service
layer (``utils/memory/*`` and ``jobs/short_term_lifecycle_worker.py``). Reads return a neutral
``StoredDocument`` (``.exists`` / ``.to_dict()`` / ``.id``); writes and transactions go through the
port. No Firestore SDK, no injected client — the backend is selected by ``STORAGE_BACKEND``.

ROLE IN THE ROADMAP: WP1 introduced this as the single Firestore-touching primitive for the memory
subsystem; WP2 (ADR-0022) absorbs it into the neutral port so the same callers run on Firestore or
Mongo unchanged. Transactions use the port's ``run_transaction(fn)``: ``fn`` receives a neutral
transaction handle (``get/set/update/delete`` by path string).
"""

from typing import Any, Callable, List, Optional

from database.store import get_document_store
from database.store.records import StoredDocument


def _store() -> Any:
    return get_document_store()


# --- single-document ops --------------------------------------------------------------

def get_document(path: str) -> StoredDocument:
    """Return the neutral document record at ``path`` (``.exists`` False when absent)."""
    return _store().get(path)


def document_exists(path: str) -> bool:
    return _store().exists(path)


def set_document(path: str, data: dict, *, merge: bool = False) -> None:
    _store().set(path, data, merge=merge)


def update_document(path: str, data: dict) -> None:
    _store().update(path, data)


def delete_document(path: str) -> None:
    _store().delete(path)


# --- collection reads -----------------------------------------------------------------

def stream_collection(path: str) -> List[StoredDocument]:
    """Return every document record under the collection at ``path``."""
    return _store().query(path)


def stream_collection_where(
    path: str,
    field: str,
    op: str,
    value: Any,
    *,
    limit: Optional[int] = None,
) -> List[StoredDocument]:
    return _store().query(path, filters=[(field, op, value)], limit=limit)


# --- transactions ---------------------------------------------------------------------

def run_transaction(fn: Callable[[Any], Any]) -> Any:
    """Run ``fn(tx)`` inside a port transaction.

    ``tx`` is a neutral transaction handle: ``tx.get(path)`` returns a ``StoredDocument`` and
    ``tx.set(path, data, merge=)`` / ``tx.update(path, data)`` / ``tx.delete(path)`` stage writes.
    The port's runner owns contention retry (Firestore | Mongo).
    """
    return _store().run_transaction(fn)
