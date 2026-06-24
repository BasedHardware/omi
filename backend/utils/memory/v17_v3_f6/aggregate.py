"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.aggregate`` (WS-G8b)."""

from utils.memory.v3_f6.aggregate import (
    ARTIFACT_VERSION_F6H,
    build_pre_gcp_aggregate_report,
    DECISION_BLOCKED_ON_GCP_ACCESS,
    DECISION_NO_GO,
    F6_LOCAL_GATE_IDS,
    GCP_ACCESS_GATE_IDS,
    NON_CLAIMS,
    STATUS_BLOCKED,
    STATUS_BLOCKED_ON_GCP_ACCESS,
    STATUS_MISSING,
    STATUS_PASS,
    STATUS_PRE_GCP_READY,
)

__all__ = [
    "ARTIFACT_VERSION_F6H",
    "build_pre_gcp_aggregate_report",
    "DECISION_BLOCKED_ON_GCP_ACCESS",
    "DECISION_NO_GO",
    "F6_LOCAL_GATE_IDS",
    "GCP_ACCESS_GATE_IDS",
    "NON_CLAIMS",
    "STATUS_BLOCKED",
    "STATUS_BLOCKED_ON_GCP_ACCESS",
    "STATUS_MISSING",
    "STATUS_PASS",
    "STATUS_PRE_GCP_READY",
]
