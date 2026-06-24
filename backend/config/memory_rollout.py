"""Canonical alias module for ``config.v17_memory`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from config.v17_memory import (
    PASSED,
    V17Capabilities,
    V17Mode,
    V17RolloutConfig,
    V17RolloutState,
    V17StageGate,
    decide_v17_capabilities,
    parse_enabled_users,
)

__all__ = [
    "PASSED",
    "V17Capabilities",
    "V17Mode",
    "V17RolloutConfig",
    "V17RolloutState",
    "V17StageGate",
    "decide_v17_capabilities",
    "parse_enabled_users",
]
