"""Local test doubles for memory-V3-F6 read-only evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from testing.memory.v3_f6.audit import AuditLogEvent, AuditQuery
from testing.memory.v3_f6.read_evidence import ReadEvidenceRequest


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
