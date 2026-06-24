"""Canonical alias module for ``routers.v17_memory_product`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from routers.v17_memory_product import (
    router,
    search_v17_archive_memory,
    search_v17_product_memory,
    search_v17_vector_memory,
)

__all__ = [
    "router",
    "search_v17_archive_memory",
    "search_v17_product_memory",
    "search_v17_vector_memory",
]
