"""Canonical alias module for ``utils.memory.v17_v3_control_state_adapter`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_control_state_adapter import (
    V17_V3_DEFAULT_CONSUMER,
    read_v17_v3_control,
    resolve_v17_v3_effective_mode,
)

__all__ = [
    "V17_V3_DEFAULT_CONSUMER",
    "read_v17_v3_control",
    "resolve_v17_v3_effective_mode",
]
