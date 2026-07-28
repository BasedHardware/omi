"""The storage port interface — the backend-neutral contract every implementation satisfies.

Firestore, MongoDB and ArcadeDB adapters implement ``DocumentStore`` identically; the domain
depends only on this Protocol, never on a concrete backend. Addressing is by logical path string
(``"users/{uid}/people/{pid}"``) and payloads are plain ``dict``s — no Firestore paths, filters or
snapshots cross this boundary.

Query filters are neutral ``(field, op, value)`` tuples with ``op`` in {"==", "in", "<", "<=",
">", ">="}. Field transforms use the neutral sentinels in ``database.store.sentinels``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from .records import StoredDocument

# (field, op, value) — op is a neutral comparison operator, not a Firestore FieldFilter.
Filter = Tuple[str, str, Any]


@runtime_checkable
class Transaction(Protocol):
    """A neutral transaction handle. Reads/writes are path-based, like the store itself."""

    def get(self, path: str) -> StoredDocument: ...
    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None: ...
    def update(self, path: str, data: Dict[str, Any]) -> None: ...
    def delete(self, path: str) -> None: ...


@runtime_checkable
class DocumentStore(Protocol):
    """Backend-neutral document store. Implemented per backend (Firestore | Mongo | ArcadeDB)."""

    # --- point ops ---
    def get(self, path: str, *, fields: Optional[Sequence[str]] = None) -> StoredDocument: ...
    def exists(self, path: str) -> bool: ...
    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None: ...
    def update(self, path: str, data: Dict[str, Any]) -> None: ...  # dotted keys + neutral sentinels
    def delete(self, path: str) -> None: ...

    # --- collection ops ---
    def query(
        self,
        collection: str,
        *,
        filters: Optional[Iterable[Filter]] = None,
        order_by: Optional[str] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
    ) -> List[StoredDocument]: ...
    def get_many(self, collection: str, ids: Sequence[str]) -> List[StoredDocument]: ...
    def list_ids(self, collection: str) -> List[str]: ...
    def delete_recursive(self, path: str) -> None: ...

    # --- transactions ---
    def run_transaction(self, fn: Callable[[Transaction], Any], *, attempts: int = 3) -> Any: ...


__all__ = ["DocumentStore", "Transaction", "Filter"]
