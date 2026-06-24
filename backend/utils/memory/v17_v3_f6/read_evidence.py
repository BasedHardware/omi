"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.read_evidence`` (WS-G8b)."""

from utils.memory.v3_f6.read_evidence import (
    EvidenceClientConfig,
    GENERIC_OR_RAW_METHODS,
    MUTATOR_TOKENS,
    ReadEvidenceRequest,
    ReadEvidenceTransport,
    ReadOnlyEvidenceClient,
    _method_is_forbidden,
)

__all__ = [
    "EvidenceClientConfig",
    "GENERIC_OR_RAW_METHODS",
    "MUTATOR_TOKENS",
    "ReadEvidenceRequest",
    "ReadEvidenceTransport",
    "ReadOnlyEvidenceClient",
    "_method_is_forbidden",
]
