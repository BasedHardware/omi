"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.identity_iam`` (WS-G8b)."""

from utils.memory.v3_f6.identity_iam import (
    FORBIDDEN_BROAD_ROLES,
    FORBIDDEN_WRITE_PERMISSIONS,
    IdentityIamSource,
    IdentityIamTarget,
    IdentityIamVerificationResult,
    REQUIRED_READ_PERMISSIONS,
    RunRecord,
    verify_identity_iam,
)

__all__ = [
    "FORBIDDEN_BROAD_ROLES",
    "FORBIDDEN_WRITE_PERMISSIONS",
    "IdentityIamSource",
    "IdentityIamTarget",
    "IdentityIamVerificationResult",
    "REQUIRED_READ_PERMISSIONS",
    "RunRecord",
    "verify_identity_iam",
]
