"""Backward-compatible shim — implementation lives in ``database.memory_vector_repair_pinecone_adapter`` (WS-G7)."""

from database.memory_vector_repair_pinecone_adapter import (
    V17VectorRepairNotReady,
    V17_VECTOR_REPAIR_PINECONE_NAMESPACE,
    make_v17_pinecone_vector_deleter,
    make_v17_pinecone_vector_repairer,
)

__all__ = [
    "V17VectorRepairNotReady",
    "V17_VECTOR_REPAIR_PINECONE_NAMESPACE",
    "make_v17_pinecone_vector_deleter",
    "make_v17_pinecone_vector_repairer",
]
