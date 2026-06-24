"""Canonical vector metadata module (WS-G).

Re-exports legacy V17 builders for the repair worker path and neutral builders for
the canonical-cohort memory path.
"""

from database.v17_vector_metadata import (
    MEMORY_VECTOR_SCHEMA_VERSION,
    V17_MEMORY_VECTOR_ID_PREFIX,
    V17_MEMORY_VECTOR_SCHEMA_VERSION,
    RESTRICTED_SENSITIVITY_LABELS,
    ParsedMemoryVectorHit,
    ParsedV17VectorHit,
    build_archive_memory_vector_filter,
    build_default_memory_vector_filter,
    build_memory_vector_metadata,
    build_v17_archive_memory_vector_filter,
    build_v17_default_memory_vector_filter,
    build_v17_memory_vector_metadata,
    deterministic_v17_memory_vector_id,
    parse_memory_search_vector_hit,
    parse_v17_search_vector_hit,
)

__all__ = [
    "MEMORY_VECTOR_SCHEMA_VERSION",
    "V17_MEMORY_VECTOR_ID_PREFIX",
    "V17_MEMORY_VECTOR_SCHEMA_VERSION",
    "RESTRICTED_SENSITIVITY_LABELS",
    "ParsedMemoryVectorHit",
    "ParsedV17VectorHit",
    "build_archive_memory_vector_filter",
    "build_default_memory_vector_filter",
    "build_memory_vector_metadata",
    "build_v17_archive_memory_vector_filter",
    "build_v17_default_memory_vector_filter",
    "build_v17_memory_vector_metadata",
    "deterministic_v17_memory_vector_id",
    "parse_memory_search_vector_hit",
    "parse_v17_search_vector_hit",
]
