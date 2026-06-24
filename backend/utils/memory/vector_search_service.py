"""Canonical alias module for ``utils.memory.v17_vector_search_service`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_vector_search_service import (
    DEFAULT_V17_VECTOR_MAX_CANDIDATES,
    DEFAULT_V17_VECTOR_MAX_QUERIES,
    DEFAULT_V17_VECTOR_OVERFETCH_FACTOR,
    DEFAULT_V17_VECTOR_SEARCH_LIMIT,
    MAX_V17_VECTOR_MAX_QUERIES,
    MAX_V17_VECTOR_OVERFETCH_FACTOR,
    MAX_V17_VECTOR_SEARCH_LIMIT,
    fetch_default_v17_vector_memory_search,
)

__all__ = [
    "DEFAULT_V17_VECTOR_MAX_CANDIDATES",
    "DEFAULT_V17_VECTOR_MAX_QUERIES",
    "DEFAULT_V17_VECTOR_OVERFETCH_FACTOR",
    "DEFAULT_V17_VECTOR_SEARCH_LIMIT",
    "MAX_V17_VECTOR_MAX_QUERIES",
    "MAX_V17_VECTOR_OVERFETCH_FACTOR",
    "MAX_V17_VECTOR_SEARCH_LIMIT",
    "fetch_default_v17_vector_memory_search",
]
