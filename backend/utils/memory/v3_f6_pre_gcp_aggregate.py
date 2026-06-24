"""Canonical module for ``utils.memory.v3_f6_pre_gcp_aggregate`` (WS-G8b)."""

from __future__ import annotations

from utils.memory.v3_f6.aggregate import (
    F6_LOCAL_GATE_IDS,
    GCP_ACCESS_GATE_IDS,
    NON_CLAIMS,
    build_pre_gcp_aggregate_report,
)
from utils.memory.v3_f6.local_smoke import (
    _concrete_registry,
    _hash64,
    _sample_run_record,
    _smoke_current_local_contracts,
    build_report_from_current_local_contracts,
)

__all__ = [
    "F6_LOCAL_GATE_IDS",
    "GCP_ACCESS_GATE_IDS",
    "NON_CLAIMS",
    "build_pre_gcp_aggregate_report",
    "build_report_from_current_local_contracts",
    "_hash64",
    "_concrete_registry",
    "_sample_run_record",
    "_smoke_current_local_contracts",
]

# Neutral symbol aliases (memory names remain valid via shim)
