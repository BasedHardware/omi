"""Canonical alias module for ``utils.memory.v17_v3_archive_visibility_readiness`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_archive_visibility_readiness import (
    BLOCKED,
    NOT_VISIBLE,
    VISIBLE,
    decide_default_visibility,
    evaluate_archive_short_term_visibility_readiness,
)

__all__ = [
    "BLOCKED",
    "NOT_VISIBLE",
    "VISIBLE",
    "decide_default_visibility",
    "evaluate_archive_short_term_visibility_readiness",
]
