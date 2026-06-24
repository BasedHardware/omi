"""Backward-compatible shim — implementation lives in ``utils.memory.projections`` (WS-G8a)."""

from utils.memory.projections import (
    rebuild_memory_projections,
    rebuild_v17_memory_projections,
)

__all__ = [
    "rebuild_memory_projections",
    "rebuild_v17_memory_projections",
]
