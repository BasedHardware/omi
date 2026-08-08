"""In-memory ``VectorStore`` fake for hermetic unit tests of migrated callers (WP4, ADR-0033).

Implements the neutral vector-store port over a dict, with real cosine ranking and a full neutral
``$``-DSL filter interpreter (via ``utils.vector.filters`` — including ``$exists``, which the legacy
e2e fake did not). The adapters have their own live dual-backend contract test (Pinecone ↔ Qdrant);
this fake exists so ``database/vector_db.py`` and callers migrated to the port can be unit-tested
without any backend.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterator, List, Optional, Tuple

from utils.vector import filters as neutral_filters
from utils.vector.ports import VectorMatch, VectorRecord


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class _Vec:
    __slots__ = ("values", "metadata")

    def __init__(self, values: List[float], metadata: Dict[str, Any]):
        self.values = list(values)
        self.metadata = dict(metadata or {})


class FakeVectorStore:
    """In-memory VectorStore keyed by (namespace, id), cosine ranking, neutral-filter interpreter."""

    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str], _Vec] = {}

    def upsert(self, namespace: str, records: List[VectorRecord]) -> int:
        for r in records:
            self._data[(namespace, r["id"])] = _Vec(r["values"], r.get("metadata") or {})
        return len(records)

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
        if filter:
            neutral_filters.validate(filter)  # enforce the contract in tests
        scored: List[Tuple[float, str, _Vec]] = []
        for (ns, vid), vec in self._data.items():
            if ns != namespace:
                continue
            if filter and not neutral_filters.matches(filter, vec.metadata):
                continue
            scored.append((_cosine(vector, vec.values), vid, vec))
        scored.sort(key=lambda t: t[0], reverse=True)
        out: List[VectorMatch] = []
        for score, vid, vec in scored[:top_k]:
            hit: VectorMatch = {"id": vid, "score": score}
            if include_metadata:
                hit["metadata"] = dict(vec.metadata)
            if include_values:
                hit["values"] = list(vec.values)
            out.append(hit)
        return out

    def update_metadata(self, namespace: str, id: str, set_metadata: Dict[str, Any]) -> None:
        vec = self._data.get((namespace, id))
        if vec is not None:
            vec.metadata.update(set_metadata)

    def delete_by_ids(self, namespace: str, ids: List[str]) -> int:
        for i in ids:
            self._data.pop((namespace, i), None)
        return len(ids)

    def delete_by_filter(self, namespace: str, filter: Dict[str, Any]) -> None:
        neutral_filters.validate(filter)
        doomed = [
            key for key, vec in self._data.items() if key[0] == namespace and neutral_filters.matches(filter, vec.metadata)
        ]
        for key in doomed:
            del self._data[key]

    def list_ids(self, namespace: str, *, prefix: str) -> Iterator[List[str]]:
        page = sorted(vid for (ns, vid) in self._data if ns == namespace and vid.startswith(prefix))
        if page:
            yield page


__all__ = ["FakeVectorStore"]
