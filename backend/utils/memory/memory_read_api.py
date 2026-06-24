"""Canonical alias module for ``utils.memory.v17_read_api`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_read_api import (
    query_archive_product_memory_items,
    query_default_product_memory_items,
    query_durable_memory,
    query_l1_archive,
    query_memory_context,
    query_working_memory,
)

__all__ = [
    "query_archive_product_memory_items",
    "query_default_product_memory_items",
    "query_durable_memory",
    "query_l1_archive",
    "query_memory_context",
    "query_working_memory",
]
