"""Intent-backed knowledge ledger on the canonical MemoryService authority.

This module deliberately owns no database collection. It builds semantic
ledger operations and delegates durability, idempotency, evidence, outbox,
privacy, and deletion behavior to the existing canonical apply transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.memory_contracts import deterministic_contract_id
from models.product_memory import (
    MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS,
    MAX_LEDGER_TRIGGER_CONDITION_CHARACTERS,
    MAX_LEDGER_TRIGGER_CONDITION_KEYS,
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
)
from utils.memory.canonical_memory_adapter import (
    close_canonical_ledger_item,
    read_canonical_memory_item,
    write_canonical_knowledge_ledger_memory,
)

LEDGER_SCHEMA_VERSION = "knowledge_ledger.v1"
DEFAULT_PROFILE_CHARACTER_BUDGET = 2_400
MAX_PLAYBOOK_BODY_CHARACTERS = MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS
MAX_TRIGGER_CONDITION_KEYS = MAX_LEDGER_TRIGGER_CONDITION_KEYS


class LedgerProvenance(BaseModel):
    """Minimum auditable source identity for a ledger write."""

    source_id: str = Field(max_length=256)
    source_type: str = Field(max_length=64)
    source_version: str = Field(default="v1", max_length=64)
    action_id: str = Field(max_length=256)
    artifact_ref: Dict[str, Any] = Field(default_factory=dict, max_length=16)
    quote_refs: List[Dict[str, Any]] = Field(default_factory=list, max_length=8)

    @field_validator("source_id", "source_type", "source_version", "action_id")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("ledger provenance identifiers must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_serialized_provenance(self):
        try:
            artifact = json.dumps(self.artifact_ref, sort_keys=True, separators=(",", ":"))
            quotes = json.dumps(self.quote_refs, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("ledger provenance must be JSON serializable") from exc
        if len(artifact) > 2_000 or len(quotes) > 8_000:
            raise ValueError("ledger provenance exceeds the serialized limit")
        return self


class LedgerWrite(BaseModel):
    kind: MemoryKind
    content: str
    provenance: LedgerProvenance
    write_reason: LedgerWriteReason
    subject_scope: MemorySubjectScope = MemorySubjectScope.primary_user
    subject_entity_id: Optional[str] = None
    slot: Optional[str] = None
    body: Optional[str] = None
    trigger_condition: Dict[str, Any] = Field(default_factory=dict)
    curation_weight: int = 0
    valid_from: Optional[datetime] = None
    user_asserted: bool = False
    supersedes: List[str] = Field(default_factory=list)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("ledger content must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_semantics(self):
        if self.subject_scope == MemorySubjectScope.third_party and not self.subject_entity_id:
            raise ValueError("third-party facts require subject_entity_id")
        if self.kind == MemoryKind.document and len(self.body or "") > MAX_PLAYBOOK_BODY_CHARACTERS:
            raise ValueError("playbook body exceeds the ledger limit")
        if self.kind == MemoryKind.document and not (self.body or "").strip():
            raise ValueError("playbooks require a non-empty body")
        if self.kind != MemoryKind.document and self.body is not None:
            raise ValueError("only playbooks may define a body")
        if self.kind == MemoryKind.trigger and len(self.trigger_condition) > MAX_TRIGGER_CONDITION_KEYS:
            raise ValueError("trigger condition exceeds the ledger key limit")
        try:
            serialized_trigger = json.dumps(self.trigger_condition, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("trigger condition must be JSON serializable") from exc
        if len(serialized_trigger) > MAX_LEDGER_TRIGGER_CONDITION_CHARACTERS:
            raise ValueError("trigger condition exceeds the serialized limit")
        if self.write_reason in {
            LedgerWriteReason.direct_user_statement,
            LedgerWriteReason.explicit_remember,
            LedgerWriteReason.onboarding,
        }:
            self.user_asserted = True
        return self


def _row_id(uid: str, write: LedgerWrite) -> str:
    return (
        "mem_"
        + deterministic_contract_id(
            "knowledge-ledger-row",
            {
                "uid": uid,
                "action_id": write.provenance.action_id,
                "kind": write.kind.value,
                "content": write.content,
                "slot": write.slot,
                "subject_scope": write.subject_scope.value,
                "subject_entity_id": write.subject_entity_id,
                "supersedes": sorted(write.supersedes),
            },
        )[:32]
    )


def _evidence_id(uid: str, provenance: LedgerProvenance) -> str:
    return (
        "ev_"
        + deterministic_contract_id(
            "knowledge-ledger-evidence",
            {
                "uid": uid,
                "source_id": provenance.source_id,
                "source_type": provenance.source_type,
                "source_version": provenance.source_version,
                "action_id": provenance.action_id,
            },
        )[:32]
    )


def save_ledger_write(uid: str, write: LedgerWrite, *, db_client: Any = None) -> str:
    """Commit one idempotent semantic row through canonical apply."""
    memory_id = _row_id(uid, write)
    evidence_id = _evidence_id(uid, write.provenance)
    return write_canonical_knowledge_ledger_memory(
        uid,
        {
            "id": memory_id,
            "content": write.content,
            "ledger_schema_version": LEDGER_SCHEMA_VERSION,
            "memory_tier": MemoryLayer.long_term.value,
            "kind": write.kind.value,
            "subject_scope": write.subject_scope.value,
            "subject_entity_id": write.subject_entity_id,
            "slot": write.slot,
            "body": write.body,
            "valid_from": write.valid_from or datetime.now(timezone.utc),
            "curation_weight": write.curation_weight,
            "trigger_condition": write.trigger_condition,
            "intent_backed": True,
            "write_reason": write.write_reason.value,
            "manually_added": write.user_asserted,
            "user_asserted": write.user_asserted,
            "supersedes": sorted(set(write.supersedes)),
            "extractor_id": "knowledge_ledger",
            "evidence": [
                {
                    "evidence_id": evidence_id,
                    "source_id": write.provenance.source_id,
                    "source_type": write.provenance.source_type,
                    "source_version": write.provenance.source_version,
                    "artifact_ref": write.provenance.artifact_ref,
                    "quote_refs": write.provenance.quote_refs,
                }
            ],
        },
        db_client=db_client,
    )


def save_fact(
    uid: str,
    content: str,
    *,
    provenance: LedgerProvenance,
    write_reason: LedgerWriteReason,
    slot: Optional[str] = None,
    subject_scope: MemorySubjectScope = MemorySubjectScope.primary_user,
    subject_entity_id: Optional[str] = None,
    curation_weight: int = 0,
    db_client: Any = None,
) -> str:
    return save_ledger_write(
        uid,
        LedgerWrite(
            kind=MemoryKind.fact,
            content=content,
            provenance=provenance,
            write_reason=write_reason,
            slot=slot,
            subject_scope=subject_scope,
            subject_entity_id=subject_entity_id,
            curation_weight=curation_weight,
        ),
        db_client=db_client,
    )


def amend_fact(
    uid: str,
    prior_memory_id: str,
    content: str,
    *,
    provenance: LedgerProvenance,
    write_reason: LedgerWriteReason,
    slot: Optional[str] = None,
    subject_scope: MemorySubjectScope = MemorySubjectScope.primary_user,
    subject_entity_id: Optional[str] = None,
    curation_weight: int = 0,
    db_client: Any = None,
) -> str:
    """Append a replacement and close the prior row in one canonical commit."""
    return save_ledger_write(
        uid,
        LedgerWrite(
            kind=MemoryKind.fact,
            content=content,
            provenance=provenance,
            write_reason=write_reason,
            slot=slot,
            subject_scope=subject_scope,
            subject_entity_id=subject_entity_id,
            curation_weight=curation_weight,
            supersedes=[prior_memory_id],
        ),
        db_client=db_client,
    )


def close_fact(
    uid: str,
    memory_id: str,
    *,
    valid_to: Optional[datetime] = None,
    db_client: Any = None,
) -> MemoryItem:
    return close_canonical_ledger_item(uid, memory_id, valid_to=valid_to, db_client=db_client)


def write_playbook(
    uid: str,
    description: str,
    body: str,
    *,
    provenance: LedgerProvenance,
    prior_memory_id: Optional[str] = None,
    db_client: Any = None,
) -> str:
    return save_ledger_write(
        uid,
        LedgerWrite(
            kind=MemoryKind.document,
            content=description,
            body=body,
            provenance=provenance,
            write_reason=LedgerWriteReason.recurring_workflow,
            supersedes=[prior_memory_id] if prior_memory_id else [],
        ),
        db_client=db_client,
    )


def read_playbook(uid: str, memory_id: str, *, db_client: Any = None) -> str:
    item = read_canonical_memory_item(uid, memory_id, db_client=db_client)
    if item is None or item.kind != MemoryKind.document:
        raise ValueError(f"active playbook not found: {memory_id}")
    return item.body or ""


def create_trigger(
    uid: str,
    description: str,
    condition: Dict[str, Any],
    *,
    provenance: LedgerProvenance,
    prior_memory_id: Optional[str] = None,
    db_client: Any = None,
) -> str:
    return save_ledger_write(
        uid,
        LedgerWrite(
            kind=MemoryKind.trigger,
            content=description,
            trigger_condition=condition,
            provenance=provenance,
            write_reason=LedgerWriteReason.standing_trigger,
            supersedes=[prior_memory_id] if prior_memory_id else [],
        ),
        db_client=db_client,
    )


def render_profile(
    items: Iterable[MemoryItem],
    *,
    character_budget: int = DEFAULT_PROFILE_CHARACTER_BUDGET,
) -> str:
    """Render a deterministic, bounded profile from current user facts only."""
    if character_budget < 0:
        raise ValueError("character_budget must be nonnegative")
    eligible = [
        item
        for item in items
        if item.ledger_schema_version == LEDGER_SCHEMA_VERSION
        and item.kind == MemoryKind.fact
        and item.subject_scope == MemorySubjectScope.primary_user
        and item.status == MemoryItemStatus.active
        and item.intent_backed
        and item.valid_to is None
        and item.slot
        and (item.content or "").strip()
    ]
    eligible.sort(
        key=lambda item: (
            -item.curation_weight,
            item.slot or "",
            item.valid_from or item.captured_at,
            item.memory_id,
        )
    )
    lines: List[str] = []
    used = 0
    for item in eligible:
        line = f"{item.slot}: {(item.content or '').strip()}"
        separator = 1 if lines else 0
        if used + separator + len(line) > character_budget:
            continue
        lines.append(line)
        used += separator + len(line)
    return "\n".join(lines)


def render_playbook_index(
    items: Iterable[MemoryItem],
    *,
    character_budget: int = 800,
) -> str:
    """Render one-line progressive-disclosure handles, never playbook bodies."""
    active = [
        item
        for item in items
        if item.ledger_schema_version == LEDGER_SCHEMA_VERSION
        and item.kind == MemoryKind.document
        and item.status == MemoryItemStatus.active
        and item.valid_to is None
    ]
    active.sort(key=lambda item: (-(item.curation_weight), item.content or "", item.memory_id))
    lines: List[str] = []
    used = 0
    for item in active:
        line = f"{item.memory_id}: {(item.content or '').strip()}"
        separator = 1 if lines else 0
        if used + separator + len(line) > character_budget:
            continue
        lines.append(line)
        used += separator + len(line)
    return "\n".join(lines)


__all__ = [
    "DEFAULT_PROFILE_CHARACTER_BUDGET",
    "LEDGER_SCHEMA_VERSION",
    "LedgerProvenance",
    "LedgerWrite",
    "amend_fact",
    "close_fact",
    "create_trigger",
    "read_playbook",
    "render_playbook_index",
    "render_profile",
    "save_fact",
    "save_ledger_write",
    "write_playbook",
]
