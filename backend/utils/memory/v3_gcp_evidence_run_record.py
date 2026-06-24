"""Canonical module for ``utils.memory.v3_gcp_evidence_run_record`` (WS-G8b)."""

from __future__ import annotations

from utils.memory.v3_f6.run_record import (
    APPROVAL_FIELDS,
    READ_BOUNDS_FIELDS,
    RUN_RECORD_FIELDS,
    WINDOW_FIELDS,
    ExecutionWindow,
    RunRecordValidationError,
    ValidatedRunRecord,
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

# Neutral symbol aliases (memory names remain valid via shim)
