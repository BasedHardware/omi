"""Qdrant adapter for the vector-store port (ADR-0033) — the self-hostable reference.

Maps the neutral contract onto Qdrant, absorbing the portability traps the study flagged:

- **id shape:** Qdrant point ids must be uint64 or UUID; our ids are arbitrary strings. We store the
  original string under ``payload["__id"]`` and use a deterministic ``uuid5`` as the point id, so
  upsert/query/delete/list round-trip the domain's string ids transparently.
- **namespaces:** one Qdrant collection per namespace (``<prefix><namespace>``), created lazily
  (dim from ``QDRANT_VECTOR_DIM`` = 3072, cosine). Nothing provisions the index today, so the adapter
  owns creation.
- **filters:** the neutral ``$``-DSL is translated to a Qdrant ``Filter`` (``$and``→must, ``$or``→should,
  ``$eq``/bare→match, ``$in``→match-any, ``$gte``/``$lte``→range, ``$exists:false``→is_empty in must,
  ``$exists:true``→is_empty in must_not).
- **list_ids(prefix):** Qdrant has no native id-prefix listing, so we ``scroll`` the collection and
  filter ``__id`` by prefix client-side (O(collection) — the ns_tchunks rollout can optimize via a
  metadata filter).

Env: ``QDRANT_URL`` (e.g. http://qdrant:6333), ``QDRANT_API_KEY`` (optional),
``QDRANT_COLLECTION_PREFIX`` (default ``omi_``), ``QDRANT_VECTOR_DIM`` (default 3072).
"""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any, Dict, Iterator, List, Optional

from utils.vector import filters as neutral_filters
from utils.vector.ports import VectorMatch, VectorRecord

_ID_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "omi-vector-store")
_ID_PAYLOAD_KEY = "__id"
_SCROLL_PAGE = 256

_client_lock = threading.Lock()
_client: Any = None
_ensured: set = set()


def _cfg_prefix() -> str:
    return (os.getenv("QDRANT_COLLECTION_PREFIX") or "omi_").strip()


def _cfg_dim() -> int:
    return int((os.getenv("QDRANT_VECTOR_DIM") or "3072").strip())


def _get_client() -> Any:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from qdrant_client import QdrantClient  # lazy: only the qdrant backend needs this SDK

                url = (os.getenv("QDRANT_URL") or "").strip()
                if not url:
                    raise RuntimeError("QDRANT_URL is not configured")
                _client = QdrantClient(url=url, api_key=(os.getenv("QDRANT_API_KEY") or None))
    return _client


def _collection(namespace: str) -> str:
    return f"{_cfg_prefix()}{namespace}"


def _ensure_collection(namespace: str) -> str:
    name = _collection(namespace)
    if name not in _ensured:
        from qdrant_client import models

        client = _get_client()
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(size=_cfg_dim(), distance=models.Distance.COSINE),
            )
        _ensured.add(name)
    return name


def _point_id(original_id: str) -> str:
    return str(uuid.uuid5(_ID_UUID_NAMESPACE, original_id))


def reset_ensured_cache_for_tests() -> None:
    _ensured.clear()


# --- filter translation ------------------------------------------------------


def _to_qdrant_filter(flt: Optional[Dict[str, Any]]):
    if not flt:
        return None
    neutral_filters.validate(flt)
    from qdrant_client import models

    must: List[Any] = []
    must_not: List[Any] = []

    def add_field(field: str, condition: Any) -> None:
        if not isinstance(condition, dict):
            must.append(models.FieldCondition(key=field, match=models.MatchValue(value=condition)))
            return
        gte = condition.get("$gte")
        lte = condition.get("$lte")
        if gte is not None or lte is not None:
            must.append(models.FieldCondition(key=field, range=models.Range(gte=gte, lte=lte)))
        if "$eq" in condition:
            must.append(models.FieldCondition(key=field, match=models.MatchValue(value=condition["$eq"])))
        if "$in" in condition:
            must.append(models.FieldCondition(key=field, match=models.MatchAny(any=list(condition["$in"]))))
        if "$exists" in condition:
            empty = models.IsEmptyCondition(is_empty=models.PayloadField(key=field))
            (must_not if condition["$exists"] else must).append(empty)

    for key, value in flt.items():
        if key == "$and":
            for sub in value:
                must.append(_to_qdrant_filter(sub))
        elif key == "$or":
            must.append(models.Filter(should=[_to_qdrant_filter(sub) for sub in value]))
        else:
            add_field(key, value)

    return models.Filter(must=must or None, must_not=must_not or None)


# --- adapter -----------------------------------------------------------------


class QdrantVectorStore:
    """VectorStore over Qdrant. ``namespace`` maps to a per-namespace collection."""

    def upsert(self, namespace: str, records: List[VectorRecord]) -> int:
        if not records:
            return 0
        from qdrant_client import models

        collection = _ensure_collection(namespace)
        points = [
            models.PointStruct(
                id=_point_id(r["id"]),
                vector=list(r["values"]),
                payload={**dict(r.get("metadata") or {}), _ID_PAYLOAD_KEY: r["id"]},
            )
            for r in records
        ]
        _get_client().upsert(collection_name=collection, points=points)
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
        collection = _ensure_collection(namespace)
        response = _get_client().query_points(
            collection_name=collection,
            query=list(vector),
            limit=top_k,
            query_filter=_to_qdrant_filter(filter),
            with_payload=True,  # always needed to recover __id
            with_vectors=include_values,
        )
        out: List[VectorMatch] = []
        for point in response.points:
            payload = dict(point.payload or {})
            hit: VectorMatch = {"id": payload.get(_ID_PAYLOAD_KEY), "score": point.score}
            if include_metadata:
                hit["metadata"] = {k: v for k, v in payload.items() if k != _ID_PAYLOAD_KEY}
            if include_values:
                hit["values"] = list(point.vector or [])
            out.append(hit)
        return out

    def update_metadata(self, namespace: str, id: str, set_metadata: Dict[str, Any]) -> None:
        collection = _ensure_collection(namespace)
        _get_client().set_payload(collection_name=collection, payload=dict(set_metadata), points=[_point_id(id)])

    def delete_by_ids(self, namespace: str, ids: List[str]) -> int:
        if not ids:
            return 0
        collection = _ensure_collection(namespace)
        _get_client().delete(collection_name=collection, points_selector=[_point_id(i) for i in ids])
        return len(ids)

    def delete_by_filter(self, namespace: str, filter: Dict[str, Any]) -> None:
        from qdrant_client import models

        collection = _ensure_collection(namespace)
        _get_client().delete(
            collection_name=collection,
            points_selector=models.FilterSelector(filter=_to_qdrant_filter(filter)),
        )

    def list_ids(self, namespace: str, *, prefix: str) -> Iterator[List[str]]:
        collection = _ensure_collection(namespace)
        client = _get_client()
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=collection,
                limit=_SCROLL_PAGE,
                offset=offset,
                with_payload=[_ID_PAYLOAD_KEY],
                with_vectors=False,
            )
            page = [
                (p.payload or {}).get(_ID_PAYLOAD_KEY)
                for p in points
                if str((p.payload or {}).get(_ID_PAYLOAD_KEY, "")).startswith(prefix)
            ]
            if page:
                yield page
            if offset is None:
                break


__all__ = ["QdrantVectorStore"]
