"""Backward-compatible shim — implementation lives in ``database.memory_vector_metadata`` (WS-G7)."""

from database.memory_vector_metadata import (
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
