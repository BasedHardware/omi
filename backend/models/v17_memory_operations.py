from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.v17_memory_contracts import deterministic_contract_id


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


def build_operation_id(
    *,
    uid: str,
    operation_type: MemoryOperationType | str,
    source_packet_id: Optional[str],
    target_memory_id: Optional[str],
    evidence_ids: List[str],
    logical_payload: Dict[str, Any],
    observed_head_commit_id: Optional[str] = None,
    output_index: Optional[int] = None,
) -> str:
    """Build a server-owned logical idempotency ID.

    `observed_head_commit_id` and model output order/index are intentionally ignored.
    They are execution context, not operation identity.
    """
    resolved_type = operation_type.value if isinstance(operation_type, MemoryOperationType) else operation_type
    payload = {
        "uid": uid,
        "operation_type": resolved_type,
        "source_packet_id": source_packet_id,
        "target_memory_id": target_memory_id,
        "evidence_ids": sorted(evidence_ids or []),
        "logical_payload": logical_payload,
    }
    return "op_" + deterministic_contract_id("v17-memory-operation", payload)[:32]


class MemoryOperation(BaseModel):
    operation_id: str
    uid: str
    operation_type: MemoryOperationType
    status: MemoryOperationStatus
    source_packet_id: Optional[str] = None
    target_memory_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    logical_payload: Dict[str, Any] = Field(default_factory=dict)
    account_generation: int = 0
    source_generation: int = 0
    observed_head_commit_id: Optional[str] = None
    committed_head_commit_id: Optional[str] = None
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
        logical_payload: Dict[str, Any],
        account_generation: int = 0,
        source_generation: int = 0,
        observed_head_commit_id: Optional[str] = None,
        proposed_operation_id: Optional[str] = None,
    ) -> "MemoryOperation":
        operation_id = build_operation_id(
            uid=uid,
            operation_type=operation_type,
            source_packet_id=source_packet_id,
            target_memory_id=target_memory_id,
            evidence_ids=evidence_ids,
            logical_payload=logical_payload,
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
            logical_payload=logical_payload,
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

    @field_validator("account_generation", "source_generation", "attempt_count")
    @classmethod
    def validate_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("generation and attempt counts must be nonnegative")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("operation timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_timestamps(self):
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        return self

    def mark_retryable(self, error_code: str) -> "MemoryOperation":
        return self.model_copy(
            update={
                "status": MemoryOperationStatus.retryable_failure,
                "attempt_count": self.attempt_count + 1,
                "error_code": error_code,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def mark_committed(self, committed_head_commit_id: str) -> "MemoryOperation":
        return self.model_copy(
            update={
                "status": MemoryOperationStatus.committed,
                "committed_head_commit_id": committed_head_commit_id,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def is_stale(self, *, account_generation: int, source_generation: int) -> bool:
        return account_generation != self.account_generation or source_generation != self.source_generation
