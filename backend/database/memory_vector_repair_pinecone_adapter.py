"""Canonical alias module for ``database.v17_vector_repair_pinecone_adapter`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_vector_repair_pinecone_adapter import (
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
