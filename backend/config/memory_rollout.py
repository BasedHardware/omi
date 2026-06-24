"""Canonical alias module for ``config.v17_memory`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from config.v17_memory import (
    MEMORY_ENABLED_USERS_ENV,
    MEMORY_MODE_ENV,
    PASSED,
    V17Capabilities,
    V17Mode,
    V17RolloutConfig,
    V17RolloutState,
    V17StageGate,
    V17_MEMORY_ENABLED_USERS_ENV,
    V17_MODE_ENV,
    decide_v17_capabilities,
    parse_enabled_users,
    rollout_enabled_users_env_raw,
    rollout_mode_env_value,
)

__all__ = [
    "MEMORY_ENABLED_USERS_ENV",
    "MEMORY_MODE_ENV",
    "PASSED",
    "V17Capabilities",
    "V17Mode",
    "V17RolloutConfig",
    "V17RolloutState",
    "V17StageGate",
    "V17_MEMORY_ENABLED_USERS_ENV",
    "V17_MODE_ENV",
    "decide_v17_capabilities",
    "parse_enabled_users",
    "rollout_enabled_users_env_raw",
    "rollout_mode_env_value",
]
