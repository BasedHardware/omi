"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.fingerprints`` (WS-G8b)."""

from utils.memory.v3_f6.fingerprints import (
    fingerprint,
    FINGERPRINT_RE,
    FingerprintContractError,
    HMAC_KEY,
    RedactionContractError,
)

__all__ = [
    "fingerprint",
    "FINGERPRINT_RE",
    "FingerprintContractError",
    "HMAC_KEY",
    "RedactionContractError",
]
