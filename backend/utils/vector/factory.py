"""Vector-store backend selection (ADR-0033). ``VECTOR_STORE_BACKEND`` picks the adapter; default
``pinecone`` (first-class cloud). Adapters are imported lazily so the pinecone default never imports
qdrant-client and vice-versa, and the client is built on first use — not at module import."""

from __future__ import annotations

import logging
import os
import threading
from typing import Dict, Mapping, Optional

from utils.observability.fallback import record_fallback
from utils.vector.ports import VectorStore

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_instance: Optional[VectorStore] = None


# The backends this factory can build. Exported so the availability gate in database/vector_db.py asks
# the factory instead of keeping its own idea: it used to treat anything that was not "qdrant" as
# pinecone, so VECTOR_STORE_BACKEND=weaviate with PINECONE_* set reported "available" and then raised
# ValueError from here — a gate whose 24 callers degrade politely, crashing mid-request instead.
SUPPORTED_BACKENDS = frozenset({'pinecone', 'qdrant'})


def get_vector_store(env: Optional[Mapping[str, str]] = None) -> VectorStore:
    """Return the configured vector store (singleton, resolved on first use).

    ``env`` selects the *backend* from that mapping instead of ``os.environ``, so a caller that
    validated backend-specific dependencies against a specific environment (the vector-repair worker
    entrypoint) selects the same backend it validated. The adapters still read their *connection*
    config (Pinecone key/index, ``QDRANT_URL``/prefix/dim) from ``os.environ``; in production ``env``
    is ``os.environ`` so the two agree. Passing a divergent ``env`` aligns only backend selection, not
    the adapter's client construction."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                source = os.environ if env is None else env
                # ``or "pinecone"`` twice (not just the getenv default) so an empty/whitespace
                # value falls back to the documented Pinecone default too, matching the store and
                # object-store factories (ADR-0032).
                backend = (source.get("VECTOR_STORE_BACKEND") or "pinecone").strip().lower() or "pinecone"
                if backend == "pinecone":
                    from utils.vector.adapters.pinecone import PineconeVectorStore

                    _instance = PineconeVectorStore()
                elif backend == "qdrant":
                    from utils.vector.adapters.qdrant import QdrantVectorStore

                    _instance = QdrantVectorStore()
                else:
                    expected = "', '".join(sorted(SUPPORTED_BACKENDS))
                    raise ValueError(f"unknown VECTOR_STORE_BACKEND: {backend!r} (expected '{expected}')")
    return _instance


def configured_vector_dimension(env: Optional[Mapping[str, str]] = None) -> int:
    """The active vector store's embedding dimension. A metadata-only query still needs an all-zeros
    placeholder vector of the RIGHT length; a hard-coded 3072 makes a store provisioned for another
    dimension reject the query (cubic PR 10887 E1). Pinecone (cloud reference) is 3072; Qdrant reads
    QDRANT_VECTOR_DIM (default 3072), so the cloud path is unchanged."""
    source = os.environ if env is None else env
    backend = (source.get("VECTOR_STORE_BACKEND") or "pinecone").strip().lower() or "pinecone"
    if backend == "qdrant":
        return int((source.get("QDRANT_VECTOR_DIM") or "3072").strip())
    return 3072


def _measure_embedding_dimension() -> int:
    """The dimension the configured embeddings model actually produces, measured once.

    Measured, not derived from ``OMI_EMBEDDINGS_MODEL``: a model name does not carry its dimension, and a
    table mapping names to dimensions would be a second thing to keep in step with reality — which is the
    class of bug this check exists to catch.
    """
    from utils.llm.clients import embeddings

    return len(embeddings.embed_query('dimension probe'))


def _existing_collection_dimensions() -> Dict[str, int]:
    """{collection: dim} for the collections that already exist, which are the real authority.

    The configured value is consulted ONLY when a collection is created (``_ensure_collection``), so an
    existing deployment's collections may have been provisioned under a different value entirely.
    """
    from utils.vector.adapters import qdrant as qdrant_adapter

    client = qdrant_adapter._get_client()
    dimensions: Dict[str, int] = {}
    for collection in client.get_collections().collections:
        params = client.get_collection(collection.name).config.params.vectors
        size = getattr(params, 'size', None)
        if isinstance(size, int):
            dimensions[collection.name] = size
    return dimensions


def validate_vector_dimension(env: Optional[Mapping[str, str]] = None) -> None:
    """Cross the embeddings dimension with the store's, at startup, loudly (BACKLOG L19).

    The two are independent variables that nothing compared: the model's dimension is implicit in
    ``OMI_EMBEDDINGS_MODEL`` and the store's is ``QDRANT_VECTOR_DIM``. Measured on a live stack, the
    problem is less the mismatch than its TIMING — the configured value is read only when a collection is
    created, so a wrong one does nothing at all until some feature touches a new namespace, and then that
    one feature's indexing fails with an error that points nowhere near the cause.

    House style of ``validate_stripe_price_ids`` / ``validate_push_configuration``: log loudly, name the
    consequence, never raise. Unknown is not mismatched — an embeddings endpoint or a store that is not up
    yet is a normal boot ordering, not a misconfiguration, and must not be reported as one.

    Not the same-dimension model swap: vectors of the right length but a different geometry land in the
    same collection and degrade search with no error, and nothing records which model produced a vector.
    That needs somewhere to keep the model name — the open half of L19.
    """
    try:
        source = os.environ if env is None else env
        backend = (source.get("VECTOR_STORE_BACKEND") or "pinecone").strip().lower() or "pinecone"
        if backend != "qdrant":
            # Pinecone's dimension belongs to the index, provisioned outside this codebase.
            return
        if not (source.get("QDRANT_URL") or "").strip():
            return  # no store configured (is_vector_available is False): nothing to reconcile

        try:
            model_dimension = _measure_embedding_dimension()
        except Exception as exc:
            logger.warning(
                'STARTUP: could not measure the embeddings dimension (%s) — skipping the vector-dimension '
                'cross-check. Unknown is not mismatched.',
                exc,
            )
            return

        configured = configured_vector_dimension(env)
        if configured != model_dimension:
            _report_dimension_mismatch(
                f'STARTUP: QDRANT_VECTOR_DIM={configured} but the configured embeddings model produces '
                f'{model_dimension}-dimensional vectors. The value is only read when a COLLECTION IS '
                f'CREATED, so nothing fails until some feature first touches a new namespace — and then '
                f'every write to it is rejected ("Vector dimension error"). Fix the value, or point '
                f'OMI_EMBEDDINGS_MODEL at a model of dimension {configured}.'
            )
            return

        try:
            existing = _existing_collection_dimensions()
        except Exception:
            return  # store not reachable yet: unknown is not mismatched
        wrong = {name: dim for name, dim in existing.items() if dim != model_dimension}
        if wrong:
            _report_dimension_mismatch(
                f'STARTUP: these vector collections were provisioned for a different dimension than the '
                f'configured embeddings model produces ({model_dimension}): '
                + ', '.join(f'{name}={dim}' for name, dim in sorted(wrong.items()))
                + '. Every write to them will be rejected. They were created under an older '
                'QDRANT_VECTOR_DIM or an older model; re-index them or restore the previous model.'
            )
    except BaseException:  # pragma: no cover - a startup check must never stop startup
        pass


def _report_dimension_mismatch(message: str) -> None:
    logger.error(message)
    record_fallback(
        component='vector_store',
        from_mode='dimension_declared',
        to_mode='dimension_mismatch',
        reason='capability_mismatch',
        outcome='degraded',
        log=logger,
    )


def reset_vector_store_for_tests() -> None:
    """Drop the cached singleton so a test can re-select the backend from the environment."""
    global _instance
    with _lock:
        _instance = None


__all__ = ["get_vector_store", "reset_vector_store_for_tests", "validate_vector_dimension"]
