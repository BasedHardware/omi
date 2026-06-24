"""Canonical alias module for ``utils.memory.v17_v3_f6_pre_gcp_aggregate`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_f6_pre_gcp_aggregate import (
    F6_LOCAL_GATE_IDS,
    GCP_ACCESS_GATE_IDS,
    NON_CLAIMS,
    _concrete_registry,
    _hash64,
    _sample_run_record,
    _smoke_current_local_contracts,
    build_pre_gcp_aggregate_report,
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
