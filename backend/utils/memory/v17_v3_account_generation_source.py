"""Backward-compatible shim — implementation lives in ``utils.memory.v3_account_generation_source`` (WS-G8b)."""

from utils.memory.v3_account_generation_source import (
    read_v17_v3_trusted_account_generation,
    V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
    V17Collections,
    V17V3AccountGenerationFailureReason,
    V17V3TrustedAccountGenerationReadError,
    V17V3TrustedAccountGenerationResult,
    V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
    V3AccountGenerationFailureReason,
    V3TrustedAccountGenerationReadError,
    V3TrustedAccountGenerationResult,
    _fail,
    _MALFORMED_SNAPSHOT_DATA,
    _snapshot_data,
)

__all__ = [
    "read_v17_v3_trusted_account_generation",
    "V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION",
    "V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE",
    "V17Collections",
    "V17V3AccountGenerationFailureReason",
    "V17V3TrustedAccountGenerationReadError",
    "V17V3TrustedAccountGenerationResult",
    "V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION",
    "V3_TRUSTED_ACCOUNT_GENERATION_SOURCE",
    "V3AccountGenerationFailureReason",
    "V3TrustedAccountGenerationReadError",
    "V3TrustedAccountGenerationResult",
    "_fail",
    "_MALFORMED_SNAPSHOT_DATA",
    "_snapshot_data",
]
