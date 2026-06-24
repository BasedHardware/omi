"""Canonical alias module for ``utils.memory.v17_product_memory_read_service`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_product_memory_read_service import (
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
