"""Pinecone adapter — the reference implementation of the vector-store port (ADR-0033).

Encapsulates exactly the Pinecone logic that lived inline in ``database/vector_db.py`` (index handle,
upsert/query/update/delete/list), but the client is built lazily on first use instead of at import —
which removes the import-time fragility (empty-key crash) and the module-level ``index`` seam. The
neutral ``$``-DSL filter is Pinecone's native metadata-filter format, so it passes through unchanged.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Iterator, List, Optional

from utils.vector import filters as neutral_filters
from utils.vector.ports import VectorMatch, VectorRecord

_client_lock = threading.Lock()
_index: Any = None


def _get_index() -> Any:
    """Lazy Pinecone index handle. Raises if PINECONE_API_KEY/PINECONE_INDEX_NAME are unset (the
    domain layer keeps its own 'vector store configured?' guard; see database/vector_db.py)."""
    global _index
    if _index is None:
        with _client_lock:
            if _index is None:
                from pinecone import Pinecone  # lazy: only the pinecone backend needs this SDK

                api_key = (os.getenv("PINECONE_API_KEY") or "").strip()
                index_name = (os.getenv("PINECONE_INDEX_NAME") or "").strip()
                if not api_key or not index_name:
                    raise RuntimeError("PINECONE_API_KEY / PINECONE_INDEX_NAME are not configured")
                _index = Pinecone(api_key=api_key).Index(index_name)
    return _index


def _match_field(match: Any, key: str, default: Any = None) -> Any:
    if isinstance(match, dict):
        return match.get(key, default)
    return getattr(match, key, default)


# Pinecone's documented per-request upsert limit, and the same number database/vector_db.py loops at in
# the two writers that got it right ("Pinecone upsert limit is 100 vectors per call").
_UPSERT_BATCH_SIZE = 100


class PineconeVectorStore:
    """VectorStore over a Pinecone serverless index. ``namespace`` maps to a Pinecone namespace."""

    def upsert(self, namespace: str, records: List[VectorRecord]) -> int:
        """Write records, splitting at Pinecone's per-request limit.

        The limit is the vendor's, so it is handled here rather than by each caller: hiding it is what
        this port is for (ADR-0033), and a caller that does not know about it must not lose the tail of
        its batch. It happened — `upsert_action_item_vectors_batch` sent up to 500 vectors in one call
        (its router bounds `items` at 500) while two sibling writers in the same module looped at 100,
        and because that write is deliberately best-effort the rejected request was caught, logged, and
        the vectors were simply gone (BACKLOG L3). The Qdrant adapter has no such cap and gets no
        chunking: this is not a port-level rule, it is one backend's request limit.
        """
        if not records:
            return 0
        index = _get_index()
        written = 0
        for start in range(0, len(records), _UPSERT_BATCH_SIZE):
            chunk = list(records[start : start + _UPSERT_BATCH_SIZE])
            index.upsert(vectors=chunk, namespace=namespace)
            written += len(chunk)
        return written

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
        # Reject an out-of-contract filter before it reaches Pinecone — parity with the Qdrant adapter,
        # which validates in _to_qdrant_filter. Pinecone would accept a wider dialect ($ne/$nin/…), so
        # without this a caller could write a filter that silently works on Pinecone but breaks on Qdrant.
        if filter is not None:
            neutral_filters.validate(filter)
        response = _get_index().query(
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            filter=filter,
            include_metadata=include_metadata,
            include_values=include_values,
        )
        out: List[VectorMatch] = []
        for m in _match_field(response, "matches", []) or []:
            hit: VectorMatch = {"id": _match_field(m, "id"), "score": _match_field(m, "score")}
            if include_metadata:
                hit["metadata"] = dict(_match_field(m, "metadata", {}) or {})
            if include_values:
                hit["values"] = list(_match_field(m, "values", []) or [])
            out.append(hit)
        return out

    def update_metadata(self, namespace: str, id: str, set_metadata: Dict[str, Any]) -> None:
        _get_index().update(id=id, set_metadata=set_metadata, namespace=namespace)

    def delete_by_ids(self, namespace: str, ids: List[str]) -> int:
        if not ids:
            return 0
        _get_index().delete(ids=list(ids), namespace=namespace)
        return len(ids)

    def delete_by_filter(self, namespace: str, filter: Dict[str, Any]) -> None:
        # Same neutral-contract validation as query()/Qdrant: a delete is destructive, so reject an
        # out-of-contract filter here rather than let Pinecone interpret a wider dialect than Qdrant would.
        # Validated unconditionally: the port declares the filter REQUIRED, and the `is not None` guard
        # this replaces let a None slip past validation into `index.delete(filter=None)` — which is not
        # a no-op, it is a delete with no predicate.
        neutral_filters.validate(filter)
        _get_index().delete(filter=filter, namespace=namespace)

    def list_ids(self, namespace: str, *, prefix: str) -> Iterator[List[str]]:
        for page in _get_index().list(prefix=prefix, namespace=namespace):
            yield list(page)


__all__ = ["PineconeVectorStore"]
