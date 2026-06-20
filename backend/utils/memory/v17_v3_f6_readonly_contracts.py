"""V17-V3-F6 local-only read-only evidence contracts.

This module deliberately contains no google-cloud imports and performs no network
I/O.  Real callers can adapt their config/run-record objects into these small
value objects, while tests and dry-run evidence use injected fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

REQUIRED_READ_PERMISSIONS = frozenset(
    {
        "datastore.databases.get",
        "datastore.entities.get",
        "datastore.entities.list",
        "datastore.indexes.list",
        "iam.serviceAccounts.get",
        "resourcemanager.projects.getIamPolicy",
        "secretmanager.secrets.get",
        "logging.logEntries.list",
    }
)
FORBIDDEN_BROAD_ROLES = frozenset({"roles/owner", "roles/editor"})
FORBIDDEN_WRITE_PERMISSIONS = frozenset(
    {
        "datastore.entities.create",
        "datastore.entities.update",
        "datastore.entities.delete",
        "datastore.indexes.create",
        "datastore.indexes.update",
        "datastore.indexes.delete",
        "secretmanager.versions.access",
        "secretmanager.secrets.create",
        "secretmanager.secrets.update",
        "secretmanager.secrets.delete",
        "logging.sinks.create",
        "logging.sinks.update",
        "logging.sinks.delete",
    }
)
GENERIC_OR_RAW_METHODS = frozenset({"request", "send", "raw_transport", "transport", "call", "rpc"})
MUTATOR_TOKENS = (
    "create",
    "update",
    "delete",
    "commit",
    "batch",
    "write",
    "set",
    "patch",
    "mutate",
    "publish",
)
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
class IdentityIamTarget:
    project_id: str
    principal: str
    required_read_permissions: frozenset[str] = REQUIRED_READ_PERMISSIONS
    forbidden_broad_roles: frozenset[str] = FORBIDDEN_BROAD_ROLES
    forbidden_write_permissions: frozenset[str] = FORBIDDEN_WRITE_PERMISSIONS


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    project_id: str
    principal: str


class IdentityIamSource(Protocol):
    def effective_project_id(self) -> str: ...

    def effective_principal(self) -> str: ...

    def iam_roles(self) -> frozenset[str]: ...

    def iam_permissions(self) -> frozenset[str]: ...

    def secret_payload_access_was_rejected(self) -> bool: ...


@dataclass(frozen=True)
class FakeIdentityIamSource:
    project_id: str
    principal: str
    permissions: frozenset[str]
    roles: set[str] | frozenset[str] = field(default_factory=frozenset)
    secret_payload_access_attempted: bool = False

    def effective_project_id(self) -> str:
        return self.project_id

    def effective_principal(self) -> str:
        return self.principal

    def iam_roles(self) -> frozenset[str]:
        return frozenset(self.roles)

    def iam_permissions(self) -> frozenset[str]:
        return frozenset(self.permissions)

    def secret_payload_access_was_rejected(self) -> bool:
        # Metadata-only is acceptable. Any payload access attempt is rejected by
        # this local contract because F6 evidence must never need secret bytes.
        return not self.secret_payload_access_attempted


@dataclass(frozen=True)
class IdentityIamVerificationResult:
    status: str
    effective_project_id: str
    effective_principal: str
    missing_read_permissions: frozenset[str]
    forbidden_roles_present: frozenset[str]
    forbidden_write_permissions_present: frozenset[str]
    secret_payload_access_rejected: bool
    failures: tuple[str, ...]


def verify_identity_iam(
    target: IdentityIamTarget,
    run_record: RunRecord,
    source: IdentityIamSource,
) -> IdentityIamVerificationResult:
    effective_project_id = source.effective_project_id()
    effective_principal = source.effective_principal()
    roles = source.iam_roles()
    permissions = source.iam_permissions()
    missing_read = target.required_read_permissions - permissions
    forbidden_roles = roles & target.forbidden_broad_roles
    forbidden_writes = permissions & target.forbidden_write_permissions
    secret_payload_rejected = source.secret_payload_access_was_rejected()

    failures: list[str] = []
    if effective_project_id != target.project_id:
        failures.append("effective_project_mismatch")
    if effective_principal != target.principal:
        failures.append("effective_principal_mismatch")
    if run_record.project_id != target.project_id:
        failures.append("run_project_mismatch")
    if run_record.principal != target.principal:
        failures.append("run_principal_mismatch")
    if missing_read:
        failures.append("missing_read_permissions")
    if forbidden_roles:
        failures.append("forbidden_broad_roles")
    if forbidden_writes:
        failures.append("forbidden_write_permissions")
    if not secret_payload_rejected:
        failures.append("secret_payload_access_not_rejected")

    return IdentityIamVerificationResult(
        status="FAIL" if failures else "PASS",
        effective_project_id=effective_project_id,
        effective_principal=effective_principal,
        missing_read_permissions=frozenset(missing_read),
        forbidden_roles_present=frozenset(forbidden_roles),
        forbidden_write_permissions_present=frozenset(forbidden_writes),
        secret_payload_access_rejected=secret_payload_rejected,
        failures=tuple(failures),
    )


@dataclass(frozen=True)
class EvidenceClientConfig:
    allowed_methods: frozenset[str]
    per_rpc_timeout_seconds: int = 5
    max_attempts: int = 2
    max_items: int = 25

    def __post_init__(self) -> None:
        if not self.allowed_methods:
            raise ValueError("allowed_methods_required")
        if self.per_rpc_timeout_seconds <= 0:
            raise ValueError("per_rpc_timeout_seconds_must_be_positive")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts_must_be_positive")
        if self.max_items <= 0:
            raise ValueError("max_items_must_be_positive")
        blocked = [method for method in self.allowed_methods if _method_is_forbidden(method)]
        if blocked:
            raise ValueError(f"allowed_methods_contains_forbidden_method:{','.join(sorted(blocked))}")


@dataclass(frozen=True)
class ReadEvidenceRequest:
    run_id: str
    limit: int | None = None
    filters: Mapping[str, Any] = field(default_factory=dict)


class ReadEvidenceTransport(Protocol):
    def read(
        self,
        method: str,
        request: ReadEvidenceRequest,
        *,
        timeout_seconds: int,
        max_attempts: int,
        max_items: int,
    ) -> Sequence[Mapping[str, Any]]: ...


@dataclass
class FakeReadEvidenceTransport:
    responses: Mapping[str, Sequence[Mapping[str, Any]]]
    calls: list[tuple[str, str, int, int, int]] = field(default_factory=list)

    def read(
        self,
        method: str,
        request: ReadEvidenceRequest,
        *,
        timeout_seconds: int,
        max_attempts: int,
        max_items: int,
    ) -> Sequence[Mapping[str, Any]]:
        self.calls.append((method, request.run_id, request.limit or max_items, timeout_seconds, max_attempts))
        return tuple(self.responses.get(method, ()))


class ReadOnlyEvidenceClient:
    def __init__(self, *, transport: ReadEvidenceTransport, config: EvidenceClientConfig) -> None:
        self._transport = transport
        self._config = config

    def call(self, method: str, request: ReadEvidenceRequest) -> list[Mapping[str, Any]]:
        if _method_is_forbidden(method) or method not in self._config.allowed_methods:
            raise PermissionError(f"read_evidence_method_not_allowed:{method}")
        effective_limit = request.limit if request.limit is not None else self._config.max_items
        if effective_limit <= 0 or effective_limit > self._config.max_items:
            raise ValueError("item_limit_exceeded")
        limited_request = ReadEvidenceRequest(run_id=request.run_id, limit=effective_limit, filters=request.filters)
        response = list(
            self._transport.read(
                method,
                limited_request,
                timeout_seconds=self._config.per_rpc_timeout_seconds,
                max_attempts=self._config.max_attempts,
                max_items=self._config.max_items,
            )
        )
        if len(response) > self._config.max_items:
            raise ValueError("item_limit_exceeded")
        return response


def _method_is_forbidden(method: str) -> bool:
    normalized = method.strip().lower()
    if normalized in GENERIC_OR_RAW_METHODS:
        return True
    return any(token in normalized for token in MUTATOR_TOKENS)


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
class FakeAuditLogClient:
    events: Sequence[AuditLogEvent]

    def list_entries(self, query: AuditQuery) -> Sequence[AuditLogEvent]:
        return tuple(
            event
            for event in self.events
            if event.run_id == query.run_id
            and event.project_id == query.project_id
            and event.principal == query.principal
            and query.started_at <= event.timestamp <= query.ended_at
        )


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
