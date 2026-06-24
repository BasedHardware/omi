"""Backward-compatible shim — implementation lives in ``database.memory_compatibility_projection`` (WS-G7)."""

from database.memory_compatibility_projection import read_v17_v3_compatibility_projection_page

__all__ = ["read_v17_v3_compatibility_projection_page"]
