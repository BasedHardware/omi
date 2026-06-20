"""Local-only V17-V3-F6F strict evidence redaction/output contract."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any


class RedactionContractError(ValueError):
    """Raised when redacted output would violate the evidence contract."""


HMAC_KEY = b"v17-v3-f6f-local-redaction-contract"
TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_version",
        "status",
        "target",
        "project_fingerprint",
        "principal_fingerprint",
        "run_fingerprint",
        "approved_metadata_paths",
        "read_bounds",
        "index_expectations",
        "audit",
        "observations",
        "non_claims",
    }
)
OBSERVATION_FIELDS = frozenset({"name", "status", "metadata"})
READ_BOUNDS_FIELDS = frozenset({"max_documents_per_path", "max_paths", "allow_collection_scans"})
AUDIT_FIELDS = frozenset({"enabled", "zero_write_methods"})

FORBIDDEN_FIELD_FRAGMENTS = (
    "raw_memory",
    "memory_content",
    "secret",
    "cursor",
    "token",
    "authorization",
    "auth_header",
    "url",
    "uri",
    "user_id",
    "uid",
    "query",
    "credential",
    "password",
    "request_body",
    "response_body",
    "body",
    "payload",
    "headers",
)
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"\b(cursor|access|refresh|id)[-_ ]?token\b", re.IGNORECASE),
    re.compile(r"\b(password|credential|secret)\s*=", re.IGNORECASE),
    re.compile(r"\buid[_:-]?[A-Za-z0-9]{6,}\b", re.IGNORECASE),
    re.compile(r"\buser[_-]?id\b", re.IGNORECASE),
    re.compile(r"raw query value", re.IGNORECASE),
    re.compile(r"raw memory content", re.IGNORECASE),
)
FINGERPRINT_RE = re.compile(r"^hmac:[a-z0-9_-]+:[0-9a-f]{32}$")


def fingerprint(value: str, *, key_id: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedactionContractError("fingerprint value must be a non-empty string")
    if not re.fullmatch(r"[a-z0-9_-]+", key_id):
        raise RedactionContractError("fingerprint key_id must be explicit and stable")
    digest = hmac.new(HMAC_KEY + b":" + key_id.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"hmac:{key_id}:{digest}"


def validate_redacted_evidence(report: dict[str, Any]) -> None:
    if not isinstance(report, dict):
        raise RedactionContractError("report must be a mapping")
    _require_exact_top_level(report)
    if report["artifact_version"] != "V17-V3-F6F":
        raise RedactionContractError("artifact_version must be V17-V3-F6F")
    for field in ("project_fingerprint", "principal_fingerprint", "run_fingerprint"):
        if not isinstance(report[field], str) or not FINGERPRINT_RE.fullmatch(report[field]):
            raise RedactionContractError(f"{field} must be a keyed HMAC fingerprint")
    _validate_read_bounds(report["read_bounds"])
    _validate_audit(report["audit"])
    _walk(report, path=())


def render_redacted_evidence_json(report: dict[str, Any]) -> str:
    validate_redacted_evidence(report)
    return json.dumps(report, sort_keys=True, indent=2)


def _require_exact_top_level(report: dict[str, Any]) -> None:
    missing = TOP_LEVEL_FIELDS - set(report)
    unknown = set(report) - TOP_LEVEL_FIELDS
    if missing:
        raise RedactionContractError(f"missing fields: {sorted(missing)}")
    if unknown:
        raise RedactionContractError(f"unknown fields: {sorted(unknown)}")


def _validate_read_bounds(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise RedactionContractError("read_bounds must be a mapping")
    unknown = set(raw) - READ_BOUNDS_FIELDS
    missing = READ_BOUNDS_FIELDS - set(raw)
    if unknown:
        raise RedactionContractError(f"read_bounds unknown fields: {sorted(unknown)}")
    if missing:
        raise RedactionContractError(f"read_bounds missing fields: {sorted(missing)}")
    if raw["allow_collection_scans"] is not False:
        raise RedactionContractError("collection scans are not redacted evidence")


def _validate_audit(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise RedactionContractError("audit must be a mapping")
    unknown = set(raw) - AUDIT_FIELDS
    missing = AUDIT_FIELDS - set(raw)
    if unknown:
        raise RedactionContractError(f"audit unknown fields: {sorted(unknown)}")
    if missing:
        raise RedactionContractError(f"audit missing fields: {sorted(missing)}")


def _walk(value: Any, *, path: tuple[str, ...]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RedactionContractError("non-string field names are forbidden")
            _check_field_name(key, path)
            if path == ("observations",) and key not in OBSERVATION_FIELDS:
                raise RedactionContractError(f"observation unknown fields: {key}")
            _walk(item, path=path + (key,))
        return
    if isinstance(value, list):
        for item in value:
            _walk(item, path=path)
        return
    if isinstance(value, str):
        if path == ("non_claims",):
            return
        _check_string_value(value)


def _check_field_name(key: str, path: tuple[str, ...]) -> None:
    if len(path) == 0:
        return
    if path == ("index_expectations",):
        # Firestore index identifiers are approved metadata names in this
        # contract; they may legitimately contain field-name fragments such as
        # ``uid`` without revealing arbitrary user IDs.
        return
    # Metadata is intentionally strict: unknown/sensitive evidence names fail closed
    # instead of being partially redacted after the fact.
    lower = key.lower()
    if any(fragment in lower for fragment in FORBIDDEN_FIELD_FRAGMENTS):
        raise RedactionContractError(f"forbidden field name: {'.'.join(path + (key,))}")


def _check_string_value(value: str) -> None:
    for pattern in FORBIDDEN_VALUE_PATTERNS:
        if pattern.search(value):
            raise RedactionContractError("forbidden sensitive value")
