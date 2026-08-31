"""Backend-neutral storage port (WP2, ADR-0002/0004).

`database/store` is THE storage abstraction — the "store" the domain talks to. Firestore,
MongoDB and (future) ArcadeDB are interchangeable *implementations* (adapters) behind it; none is
privileged in the domain. Selection is by configuration (`STORAGE_BACKEND`).

Public surface:
  - StoredDocument     : neutral read result ({exists, id, path, data}) — never a Firestore snapshot
  - DocumentStore      : the port interface (typing.Protocol)
  - sentinels          : neutral field transforms (DELETE / ArrayUnion / ArrayRemove / Increment /
                         SERVER_TIMESTAMP), each adapter maps to its own primitive
"""

from .records import StoredDocument
from .ports import DocumentStore, Transaction, WriteBatch, Filter
from .factory import get_document_store, reset_document_store
from .keys import ensure_id_segment
from . import errors, sentinels

__all__ = [
    "StoredDocument",
    "DocumentStore",
    "Transaction",
    "WriteBatch",
    "Filter",
    "get_document_store",
    "reset_document_store",
    "ensure_id_segment",
    "errors",
    "sentinels",
]
