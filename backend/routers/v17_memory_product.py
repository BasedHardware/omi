"""Backward-compatible shim — implementation in ``routers.memory_product`` (WS-G9)."""

from routers.memory_product import (
    V17_GLOBAL_READ_GATE_PATH,
    _current_time,
    _require_v17_product_authorization,
    db,
    fetch_archive_product_memory_search,
    fetch_default_product_memory_search,
    router,
    search_v17_archive_memory,
    search_v17_product_memory,
    search_v17_vector_memory,
)

__all__ = [
    "V17_GLOBAL_READ_GATE_PATH",
    "_current_time",
    "_require_v17_product_authorization",
    "db",
    "fetch_archive_product_memory_search",
    "fetch_default_product_memory_search",
    "router",
    "search_v17_archive_memory",
    "search_v17_product_memory",
    "search_v17_vector_memory",
]
