"""Canonical alias module for ``database.v17_vector_metadata`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_vector_metadata import (
    V17_MEMORY_VECTOR_ID_PREFIX,
    V17_MEMORY_VECTOR_SCHEMA_VERSION,
    RESTRICTED_SENSITIVITY_LABELS,
    ParsedV17VectorHit,
    build_v17_archive_memory_vector_filter,
    build_v17_default_memory_vector_filter,
    build_v17_memory_vector_metadata,
    deterministic_v17_memory_vector_id,
    parse_v17_search_vector_hit,
)

__all__ = [
    "V17_MEMORY_VECTOR_ID_PREFIX",
    "V17_MEMORY_VECTOR_SCHEMA_VERSION",
    "RESTRICTED_SENSITIVITY_LABELS",
    "ParsedV17VectorHit",
    "build_v17_archive_memory_vector_filter",
    "build_v17_default_memory_vector_filter",
    "build_v17_memory_vector_metadata",
    "deterministic_v17_memory_vector_id",
    "parse_v17_search_vector_hit",
]
