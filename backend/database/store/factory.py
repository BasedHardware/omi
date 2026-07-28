"""Backend selection for the storage port — the ``STORAGE_BACKEND`` seam (ADR-0004).

``get_document_store()`` returns the process-wide ``DocumentStore`` chosen by configuration.
Firestore is the default (ADR-0003, first-class); ``mongo`` selects the MongoDB adapter. Adapters
are imported lazily so a Firestore deployment never needs ``pymongo`` installed, and vice versa.

    STORAGE_BACKEND=firestore   # default
    STORAGE_BACKEND=mongo       # + MONGO_URI, MONGO_DB
"""

from __future__ import annotations

import os
from threading import Lock
from typing import Optional

from .ports import DocumentStore

_store: Optional[DocumentStore] = None
_store_lock = Lock()


def _build_store() -> DocumentStore:
    backend = (os.environ.get("STORAGE_BACKEND") or "firestore").strip().lower()
    if backend == "firestore":
        from .adapters.firestore import FirestoreDocumentStore

        return FirestoreDocumentStore()
    if backend == "mongo":
        from .adapters.mongo import MongoDocumentStore

        return MongoDocumentStore(
            uri=os.environ.get("MONGO_URI"),
            db_name=os.environ.get("MONGO_DB", "omi"),
        )
    raise ValueError(f"Unknown STORAGE_BACKEND={backend!r} (expected 'firestore' or 'mongo')")


def get_document_store() -> DocumentStore:
    """Return the configured document store (singleton, resolved on first use)."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = _build_store()
    return _store


def reset_document_store() -> None:
    """Drop the cached store so the next call re-reads configuration. For tests only."""
    global _store
    with _store_lock:
        _store = None


__all__ = ["get_document_store", "reset_document_store"]
