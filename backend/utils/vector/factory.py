"""Vector-store backend selection (ADR-0033). ``VECTOR_STORE_BACKEND`` picks the adapter; default
``pinecone`` (first-class cloud). Adapters are imported lazily so the pinecone default never imports
qdrant-client and vice-versa, and the client is built on first use — not at module import."""

from __future__ import annotations

import os
import threading
from typing import Optional

from utils.vector.ports import VectorStore

_lock = threading.Lock()
_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                backend = (os.getenv("VECTOR_STORE_BACKEND") or "pinecone").strip().lower()
                if backend == "pinecone":
                    from utils.vector.adapters.pinecone import PineconeVectorStore

                    _instance = PineconeVectorStore()
                elif backend == "qdrant":
                    from utils.vector.adapters.qdrant import QdrantVectorStore

                    _instance = QdrantVectorStore()
                else:
                    raise ValueError(f"unknown VECTOR_STORE_BACKEND: {backend!r} (expected 'pinecone' or 'qdrant')")
    return _instance


def reset_vector_store_for_tests() -> None:
    """Drop the cached singleton so a test can re-select the backend from the environment."""
    global _instance
    with _lock:
        _instance = None


__all__ = ["get_vector_store", "reset_vector_store_for_tests"]
