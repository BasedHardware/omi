"""Canonical alias module for ``database.v17_v3_compatibility_projection`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_v3_compatibility_projection import (
    read_v17_v3_compatibility_projection_page,
)

__all__ = [
    "read_v17_v3_compatibility_projection_page",
]
