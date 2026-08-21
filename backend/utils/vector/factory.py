"""Vector-store backend selection (ADR-0033). ``VECTOR_STORE_BACKEND`` picks the adapter; default
``pinecone`` (first-class cloud). Adapters are imported lazily so the pinecone default never imports
qdrant-client and vice-versa, and the client is built on first use — not at module import."""

from __future__ import annotations

import os
import threading
from typing import Mapping, Optional

from utils.vector.ports import VectorStore

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


def reset_vector_store_for_tests() -> None:
    """Drop the cached singleton so a test can re-select the backend from the environment."""
    global _instance
    with _lock:
        _instance = None


__all__ = ["get_vector_store", "reset_vector_store_for_tests"]
