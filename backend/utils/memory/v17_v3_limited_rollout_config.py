"""Backward-compatible shim — implementation lives in ``utils.memory.v3_limited_rollout_config`` (WS-G8b)."""

from utils.memory.v3_limited_rollout_config import (
    build_disabled_global_read_gate,
    build_limited_rollout_config_bundle,
    build_whitelisted_user_control_state,
    build_write_convergence_gate,
    GLOBAL_READ_GATE_PATH,
    OWNER,
    ROUTE_SCOPE,
    V17_DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    V17Collections,
    V17LimitedRolloutConfigBundle,
    WRITE_CONVERGENCE_GATE_PATH,
)

__all__ = [
    "build_disabled_global_read_gate",
    "build_limited_rollout_config_bundle",
    "build_whitelisted_user_control_state",
    "build_write_convergence_gate",
    "GLOBAL_READ_GATE_PATH",
    "OWNER",
    "ROUTE_SCOPE",
    "V17_DEFAULT_READ_ROLLOUT_SCHEMA_VERSION",
    "V17Collections",
    "V17LimitedRolloutConfigBundle",
    "WRITE_CONVERGENCE_GATE_PATH",
]
