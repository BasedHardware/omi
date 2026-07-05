from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.memory_contracts import deterministic_contract_id


class MemoryOperationType(str, Enum):
    source_candidate = "source_candidate"
    synthesis = "synthesis"
    long_term_apply = "long_term_apply"
    archive_transition = "archive_transition"
    projection_sync = "projection_sync"
    vector_sync = "vector_sync"
    deletion = "deletion"


class MemoryOperationStatus(str, Enum):
    pending = "pending"
    committed = "committed"
    skipped_idempotent = "skipped_idempotent"
    retryable_failure = "retryable_failure"
    permanent_failure = "permanent_failure"
    stale_generation = "stale_generation"


_TERMINAL_STATUSES = {
    MemoryOperationStatus.committed,
    MemoryOperationStatus.skipped_idempotent,
    MemoryOperationStatus.permanent_failure,
    MemoryOperationStatus.stale_generation,
}


class OperationLogicalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str
    memory_text: Optional[str] = None
    target_memory_id: Optional[str] = None
    result_status: Optional[str] = None
    supersedes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def canonical(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


def _coerce_logical_payload(value: OperationLogicalPayload | Dict[str, Any]) -> OperationLogicalPayload:
    if isinstance(value, OperationLogicalPayload):
        return value
    known = {
        key: value[key]
        for key in ["decision", "memory_text", "target_memory_id", "result_status", "supersedes"]
        if key in value
    }
    metadata = {key: val for key, val in value.items() if key not in known}
    return OperationLogicalPayload(**known, metadata=metadata)


def build_operation_id(
    *,
    uid: str,
    operation_type: MemoryOperationType | str,
    source_packet_id: Optional[str],
    target_memory_id: Optional[str],
    evidence_ids: List[str],
    logical_payload: OperationLogicalPayload | Dict[str, Any],
    account_generation: int,
    source_generation: int,
    observed_head_commit_id: Optional[str] = None,
    output_index: Optional[int] = None,
) -> str:
    """Build a server-owned logical idempotency ID.

    `observed_head_commit_id` and model output order/index are intentionally ignored.
    Account/source generations are included so deletes/purges reset identity space.
    """
    resolved_type = operation_type.value if isinstance(operation_type, MemoryOperationType) else operation_type
    payload_model = _coerce_logical_payload(logical_payload)
    payload = {
        "uid": uid,
        "operation_type": resolved_type,
        "source_packet_id": source_packet_id,
        "target_memory_id": target_memory_id,
        "evidence_ids": sorted(evidence_ids or []),
        "logical_payload": payload_model.canonical(),
        "account_generation": account_generation,
        "source_generation": source_generation,
    }
    return "op_" + deterministic_contract_id("memory-operation", payload)[:32]


def logical_payload_digest(value: OperationLogicalPayload | Dict[str, Any]) -> str:
    return deterministic_contract_id("memory-operation-logical-payload", _coerce_logical_payload(value).canonical())


class MemoryOperation(BaseModel):
    operation_id: str
    uid: str
    operation_type: MemoryOperationType
    status: MemoryOperationStatus
    source_packet_id: Optional[str] = None
    target_memory_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    logical_payload: OperationLogicalPayload
    logical_payload_digest: str
    account_generation: int
    source_generation: int
    observed_head_commit_id: Optional[str] = None
    committed_head_commit_id: Optional[str] = None
    committed_sequence: Optional[int] = None
    committed_memory_item_ids: List[str] = Field(default_factory=list)
    committed_outbox_event_ids: List[str] = Field(default_factory=list)
    attempt_count: int = 0
    error_code: Optional[str] = None
    untrusted_proposed_operation_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def new(
        cls,
        *,
        uid: str,
        operation_type: MemoryOperationType,
        source_packet_id: Optional[str],
        target_memory_id: Optional[str],
        evidence_ids: List[str],
        logical_payload: OperationLogicalPayload | Dict[str, Any],
        account_generation: int,
        source_generation: int,
        observed_head_commit_id: Optional[str] = None,
        proposed_operation_id: Optional[str] = None,
    ) -> "MemoryOperation":
        payload_model = _coerce_logical_payload(logical_payload)
        operation_id = build_operation_id(
            uid=uid,
            operation_type=operation_type,
            source_packet_id=source_packet_id,
            target_memory_id=target_memory_id,
            evidence_ids=evidence_ids,
            logical_payload=payload_model,
            account_generation=account_generation,
            source_generation=source_generation,
            observed_head_commit_id=observed_head_commit_id,
        )
        now = datetime.now(timezone.utc)
        return cls(
            operation_id=operation_id,
            uid=uid,
            operation_type=operation_type,
            status=MemoryOperationStatus.pending,
            source_packet_id=source_packet_id,
            target_memory_id=target_memory_id,
            evidence_ids=evidence_ids,
            logical_payload=payload_model,
            logical_payload_digest=logical_payload_digest(payload_model),
            account_generation=account_generation,
            source_generation=source_generation,
            observed_head_commit_id=observed_head_commit_id,
            untrusted_proposed_operation_id=proposed_operation_id if proposed_operation_id else None,
            created_at=now,
            updated_at=now,
        )

    @field_validator("operation_id", "uid")
    @classmethod
    def validate_required_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("required operation fields must not be blank")
        return value

    @field_validator("committed_head_commit_id", "error_code")
    @classmethod
    def validate_optional_nonblank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("optional operation fields must not be blank")
        return value

    @field_validator("account_generation", "source_generation", "attempt_count")
    @classmethod
    def validate_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("generation and attempt counts must be nonnegative")
        return value

    @field_validator("committed_sequence")
    @classmethod
    def validate_optional_nonnegative(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError("committed_sequence must be nonnegative")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("operation timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_integrity(self):
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        expected = build_operation_id(
            uid=self.uid,
            operation_type=self.operation_type,
            source_packet_id=self.source_packet_id,
            target_memory_id=self.target_memory_id,
            evidence_ids=self.evidence_ids,
            logical_payload=self.logical_payload,
            account_generation=self.account_generation,
            source_generation=self.source_generation,
            observed_head_commit_id=self.observed_head_commit_id,
        )
        if self.operation_id != expected:
            raise ValueError("operation_id does not match server-computed logical identity")
        if self.logical_payload_digest != logical_payload_digest(self.logical_payload):
            raise ValueError("logical_payload_digest does not match canonical logical payload")
        if self.status == MemoryOperationStatus.committed and not self.committed_head_commit_id:
            raise ValueError("committed operations require committed_head_commit_id")
        if self.status == MemoryOperationStatus.committed and self.committed_sequence is None:
            raise ValueError("committed operations require committed_sequence")
        if (
            self.status in {MemoryOperationStatus.retryable_failure, MemoryOperationStatus.permanent_failure}
            and not self.error_code
        ):
            raise ValueError("failure operations require error_code")
        return self

    def _transition(self, *, status: MemoryOperationStatus, **updates: Any) -> "MemoryOperation":
        if self.status in _TERMINAL_STATUSES:
            raise ValueError(f"cannot transition terminal operation from {self.status.value}")
        data = self.dict()
        data.update(updates)
        data["status"] = status
        data["updated_at"] = datetime.now(timezone.utc)
        return MemoryOperation(**data)

    def mark_retryable(self, error_code: str) -> "MemoryOperation":
        return self._transition(
            status=MemoryOperationStatus.retryable_failure,
            attempt_count=self.attempt_count + 1,
            error_code=error_code,
        )

    def mark_committed(
        self,
        committed_head_commit_id: str,
        *,
        committed_sequence: int,
        committed_memory_item_ids: Optional[List[str]] = None,
        committed_outbox_event_ids: Optional[List[str]] = None,
    ) -> "MemoryOperation":
        return self._transition(
            status=MemoryOperationStatus.committed,
            committed_head_commit_id=committed_head_commit_id,
            committed_sequence=committed_sequence,
            committed_memory_item_ids=committed_memory_item_ids or [],
            committed_outbox_event_ids=committed_outbox_event_ids or [],
            error_code=None,
        )

    def is_stale(self, *, account_generation: int, source_generation: int) -> bool:
        return account_generation != self.account_generation or source_generation != self.source_generation


__all__ = [
    "MemoryOperation",
    "MemoryOperationStatus",
    "MemoryOperationType",
    "OperationLogicalPayload",
    "build_operation_id",
    "logical_payload_digest",
]
