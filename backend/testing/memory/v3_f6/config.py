"""Canonical local-only memory-V3-F6 GCP evidence target registry/schema.

No cloud SDKs, clients, credentials, or network calls are imported or constructed
here. This module owns the schema and validation logic; local placeholder
defaults live in :mod:`testing.memory.v3_f6.local_defaults`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testing.memory.v3_f6._validation import require_exact_fields


class ValidationError(ValueError):
    """Raised when target registry/config validation fails closed."""


PLACEHOLDER_MARKERS = ("PLACEHOLDER", "example", "000000", "TODO", "fake")
TARGET_FIELDS = frozenset(
    {
        "project_id",
        "project_number",
        "env_label",
        "evidence_principal",
        "approved_metadata_paths",
        "index_expectations",
        "audit_settings",
        "limits",
    }
)
AUDIT_FIELDS = frozenset({"enabled", "log_name", "require_zero_write_methods"})
LIMIT_FIELDS = frozenset({"max_documents_per_path", "max_paths", "per_rpc_timeout_seconds", "overall_deadline_seconds"})
INDEX_FIELDS = frozenset({"fields", "query_scope", "state"})


@dataclass(frozen=True)
class AuditSettings:
    enabled: bool
    log_name: str
    require_zero_write_methods: bool


@dataclass(frozen=True)
class EvidenceLimits:
    max_documents_per_path: int
    max_paths: int
    per_rpc_timeout_seconds: int
    overall_deadline_seconds: int


@dataclass(frozen=True)
class EvidenceTarget:
    name: str
    project_id: str
    project_number: str
    env_label: str
    evidence_principal: str
    approved_metadata_paths: tuple[str, ...]
    index_expectations: dict[str, dict[str, Any]]
    audit_settings: AuditSettings
    limits: EvidenceLimits

    def validate_for_real_execution(self, *, project_id: str, project_number: str, evidence_principal: str) -> None:
        """Require concrete, exact target identity before any real evidence run."""
        for field_name, value in (
            ("project_id", self.project_id),
            ("project_number", self.project_number),
            ("evidence_principal", self.evidence_principal),
        ):
            if _has_placeholder(value):
                raise ValidationError(
                    f"{self.name}.{field_name} contains placeholder and cannot authorize real execution"
                )
        if project_id != self.project_id:
            raise ValidationError("project_id does not match target registry")
        if project_number != self.project_number:
            raise ValidationError("project_number does not match target registry")
        if evidence_principal != self.evidence_principal:
            raise ValidationError("evidence_principal does not match target registry")


class EvidenceTargetRegistry:
    def __init__(self, targets: dict[str, EvidenceTarget]):
        self._targets = dict(targets)

    @classmethod
    def from_dict(cls, raw: dict[str, dict[str, Any]]) -> "EvidenceTargetRegistry":
        if not isinstance(raw, dict) or not raw:
            raise ValidationError("registry must be a non-empty mapping")
        targets = {name: _parse_target(name, config) for name, config in raw.items()}
        return cls(targets)

    def target_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._targets))

    def get(self, name: str) -> EvidenceTarget:
        try:
            return self._targets[name]
        except KeyError as exc:
            raise ValidationError(f"unknown target: {name}") from exc


def _has_placeholder(value: Any) -> bool:
    text = str(value)
    return any(marker.lower() in text.lower() for marker in PLACEHOLDER_MARKERS)


def _require_exact_fields(raw: dict[str, Any], expected: frozenset[str], label: str) -> None:
    require_exact_fields(raw, expected, label=label, error_type=ValidationError)


def _parse_target(name: str, raw: dict[str, Any]) -> EvidenceTarget:
    if not isinstance(raw, dict):
        raise ValidationError(f"target {name} must be a mapping")
    _require_exact_fields(raw, TARGET_FIELDS, f"target {name}")
    if raw["env_label"] not in {"dev", "prod"}:
        raise ValidationError("env_label must be dev or prod")
    if raw["env_label"] != name:
        raise ValidationError("target name must match env_label")

    audit = raw["audit_settings"]
    if not isinstance(audit, dict):
        raise ValidationError("audit_settings must be a mapping")
    _require_exact_fields(audit, AUDIT_FIELDS, "audit_settings")

    limits = raw["limits"]
    if not isinstance(limits, dict):
        raise ValidationError("limits must be a mapping")
    _require_exact_fields(limits, LIMIT_FIELDS, "limits")
    parsed_limits = EvidenceLimits(**{k: int(limits[k]) for k in LIMIT_FIELDS})
    if (
        min(
            parsed_limits.max_documents_per_path,
            parsed_limits.max_paths,
            parsed_limits.per_rpc_timeout_seconds,
            parsed_limits.overall_deadline_seconds,
        )
        <= 0
    ):
        raise ValidationError("limits must be positive")

    paths = raw["approved_metadata_paths"]
    if not isinstance(paths, list) or not paths or not all(isinstance(path, str) and path for path in paths):
        raise ValidationError("approved_metadata_paths must be a non-empty string list")
    if len(paths) > parsed_limits.max_paths:
        raise ValidationError("approved_metadata_paths exceed max_paths limit")

    indexes = raw["index_expectations"]
    if not isinstance(indexes, dict) or not indexes:
        raise ValidationError("index_expectations must be a non-empty mapping")
    normalized_indexes: dict[str, dict[str, Any]] = {}
    for index_name, spec in indexes.items():
        if not isinstance(spec, dict):
            raise ValidationError("index_expectations entries must be mappings")
        _require_exact_fields(spec, INDEX_FIELDS, f"index {index_name}")
        normalized_indexes[index_name] = dict(spec)

    return EvidenceTarget(
        name=name,
        project_id=str(raw["project_id"]),
        project_number=str(raw["project_number"]),
        env_label=str(raw["env_label"]),
        evidence_principal=str(raw["evidence_principal"]),
        approved_metadata_paths=tuple(paths),
        index_expectations=normalized_indexes,
        audit_settings=AuditSettings(**audit),
        limits=parsed_limits,
    )


__all__ = [
    "AUDIT_FIELDS",
    "AuditSettings",
    "EvidenceLimits",
    "EvidenceTarget",
    "EvidenceTargetRegistry",
    "INDEX_FIELDS",
    "LIMIT_FIELDS",
    "PLACEHOLDER_MARKERS",
    "TARGET_FIELDS",
    "ValidationError",
]
