"""Compatibility facade for V17-V3-F6 evidence approval/run-record validation."""

from __future__ import annotations

from utils.memory.v17_v3_f6.run_record import (
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
