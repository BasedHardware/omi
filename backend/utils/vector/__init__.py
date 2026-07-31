"""Neutral vector-store port (ADR-0033/0004): Pinecone | Qdrant behind one contract."""

from utils.vector.factory import get_vector_store, reset_vector_store_for_tests
from utils.vector.ports import VectorMatch, VectorRecord, VectorStore

__all__ = [
    "VectorRecord",
    "VectorMatch",
    "VectorStore",
    "get_vector_store",
    "reset_vector_store_for_tests",
]
