"""Canonical memory-V3-F6 keyed fingerprint helpers."""

from __future__ import annotations

import hashlib
import hmac
import re


class RedactionContractError(ValueError):
    """Raised when fingerprint/redacted output would violate the evidence contract."""


FingerprintContractError = RedactionContractError


HMAC_KEY = b"memory-v3-f6f-local-redaction-contract"
FINGERPRINT_RE = re.compile(r"^hmac:[a-z0-9_-]+:[0-9a-f]{32}$")


def fingerprint(value: str, *, key_id: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedactionContractError("fingerprint value must be a non-empty string")
    if not re.fullmatch(r"[a-z0-9_-]+", key_id):
        raise RedactionContractError("fingerprint key_id must be explicit and stable")
    digest = hmac.new(HMAC_KEY + b":" + key_id.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"hmac:{key_id}:{digest}"


__all__ = ["FINGERPRINT_RE", "HMAC_KEY", "FingerprintContractError", "RedactionContractError", "fingerprint"]
