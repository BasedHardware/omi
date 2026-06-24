"""Canonical alias module for ``utils.memory.v17_projections`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_projections import (
    rebuild_v17_memory_projections,
)

__all__ = [
    "rebuild_v17_memory_projections",
]
