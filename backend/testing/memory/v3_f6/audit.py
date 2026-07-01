"""Audit correlation contracts for memory-V3-F6 read-only evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence

WRITE_METHOD_MARKERS = (
    ".commit",
    ".batchwrite",
    ".write",
    ".createdocument",
    ".updatedocument",
    ".deletedocument",
    ".addsecretversion",
    ".accesssecretversion",
    ".createsink",
    ".updatesink",
    ".deletesink",
)


@dataclass(frozen=True)
class AuditLogEvent:
    timestamp: datetime
    run_id: str
    project_id: str
    principal: str
    service: str
    method: str


@dataclass(frozen=True)
class AuditQuery:
    run_id: str
    project_id: str
    principal: str
    started_at: datetime
    ended_at: datetime
    expected_method_families: frozenset[str]

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise ValueError("audit_window_must_be_timezone_aware_utc")
        if self.started_at.utcoffset() != timezone.utc.utcoffset(self.started_at):
            raise ValueError("audit_window_must_be_timezone_aware_utc")
        if self.ended_at.utcoffset() != timezone.utc.utcoffset(self.ended_at):
            raise ValueError("audit_window_must_be_timezone_aware_utc")
        if self.ended_at < self.started_at:
            raise ValueError("audit_window_invalid")


class AuditLogClient(Protocol):
    def list_entries(self, query: AuditQuery) -> Sequence[AuditLogEvent]: ...


@dataclass(frozen=True)
class AuditCorrelationResult:
    status: str
    covered_method_families: frozenset[str]
    missing_method_families: frozenset[str]
    unexpected_write_methods: tuple[str, ...]
    failures: tuple[str, ...]


def assess_audit_correlation(client: AuditLogClient, query: AuditQuery) -> AuditCorrelationResult:
    events = tuple(client.list_entries(query))
    failures: list[str] = []
    unexpected_writes = tuple(event.method for event in events if _audit_method_is_write(event.method))
    covered = frozenset(_method_family(event) for event in events) - frozenset({"unknown"})
    missing = query.expected_method_families - covered

    if unexpected_writes:
        failures.append("unexpected_write_methods")
        status = "FAIL"
    else:
        if not events:
            failures.append("missing_audit_logs")
        if missing and events:
            failures.append("incomplete_method_family_coverage")
        status = "INCONCLUSIVE" if failures else "PASS"

    return AuditCorrelationResult(
        status=status,
        covered_method_families=covered,
        missing_method_families=frozenset(missing),
        unexpected_write_methods=unexpected_writes,
        failures=tuple(failures),
    )


def _audit_method_is_write(method: str) -> bool:
    normalized = method.replace("/", ".").lower()
    return any(marker in normalized for marker in WRITE_METHOD_MARKERS)


def _method_family(event: AuditLogEvent) -> str:
    service = event.service.lower()
    method = event.method.lower()
    if service == "firestore.googleapis.com" or "firestore" in method:
        return "firestore.read"
    if service == "secretmanager.googleapis.com" and ("getsecret" in method or "listsecrets" in method):
        return "secretmanager.metadata"
    if service == "logging.googleapis.com" and ("listlogentries" in method or "logging" in method):
        return "logging.read"
    if service == "iam.googleapis.com":
        return "iam.read"
    if service == "cloudresourcemanager.googleapis.com":
        return "resourcemanager.read"
    return "unknown"
