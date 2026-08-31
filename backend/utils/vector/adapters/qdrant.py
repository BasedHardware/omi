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

import logging

import os
import threading
import uuid
from typing import Any, Dict, Iterator, List, Optional

from utils.vector import filters as neutral_filters
from utils.vector.ports import VectorMatch, VectorRecord

logger = logging.getLogger(__name__)

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


def collection_dimensions() -> Dict[str, int]:
    """``{collection: dim}`` for the collections that exist on the server right now.

    Lives here, beside the client it needs, because it is entirely Qdrant: ``get_collections()`` and
    ``config.params.vectors`` are this SDK's shapes. ``utils/vector/factory`` used to walk them itself,
    which meant pulling ``_get_client()`` out of this module — a caller reaching past the port for the
    vendor client is the one thing the vector abstraction exists to prevent (ADR-0033).
    """
    client = _get_client()
    dimensions: Dict[str, int] = {}
    for collection in client.get_collections().collections:
        params = client.get_collection(collection.name).config.params.vectors
        size = getattr(params, 'size', None)
        if isinstance(size, int):
            dimensions[collection.name] = size
    return dimensions


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
            # Creation is the one moment when the model that owns this namespace is known for certain:
            # nothing has been written yet. Recorded here so the boot check can later catch a swap to a
            # different model of the SAME dimension, which leaves no other trace (ADR-0086).
            _record_creating_model(name)
        _ensured.add(name)
    return name


def _record_creating_model(collection: str) -> None:
    """Remember which embeddings model this collection was created for. Never raises: a bookkeeping
    failure must not break the write that triggered the creation."""
    try:
        from utils.llm.clients import embeddings_model
        from utils.vector.namespace_state import record_namespace_state

        record_namespace_state(collection, model=embeddings_model(), dim=_cfg_dim())
    except Exception:  # pragma: no cover - defensive, see docstring
        pass


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
            # Built by narrowing rather than checked afterwards: an empty sub-filter translates to
            # None, and `should=[None]` is not "match anything" to Qdrant — it is a malformed query.
            # Reject it here, where the cause is still visible, instead of letting the client fail on
            # a shape it cannot name.
            branches = []
            for sub in value:
                branch = _to_qdrant_filter(sub)
                if branch is None:
                    raise neutral_filters.UnsupportedFilterError("$or contains an empty sub-filter")
                branches.append(branch)
            must.append(models.Filter(should=branches))
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
            original_id = payload.get(_ID_PAYLOAD_KEY)
            if not isinstance(original_id, str):
                # Every point WE write carries the caller's id under __id, because the point id itself
                # is a uuid5 we derive and cannot invert. A point without it was not written through
                # this adapter, and its qdrant id would be meaningless to the caller — returning it
                # would send a lookup somewhere that does not exist. Drop it, and say so once.
                logger.warning(
                    "qdrant: point %s in %s has no %s payload key; dropping it from the results",
                    point.id,
                    namespace,
                    _ID_PAYLOAD_KEY,
                )
                continue
            hit: VectorMatch = {"id": original_id, "score": point.score}
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

        selector = _to_qdrant_filter(filter)
        if selector is None:
            # A delete whose predicate translated to nothing is not a no-op: `FilterSelector(filter=None)`
            # selects the whole collection. The port declares the filter required, so an empty one is a
            # caller error, and this is the last place that can still say so. Same hole as the one the
            # pinecone adapter carried in `delete_by_filter`.
            raise neutral_filters.UnsupportedFilterError("delete_by_filter needs a non-empty filter")
        collection = _ensure_collection(namespace)
        _get_client().delete(collection_name=collection, points_selector=models.FilterSelector(filter=selector))

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
            # Read once, and test the value that is actually yielded. The predicate used to stringify
            # a MISSING key into "" while the value beside it was taken raw, so the two disagreed: with
            # an empty prefix — or a non-string ``__id`` — a point carrying no id passed the test and
            # entered a ``List[str]`` as None, to be handed to ``delete_by_ids`` later. Not reachable
            # from today's two callers (both pass ``f"{uid}-{conversation_id}-c"``), which is why this
            # is a latent hole and not an outage; it is one empty-prefix caller from being live.
            page: List[str] = []
            for point in points:
                stored = (point.payload or {}).get(_ID_PAYLOAD_KEY)
                if isinstance(stored, str) and stored.startswith(prefix):
                    page.append(stored)
            if page:
                yield page
            if offset is None:
                break


__all__ = ["QdrantVectorStore"]
