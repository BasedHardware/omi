"""Canonical alias module for ``utils.memory.v17_v3_account_generation_source`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_account_generation_source import (
    V17V3AccountGenerationFailureReason,
    V17V3TrustedAccountGenerationReadError,
    V17V3TrustedAccountGenerationResult,
    V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
    read_v17_v3_trusted_account_generation,
)

__all__ = [
    "V17V3AccountGenerationFailureReason",
    "V17V3TrustedAccountGenerationReadError",
    "V17V3TrustedAccountGenerationResult",
    "V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION",
    "V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE",
    "read_v17_v3_trusted_account_generation",
]
