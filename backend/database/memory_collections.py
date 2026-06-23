"""Canonical alias module for ``database.v17_collections`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_collections import V17Collections

__all__ = ["V17Collections"]
