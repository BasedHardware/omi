"""Canonical alias module for ``utils.memory.v17_v3_gcp_evidence_run_record`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_gcp_evidence_run_record import (
    APPROVAL_FIELDS,
    ExecutionWindow,
    READ_BOUNDS_FIELDS,
    RUN_RECORD_FIELDS,
    RunRecordValidationError,
    ValidatedRunRecord,
    WINDOW_FIELDS,
    validate_run_record,
)

__all__ = [
    "APPROVAL_FIELDS",
    "ExecutionWindow",
    "READ_BOUNDS_FIELDS",
    "RUN_RECORD_FIELDS",
    "RunRecordValidationError",
    "ValidatedRunRecord",
    "WINDOW_FIELDS",
    "validate_run_record",
]
