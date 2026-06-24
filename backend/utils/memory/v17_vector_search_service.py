"""Backward-compatible shim — implementation lives in ``utils.memory.vector_search_service`` (WS-G8a)."""

from utils.memory.vector_search_service import (
    DEFAULT_V17_VECTOR_MAX_CANDIDATES,
    DEFAULT_V17_VECTOR_MAX_QUERIES,
    DEFAULT_V17_VECTOR_OVERFETCH_FACTOR,
    DEFAULT_V17_VECTOR_SEARCH_LIMIT,
    DEFAULT_VECTOR_SEARCH_LIMIT,
    MAX_V17_VECTOR_MAX_QUERIES,
    MAX_V17_VECTOR_OVERFETCH_FACTOR,
    MAX_V17_VECTOR_SEARCH_LIMIT,
    MAX_VECTOR_SEARCH_LIMIT,
    fetch_default_v17_vector_memory_search,
    fetch_default_vector_memory_search,
    query_v17_memory_vector_candidates,
)

__all__ = [
    "DEFAULT_V17_VECTOR_MAX_CANDIDATES",
    "DEFAULT_V17_VECTOR_MAX_QUERIES",
    "DEFAULT_V17_VECTOR_OVERFETCH_FACTOR",
    "DEFAULT_V17_VECTOR_SEARCH_LIMIT",
    "DEFAULT_VECTOR_SEARCH_LIMIT",
    "MAX_V17_VECTOR_MAX_QUERIES",
    "MAX_V17_VECTOR_OVERFETCH_FACTOR",
    "MAX_V17_VECTOR_SEARCH_LIMIT",
    "MAX_VECTOR_SEARCH_LIMIT",
    "fetch_default_v17_vector_memory_search",
    "fetch_default_vector_memory_search",
    "query_v17_memory_vector_candidates",
]
