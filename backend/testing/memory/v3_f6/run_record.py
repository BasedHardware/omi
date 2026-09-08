"""Canonical local-only memory-V3-F6 evidence approval/run-record validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from testing.memory.v3_f6._validation import require_exact_fields
from testing.memory.v3_f6.config import EvidenceTargetRegistry, ValidationError


class RunRecordValidationError(ValueError):
    """Raised when an evidence run record fails closed."""


RUN_RECORD_FIELDS = frozenset(
    {
        "artifact_version",
        "run_id",
        "one_run_scope",
        "target",
        "project_id",
        "project_number",
        "evidence_principal",
        "approved_metadata_paths",
        "commit",
        "runner_hashes",
        "helper_hashes",
        "execution_window",
        "read_bounds",
        "approvals",
    }
)
WINDOW_FIELDS = frozenset({"started_at", "ended_at", "max_seconds"})
READ_BOUNDS_FIELDS = frozenset({"max_documents_per_path", "max_paths", "allow_collection_scans"})
APPROVAL_FIELDS = frozenset({"role", "approver", "approved_at"})


@dataclass(frozen=True)
class ExecutionWindow:
    started_at: datetime
    ended_at: datetime
    max_seconds: int


@dataclass(frozen=True)
class ValidatedRunRecord:
    artifact_version: str
    run_id: str
    target: str
    project_id: str
    project_number: str
    evidence_principal: str
    approved_metadata_paths: tuple[str, ...]
    commit: str
    execution_window: ExecutionWindow


def validate_run_record(
    raw: dict[str, Any], registry: EvidenceTargetRegistry, *, now: datetime | None = None
) -> ValidatedRunRecord:
    """Validate bounded, one-run evidence artifact metadata.

    This function only validates local dictionaries and never constructs cloud
    clients. All schema surprises fail closed.
    """

    if not isinstance(raw, dict):
        raise RunRecordValidationError("run record must be a mapping")
    _require_exact_fields(raw, RUN_RECORD_FIELDS, "run record")
    if raw["artifact_version"] != "memory-V3-F6B":
        raise RunRecordValidationError("artifact_version must be memory-V3-F6B")
    if raw["one_run_scope"] is not True:
        raise RunRecordValidationError("one_run_scope must be true")

    target_name = _require_str(raw, "target")
    try:
        target = registry.get(target_name)
        target.validate_for_real_execution(
            project_id=_require_str(raw, "project_id"),
            project_number=_require_str(raw, "project_number"),
            evidence_principal=_require_str(raw, "evidence_principal"),
        )
    except ValidationError as exc:
        raise RunRecordValidationError(str(exc)) from exc

    paths = raw["approved_metadata_paths"]
    if not isinstance(paths, list) or not paths:
        raise RunRecordValidationError("approved_metadata_paths must be a non-empty list")
    approved_set = set(target.approved_metadata_paths)
    if any(path not in approved_set for path in paths):
        raise RunRecordValidationError("approved_metadata_paths contain path outside target approval")
    if len(paths) > target.limits.max_paths:
        raise RunRecordValidationError("approved_metadata_paths exceed target path limit")

    commit = _require_str(raw, "commit")
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit.lower()):
        raise RunRecordValidationError("commit must be a 40-character hex sha")
    _validate_hash_map(raw["runner_hashes"], "runner_hashes")
    _validate_hash_map(raw["helper_hashes"], "helper_hashes")
    window = _parse_window(raw["execution_window"])
    # ``now`` is accepted for callers that want deterministic validation in
    # tests, but run-record validity is defined by its bounded window and target
    # scope rather than the validator host clock.
    _ = now
    if (window.ended_at - window.started_at).total_seconds() > window.max_seconds:
        raise RunRecordValidationError("execution_window exceeds max_seconds")
    if window.max_seconds > target.limits.overall_deadline_seconds * 10:
        raise RunRecordValidationError("execution_window max_seconds is unbounded for target")

    bounds = raw["read_bounds"]
    if not isinstance(bounds, dict):
        raise RunRecordValidationError("read_bounds must be a mapping")
    _require_exact_fields(bounds, READ_BOUNDS_FIELDS, "read_bounds")
    if bounds["allow_collection_scans"] is not False:
        raise RunRecordValidationError("collection scans are forbidden")
    if int(bounds["max_documents_per_path"]) > target.limits.max_documents_per_path:
        raise RunRecordValidationError("max_documents_per_path exceeds target limit")
    if int(bounds["max_paths"]) < len(paths) or int(bounds["max_paths"]) > target.limits.max_paths:
        raise RunRecordValidationError("max_paths does not bound approved paths")

    approvals = raw["approvals"]
    if not isinstance(approvals, list):
        raise RunRecordValidationError("approvals must be a list")
    _validate_approvals(approvals, prod=(target.env_label == "prod"))

    return ValidatedRunRecord(
        artifact_version=raw["artifact_version"],
        run_id=_require_str(raw, "run_id"),
        target=target.name,
        project_id=target.project_id,
        project_number=target.project_number,
        evidence_principal=target.evidence_principal,
        approved_metadata_paths=tuple(paths),
        commit=commit,
        execution_window=window,
    )


def _require_exact_fields(raw: dict[str, Any], expected: frozenset[str], label: str) -> None:
    require_exact_fields(raw, expected, label=label, error_type=RunRecordValidationError)


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise RunRecordValidationError(f"{key} must be a non-empty string")
    return value


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise RunRecordValidationError("timestamp must be a string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunRecordValidationError("timestamp must be ISO-8601") from exc


def _parse_window(raw: Any) -> ExecutionWindow:
    if not isinstance(raw, dict):
        raise RunRecordValidationError("execution_window must be a mapping")
    _require_exact_fields(raw, WINDOW_FIELDS, "execution_window")
    started = _parse_time(raw["started_at"])
    ended = _parse_time(raw["ended_at"])
    if started.tzinfo is None or ended.tzinfo is None:
        raise RunRecordValidationError("execution_window timestamps must include timezone")
    if ended < started:
        raise RunRecordValidationError("execution_window ended_at must not precede started_at")
    max_seconds = int(raw["max_seconds"])
    if max_seconds <= 0:
        raise RunRecordValidationError("execution_window max_seconds must be positive")
    return ExecutionWindow(
        started_at=started.astimezone(timezone.utc), ended_at=ended.astimezone(timezone.utc), max_seconds=max_seconds
    )


def _validate_hash_map(raw: Any, label: str) -> None:
    if not isinstance(raw, dict) or not raw:
        raise RunRecordValidationError(f"{label} must be a non-empty mapping")
    for name, digest in raw.items():
        if not isinstance(name, str) or not name:
            raise RunRecordValidationError(f"{label} keys must be file names")
        if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
            raise RunRecordValidationError(f"{label} values must be sha256 digests")
        if any(ch not in "0123456789abcdef" for ch in digest.removeprefix("sha256:").lower()):
            raise RunRecordValidationError(f"{label} values must be hex sha256 digests")


def _validate_approvals(raw: list[Any], *, prod: bool) -> None:
    roles: set[str] = set()
    for approval in raw:
        if not isinstance(approval, dict):
            raise RunRecordValidationError("approvals entries must be mappings")
        _require_exact_fields(approval, APPROVAL_FIELDS, "approval")
        role = approval["role"]
        approver = approval["approver"]
        if role not in {"platform", "security"}:
            raise RunRecordValidationError("approval role must be platform or security")
        if not isinstance(approver, str) or len(approver.strip().split()) < 2:
            raise RunRecordValidationError("approval approver must be a named person")
        _parse_time(approval["approved_at"])
        roles.add(role)
    if prod and not {"platform", "security"}.issubset(roles):
        raise RunRecordValidationError("prod requires named platform and security approvals")


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
