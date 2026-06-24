"""Backward-compatible shim — implementation lives in ``utils.memory.memory_read_api`` (WS-G8a)."""

from utils.memory.memory_read_api import (
    MemoryAccessPolicy,
    MemoryLayer,
    V17MemoryItem,
    query_archive_product_memory_items,
    query_default_product_memory_items,
    query_durable_memory,
    query_l1_archive,
    query_memory_context,
    query_working_memory,
)

__all__ = [
    "MemoryAccessPolicy",
    "MemoryLayer",
    "V17MemoryItem",
    "query_archive_product_memory_items",
    "query_default_product_memory_items",
    "query_durable_memory",
    "query_l1_archive",
    "query_memory_context",
    "query_working_memory",
]
