"""Read-only evidence client contracts for memory-V3-F6."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

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
