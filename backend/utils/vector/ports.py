"""Neutral vector-store port (ADR-0033/0004).

The domain speaks (logical namespace, string id, float vector, neutral metadata dict) and a neutral
``$``-DSL filter (see ``filters.py``) — never a Pinecone ``Index`` or a Qdrant client. Adapters map the
contract onto Pinecone (reference) or Qdrant (self-hostable). Selected by ``VECTOR_STORE_BACKEND`` via
``factory.get_vector_store()``. Embeddings live OUTSIDE the port: callers embed and pass vectors.

Chunking (per-namespace batch limits) stays in the domain layer (``database/vector_db.py``), not here.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Protocol, TypedDict, runtime_checkable


class VectorRecord(TypedDict):
    """One vector to upsert: id + values + metadata."""

    id: str
    values: List[float]
    metadata: Dict[str, Any]


class _VectorMatchIdentity(TypedDict):
    """What every hit carries, on every backend."""

    id: str
    score: float


class VectorMatch(_VectorMatchIdentity, total=False):
    """One query hit.

    ``id`` and ``score`` are REQUIRED: both adapters set them unconditionally when they build a hit
    (pinecone.py:99, qdrant.py:191) — a match without an identity or a rank is not a match. Declaring
    the whole shape `total=False` said the opposite, so every `hit["id"]` and `hit["score"]` in
    `database/vector_db.py` read as an access to a possibly-absent key. ``values`` and ``metadata``
    genuinely are optional: they appear only when the caller asked for them via
    ``include_values`` / ``include_metadata``, and readers must keep using ``.get()`` for those."""

    values: List[float]
    metadata: Dict[str, Any]


@runtime_checkable
class VectorStore(Protocol):
    """The neutral vector-store contract. ``namespace`` is a logical name (each adapter maps it to a
    configured index/collection); ``id`` is the vector id within it."""

    def upsert(self, namespace: str, records: List[VectorRecord]) -> int:
        """Upsert records; return the number written."""
        ...

    def query(
        self,
        namespace: str,
        vector: List[float],
        *,
        top_k: int,
        filter: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True,
        include_values: bool = False,
    ) -> List[VectorMatch]:
        """Nearest-neighbor search, optionally constrained by a neutral ``$``-DSL filter."""
        ...

    def update_metadata(self, namespace: str, id: str, set_metadata: Dict[str, Any]) -> None:
        """Merge ``set_metadata`` into an existing vector's metadata."""
        ...

    def delete_by_ids(self, namespace: str, ids: List[str]) -> int:
        """Delete by explicit ids; return the number requested (idempotent)."""
        ...

    def delete_by_filter(self, namespace: str, filter: Dict[str, Any]) -> None:
        """Delete every vector in the namespace whose metadata matches the neutral filter."""
        ...

    def list_ids(self, namespace: str, *, prefix: str) -> Iterator[List[str]]:
        """Yield pages of ids whose id starts with ``prefix`` (for prefix-scoped deletes)."""
        ...


__all__ = ["VectorRecord", "VectorMatch", "VectorStore"]
