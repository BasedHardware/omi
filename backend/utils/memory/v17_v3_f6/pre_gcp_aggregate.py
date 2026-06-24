"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.pre_gcp_aggregate`` (WS-G8b)."""

from utils.memory.v3_f6.pre_gcp_aggregate import (
    build_pre_gcp_aggregate_report,
    build_report_from_current_local_contracts,
    F6_LOCAL_GATE_IDS,
    GCP_ACCESS_GATE_IDS,
    NON_CLAIMS,
)

__all__ = [
    "build_pre_gcp_aggregate_report",
    "build_report_from_current_local_contracts",
    "F6_LOCAL_GATE_IDS",
    "GCP_ACCESS_GATE_IDS",
    "NON_CLAIMS",
]
