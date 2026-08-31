"""Per-user compatibility/knowledge-ledger writer transition authority.

Only the memory control document and a content-free proof receipt are mutated
here.  In particular, transition completion never rewrites or deletes memory
rows.  Account deletion and privacy enforcement are independent authorities;
callers must not route those operations through ``require_writer_admitted``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import database.memory_apply_store as memory_apply_store
from database._client import get_firestore_client
from database.memory_collections import MemoryCollections
from models.memory_apply import (
    MemoryControlState,
    MemoryWriterClass,
    WriterAdmissionError,
    WriterMode,
    require_writer_admitted,
)
from utils.metrics import record_jit_writer_mode_transition

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WriterTransitionConflictCode(str, Enum):
    missing_control = "missing_control"
    malformed_control = "malformed_control"
    stale_fence = "stale_fence"
    cross_owner = "cross_owner"
    illegal_transition = "illegal_transition"
    invalid_proof = "invalid_proof"


class WriterTransitionError(RuntimeError):
    """Base error for writer admission and transition failures."""


class WriterTransitionConflict(WriterTransitionError):
    """A transition request no longer owns the exact control-state fence."""

    def __init__(self, code: WriterTransitionConflictCode, message: str):
        super().__init__(message)
        self.code = code


class MemoryWriterFence(BaseModel):
    """The complete compare-and-swap fence for writer-mode transitions."""

    model_config = ConfigDict(extra="forbid")

    uid: str
    head_commit_id: str
    account_generation: int = Field(ge=0)
    source_generation: int = Field(ge=0)
    commit_sequence: int = Field(ge=0)
    writer_mode: WriterMode
    writer_epoch: int = Field(ge=0)
    writer_transition_owner: str | None = None

    @classmethod
    def from_control(cls, control: MemoryControlState) -> "MemoryWriterFence":
        return cls(
            uid=control.uid,
            head_commit_id=control.head_commit_id,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
            commit_sequence=control.commit_sequence,
            writer_mode=control.writer_mode,
            writer_epoch=control.writer_epoch,
            writer_transition_owner=control.writer_transition_owner,
        )


class CompleteUnionProofReceipt(BaseModel):
    """Content-free proof joined atomically to transition completion.

    ``extra='forbid'`` is intentional: a caller cannot smuggle memory content,
    row bodies, or an unbounded result set into this control-plane receipt.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["knowledge_ledger_writer_transition.v1"] = "knowledge_ledger_writer_transition.v1"
    status: Literal["complete"] = "complete"
    uid: str
    transition_owner: str
    writer_mode: WriterMode
    target_mode: WriterMode
    writer_epoch: int = Field(ge=1)
    head_commit_id: str
    account_generation: int = Field(ge=0)
    source_generation: int = Field(ge=0)
    commit_sequence: int = Field(ge=0)
    complete_union_digest: str
    complete_union_count: int = Field(ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("uid", "transition_owner", "head_commit_id")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        if not value or not value.strip() or value != value.strip():
            raise ValueError("writer transition proof identifiers must be nonblank and trimmed")
        return value

    @field_validator("complete_union_digest")
    @classmethod
    def validate_complete_union_digest(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("complete-union digest must be a lowercase SHA-256 hex digest")
        return value

    @field_validator("writer_epoch", mode="before")
    @classmethod
    def validate_writer_epoch_is_an_integer(cls, value: Any) -> Any:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("writer_epoch must be an integer")
        return value

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("writer transition proof timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_modes(self) -> "CompleteUnionProofReceipt":
        expected_target = {
            WriterMode.transitioning_to_ledger: WriterMode.ledger,
            WriterMode.transitioning_to_compatibility: WriterMode.compatibility,
        }.get(self.writer_mode)
        if expected_target is None or self.target_mode != expected_target:
            raise ValueError("writer transition proof modes do not describe a legal completion")
        return self


def begin_writer_transition(
    uid: str,
    *,
    target_mode: WriterMode | MemoryWriterClass,
    transition_owner: str,
    expected_control: MemoryControlState,
    db_client: Any | None = None,
) -> MemoryControlState:
    """CAS a stable mode into its transition mode and advance both fences."""

    owner = _required_owner(transition_owner)
    target = _stable_mode(target_mode)
    _require_expected_owner(uid, expected_control)
    if expected_control.writer_mode not in {WriterMode.compatibility, WriterMode.ledger}:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition,
            "transition entry requires a stable expected writer mode",
        )
    if expected_control.writer_mode == target:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition,
            "writer transition target is already the expected stable mode",
        )
    client = _client_or_default(db_client)
    result = _execute_transaction(
        _begin_writer_transition_transaction,
        client,
        uid,
        target,
        owner,
        MemoryWriterFence.from_control(expected_control),
    )
    if result.writer_epoch == expected_control.writer_epoch + 1:
        try:
            record_jit_writer_mode_transition(
                from_mode=expected_control.writer_mode.value,
                to_mode=result.writer_mode.value,
            )
        except Exception:
            pass
    return result


def _begin_writer_transition_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    target_mode: WriterMode,
    transition_owner: str,
    expected_fence: MemoryWriterFence,
) -> MemoryControlState:
    control_ref = _document(db_client, MemoryCollections(uid=uid).memory_apply_control_state)
    current = _read_control(control_ref, transaction=transaction, uid=uid)
    transition_mode = _transition_mode_for(target_mode)

    if _is_begin_replay(current, expected_fence, transition_mode, transition_owner):
        return current
    if (
        current.writer_mode
        in {
            WriterMode.transitioning_to_ledger,
            WriterMode.transitioning_to_compatibility,
        }
        and current.writer_transition_owner != transition_owner
    ):
        raise WriterTransitionConflict(WriterTransitionConflictCode.cross_owner, "writer transition has another owner")
    if MemoryWriterFence.from_control(current) != expected_fence:
        raise WriterTransitionConflict(WriterTransitionConflictCode.stale_fence, "writer transition fence is stale")
    if current.writer_mode not in {WriterMode.compatibility, WriterMode.ledger}:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition, "writer mode is already transitioning"
        )
    if current.writer_mode == target_mode:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition,
            "writer transition target is already the stable mode",
        )
    if (current.writer_mode, target_mode) not in {
        (WriterMode.compatibility, WriterMode.ledger),
        (WriterMode.ledger, WriterMode.compatibility),
    }:
        raise WriterTransitionConflict(WriterTransitionConflictCode.illegal_transition, "illegal writer transition")

    transitioned = _validated_control_update(
        current,
        writer_mode=transition_mode,
        writer_epoch=current.writer_epoch + 1,
        source_generation=current.source_generation + 1,
        writer_transition_owner=transition_owner,
        updated_at=datetime.now(timezone.utc),
    )
    transaction.set(control_ref, transitioned.model_dump(mode="python"))
    return transitioned


def complete_writer_transition(
    uid: str,
    *,
    transition_owner: str,
    expected_control: MemoryControlState,
    receipt: CompleteUnionProofReceipt | Mapping[str, Any],
    db_client: Any | None = None,
) -> MemoryControlState:
    """Complete an exact transition fence after an atomic content-free proof."""

    owner = _required_owner(transition_owner)
    _require_expected_owner(uid, expected_control)
    _require_transition_expected(expected_control, owner)
    try:
        validated_receipt = CompleteUnionProofReceipt.model_validate(receipt)
    except (TypeError, ValueError) as exc:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.invalid_proof, "writer transition proof is malformed"
        ) from exc
    _validate_receipt_fence(validated_receipt, MemoryWriterFence.from_control(expected_control), owner)
    client = _client_or_default(db_client)
    result = _execute_transaction(
        _complete_writer_transition_transaction,
        client,
        uid,
        owner,
        MemoryWriterFence.from_control(expected_control),
        validated_receipt,
    )
    if result.writer_mode != expected_control.writer_mode:
        try:
            record_jit_writer_mode_transition(
                from_mode=expected_control.writer_mode.value,
                to_mode=result.writer_mode.value,
            )
        except Exception:
            pass
    return result


def _complete_writer_transition_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    transition_owner: str,
    expected_fence: MemoryWriterFence,
    receipt: CompleteUnionProofReceipt,
) -> MemoryControlState:
    control_ref = _document(db_client, MemoryCollections(uid=uid).memory_apply_control_state)
    receipt_ref = _document(db_client, _receipt_path(uid))
    current = _read_control(control_ref, transaction=transaction, uid=uid)
    receipt_snapshot = receipt_ref.get(transaction=transaction)

    if _is_completed_replay(current, expected_fence, receipt.target_mode):
        persisted = _parse_persisted_receipt(receipt_snapshot)
        if persisted != receipt:
            raise WriterTransitionConflict(
                WriterTransitionConflictCode.invalid_proof,
                "completed writer transition proof does not match the persisted receipt",
            )
        return current
    if (
        current.writer_mode
        in {
            WriterMode.transitioning_to_ledger,
            WriterMode.transitioning_to_compatibility,
        }
        and current.writer_transition_owner != transition_owner
    ):
        raise WriterTransitionConflict(WriterTransitionConflictCode.cross_owner, "writer transition has another owner")
    if MemoryWriterFence.from_control(current) != expected_fence:
        raise WriterTransitionConflict(WriterTransitionConflictCode.stale_fence, "writer transition fence is stale")
    if current.writer_transition_owner != transition_owner:
        raise WriterTransitionConflict(WriterTransitionConflictCode.cross_owner, "writer transition owner mismatch")
    if current.writer_mode != receipt.writer_mode:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition, "proof targets another transition"
        )

    completed = _validated_control_update(
        current,
        writer_mode=receipt.target_mode,
        writer_transition_owner=None,
        updated_at=datetime.now(timezone.utc),
    )
    # All transaction reads are complete before either write.  This ordering is
    # intentionally covered with StrictFirestore.
    transaction.set(receipt_ref, receipt.model_dump(mode="python"))
    transaction.set(control_ref, completed.model_dump(mode="python"))
    return completed


def abort_writer_transition(
    uid: str,
    *,
    transition_owner: str,
    expected_control: MemoryControlState,
    db_client: Any | None = None,
) -> MemoryControlState:
    """Return an exact transition fence to its prior stable writer mode."""

    owner = _required_owner(transition_owner)
    _require_expected_owner(uid, expected_control)
    _require_transition_expected(expected_control, owner)
    client = _client_or_default(db_client)
    return _execute_transaction(
        _abort_writer_transition_transaction,
        client,
        uid,
        owner,
        MemoryWriterFence.from_control(expected_control),
    )


def _abort_writer_transition_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    transition_owner: str,
    expected_fence: MemoryWriterFence,
) -> MemoryControlState:
    control_ref = _document(db_client, MemoryCollections(uid=uid).memory_apply_control_state)
    current = _read_control(control_ref, transaction=transaction, uid=uid)
    prior_mode = _prior_stable_mode(expected_fence.writer_mode)

    if _is_aborted_replay(current, expected_fence, prior_mode):
        return current
    if (
        current.writer_mode
        in {
            WriterMode.transitioning_to_ledger,
            WriterMode.transitioning_to_compatibility,
        }
        and current.writer_transition_owner != transition_owner
    ):
        raise WriterTransitionConflict(WriterTransitionConflictCode.cross_owner, "writer transition has another owner")
    if MemoryWriterFence.from_control(current) != expected_fence:
        raise WriterTransitionConflict(WriterTransitionConflictCode.stale_fence, "writer transition fence is stale")
    if current.writer_transition_owner != transition_owner:
        raise WriterTransitionConflict(WriterTransitionConflictCode.cross_owner, "writer transition owner mismatch")

    aborted = _validated_control_update(
        current,
        writer_mode=prior_mode,
        writer_transition_owner=None,
        updated_at=datetime.now(timezone.utc),
    )
    transaction.set(control_ref, aborted.model_dump(mode="python"))
    return aborted


def _execute_transaction(function: Any, db_client: Any, *args: Any) -> Any:
    """Bind the Firestore decorator at call time so strict local fakes share production semantics."""
    return memory_apply_store.transactional(function)(db_client.transaction(), db_client, *args)


def _client_or_default(db_client: Any | None) -> Any:
    if db_client is not None:
        return db_client
    return get_firestore_client()


def _document(db_client: Any, path: str) -> Any:
    document = getattr(db_client, "document", None)
    if callable(document):
        return document(path)
    parts = path.split("/")
    if len(parts) < 2 or len(parts) % 2:
        raise ValueError("Firestore document path must contain collection/document pairs")
    ref = db_client.collection(parts[0]).document(parts[1])
    for index in range(2, len(parts), 2):
        ref = ref.collection(parts[index]).document(parts[index + 1])
    return ref


def _receipt_path(uid: str) -> str:
    return MemoryCollections(uid=uid).knowledge_ledger_writer_transition_receipt


def _read_control(ref: Any, *, transaction: Any, uid: str) -> MemoryControlState:
    snapshot = ref.get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        raise WriterTransitionConflict(WriterTransitionConflictCode.missing_control, "memory control state is missing")
    try:
        control = MemoryControlState.model_validate(snapshot.to_dict() or {})
    except (TypeError, ValueError) as exc:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.malformed_control, "memory control state is malformed"
        ) from exc
    if control.uid != uid:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.cross_owner, "memory control state belongs to another user"
        )
    return control


def _parse_persisted_receipt(snapshot: Any) -> CompleteUnionProofReceipt:
    if not getattr(snapshot, "exists", False):
        raise WriterTransitionConflict(WriterTransitionConflictCode.invalid_proof, "writer transition proof is missing")
    try:
        return CompleteUnionProofReceipt.model_validate(snapshot.to_dict() or {})
    except (TypeError, ValueError) as exc:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.invalid_proof, "persisted writer proof is malformed"
        ) from exc


def _required_owner(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.cross_owner,
            "writer transition owner must be nonblank and trimmed",
        )
    return value


def _stable_mode(value: WriterMode | MemoryWriterClass) -> WriterMode:
    try:
        mode = WriterMode(getattr(value, "value", value))
    except ValueError as exc:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition, "unknown writer target mode"
        ) from exc
    if mode not in {WriterMode.compatibility, WriterMode.ledger}:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition, "writer target must be a stable mode"
        )
    return mode


def _transition_mode_for(target_mode: WriterMode) -> WriterMode:
    return {
        WriterMode.ledger: WriterMode.transitioning_to_ledger,
        WriterMode.compatibility: WriterMode.transitioning_to_compatibility,
    }[target_mode]


def _prior_stable_mode(transition_mode: WriterMode) -> WriterMode:
    try:
        return {
            WriterMode.transitioning_to_ledger: WriterMode.compatibility,
            WriterMode.transitioning_to_compatibility: WriterMode.ledger,
        }[transition_mode]
    except KeyError as exc:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition,
            "abort requires a transitioning writer fence",
        ) from exc


def _require_expected_owner(uid: str, control: MemoryControlState) -> None:
    if control.uid != uid:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.cross_owner, "expected writer fence belongs to another user"
        )


def _require_transition_expected(control: MemoryControlState, transition_owner: str) -> None:
    if control.writer_mode not in {
        WriterMode.transitioning_to_ledger,
        WriterMode.transitioning_to_compatibility,
    }:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.illegal_transition,
            "operation requires a transitioning expected writer mode",
        )
    if control.writer_transition_owner != transition_owner:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.cross_owner, "expected transition has another owner"
        )


def _validated_control_update(control: MemoryControlState, **updates: Any) -> MemoryControlState:
    return MemoryControlState.model_validate({**control.model_dump(mode="python"), **updates})


def _same_nonmode_fence(current: MemoryWriterFence, expected: MemoryWriterFence) -> bool:
    return (
        current.uid,
        current.head_commit_id,
        current.account_generation,
        current.source_generation,
        current.commit_sequence,
        current.writer_epoch,
    ) == (
        expected.uid,
        expected.head_commit_id,
        expected.account_generation,
        expected.source_generation,
        expected.commit_sequence,
        expected.writer_epoch,
    )


def _is_begin_replay(
    current: MemoryControlState,
    expected: MemoryWriterFence,
    transition_mode: WriterMode,
    transition_owner: str,
) -> bool:
    current_fence = MemoryWriterFence.from_control(current)
    return (
        expected.writer_mode in {WriterMode.compatibility, WriterMode.ledger}
        and current.writer_mode == transition_mode
        and current.writer_transition_owner == transition_owner
        and current.uid == expected.uid
        and current.head_commit_id == expected.head_commit_id
        and current.account_generation == expected.account_generation
        and current.commit_sequence == expected.commit_sequence
        and current.source_generation == expected.source_generation + 1
        and current.writer_epoch == expected.writer_epoch + 1
        and current_fence.writer_mode == transition_mode
    )


def _is_completed_replay(current: MemoryControlState, expected: MemoryWriterFence, target_mode: WriterMode) -> bool:
    current_fence = MemoryWriterFence.from_control(current)
    return (
        expected.writer_mode
        in {
            WriterMode.transitioning_to_ledger,
            WriterMode.transitioning_to_compatibility,
        }
        and current.writer_mode == target_mode
        and current.writer_transition_owner is None
        and _same_nonmode_fence(current_fence, expected)
    )


def _is_aborted_replay(current: MemoryControlState, expected: MemoryWriterFence, prior_mode: WriterMode) -> bool:
    current_fence = MemoryWriterFence.from_control(current)
    return (
        current.writer_mode == prior_mode
        and current.writer_transition_owner is None
        and _same_nonmode_fence(current_fence, expected)
    )


def _validate_receipt_fence(
    receipt: CompleteUnionProofReceipt,
    expected: MemoryWriterFence,
    transition_owner: str,
) -> None:
    if expected.writer_transition_owner != transition_owner:
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.cross_owner,
            "complete-union proof owner does not own the expected transition",
        )
    if (
        receipt.uid,
        receipt.head_commit_id,
        receipt.account_generation,
        receipt.source_generation,
        receipt.commit_sequence,
        receipt.writer_mode,
        receipt.writer_epoch,
        receipt.transition_owner,
    ) != (
        expected.uid,
        expected.head_commit_id,
        expected.account_generation,
        expected.source_generation,
        expected.commit_sequence,
        expected.writer_mode,
        expected.writer_epoch,
        transition_owner,
    ):
        raise WriterTransitionConflict(
            WriterTransitionConflictCode.invalid_proof,
            "complete-union proof does not match the expected writer fence",
        )


__all__ = [
    "CompleteUnionProofReceipt",
    "MemoryWriterClass",
    "MemoryWriterFence",
    "WriterAdmissionError",
    "WriterTransitionConflict",
    "WriterTransitionConflictCode",
    "WriterTransitionError",
    "abort_writer_transition",
    "begin_writer_transition",
    "complete_writer_transition",
    "require_writer_admitted",
]
