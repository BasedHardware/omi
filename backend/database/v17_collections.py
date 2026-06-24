"""Backward-compatible shim — implementation lives in ``database.memory_collections`` (WS-G7)."""

from database.memory_collections import MemoryCollections, V17Collections

__all__ = ["MemoryCollections", "V17Collections"]
