"""Canonical alias module for ``utils.memory.v17_v3_limited_rollout_config`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_limited_rollout_config import (
    GLOBAL_READ_GATE_PATH,
    OWNER,
    ROUTE_SCOPE,
    V17LimitedRolloutConfigBundle,
    WRITE_CONVERGENCE_GATE_PATH,
    build_disabled_global_read_gate,
    build_limited_rollout_config_bundle,
    build_whitelisted_user_control_state,
    build_write_convergence_gate,
)

__all__ = [
    "GLOBAL_READ_GATE_PATH",
    "OWNER",
    "ROUTE_SCOPE",
    "V17LimitedRolloutConfigBundle",
    "WRITE_CONVERGENCE_GATE_PATH",
    "build_disabled_global_read_gate",
    "build_limited_rollout_config_bundle",
    "build_whitelisted_user_control_state",
    "build_write_convergence_gate",
]
