"""Backward-compatible shim — implementation lives in ``utils.memory.product_memory_read_service`` (WS-G8a)."""

from utils.memory.product_memory_read_service import (
    DEFAULT_PRODUCT_MEMORY_READ_LIMIT,
    MAX_PRODUCT_MEMORY_READ_LIMIT,
    fetch_archive_product_memory_search,
    fetch_authoritative_product_memory_items,
    fetch_default_product_memory_search,
)

__all__ = [
    "DEFAULT_PRODUCT_MEMORY_READ_LIMIT",
    "MAX_PRODUCT_MEMORY_READ_LIMIT",
    "fetch_archive_product_memory_search",
    "fetch_authoritative_product_memory_items",
    "fetch_default_product_memory_search",
]
