"""Path-based Firestore verb layer — the persistence boundary for injected-client callers.

The memory subsystem threads a ``db_client`` (a real client, a test fake, or ``None``) but must
not hold the client or run raw Firestore ops itself. These verbs are the only place those raw
ops live: callers pass ``db_client`` and a document/collection *path string*; when ``db_client``
is ``None`` the injected boundary client (``db``) is used, so the same conftest global patch that
swaps ``db`` continues to reach these ops.

Raw ``DocumentSnapshot`` objects are returned by reads: ``.exists`` / ``.to_dict()`` /
``.get(field)`` need no SDK import and are not client/reference ops. Do not call
``snapshot.reference.set(...)`` outside ``database/`` — use the write verbs instead.

Transaction helpers are added here (mirroring the SDK ``@firestore.transactional`` pattern) when
the first transaction-heavy caller is migrated.
"""

from typing import Any, Iterable, Optional

from ._client import db


def _resolve(db_client: Any) -> Any:
    return db_client if db_client is not None else db


# --- single-document ops --------------------------------------------------------------

def get_document(db_client: Any, path: str) -> Any:
    """Return the DocumentSnapshot at ``path``."""
    return _resolve(db_client).document(path).get()


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
