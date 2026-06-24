"""Backward-compatible shim — implementation lives in ``utils.memory.v3_gcp_evidence_run_record`` (WS-G8b)."""

from utils.memory.v3_gcp_evidence_run_record import (
    APPROVAL_FIELDS,
    ExecutionWindow,
    READ_BOUNDS_FIELDS,
    RUN_RECORD_FIELDS,
    RunRecordValidationError,
    validate_run_record,
    ValidatedRunRecord,
    WINDOW_FIELDS,
)

__all__ = [
    "APPROVAL_FIELDS",
    "ExecutionWindow",
    "READ_BOUNDS_FIELDS",
    "RUN_RECORD_FIELDS",
    "RunRecordValidationError",
    "validate_run_record",
    "ValidatedRunRecord",
    "WINDOW_FIELDS",
]
