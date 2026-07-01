"""Identity/IAM contracts for memory-V3-F6 read-only evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from testing.memory.v3_f6.run_context import RunRecord

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


@dataclass(frozen=True)
class IdentityIamTarget:
    project_id: str
    principal: str
    required_read_permissions: frozenset[str] = REQUIRED_READ_PERMISSIONS
    forbidden_broad_roles: frozenset[str] = FORBIDDEN_BROAD_ROLES
    forbidden_write_permissions: frozenset[str] = FORBIDDEN_WRITE_PERMISSIONS


class IdentityIamSource(Protocol):
    def effective_project_id(self) -> str: ...

    def effective_principal(self) -> str: ...

    def iam_roles(self) -> frozenset[str]: ...

    def iam_permissions(self) -> frozenset[str]: ...

    def secret_payload_access_was_rejected(self) -> bool: ...


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
