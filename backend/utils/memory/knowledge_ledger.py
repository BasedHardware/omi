"""Intent-backed knowledge ledger on the canonical MemoryService authority.

This module deliberately owns no database collection. It builds semantic
ledger operations and delegates durability, idempotency, evidence, outbox,
privacy, and deletion behavior to the existing canonical apply transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Iterable, List, Literal, Optional, cast

from pydantic import BaseModel, Field, field_validator, model_validator

from models.knowledge_ledger_policy import (
    PLAYBOOK_HANDLE_CHARACTER_LIMIT,
    PLAYBOOK_INDEX_CHARACTER_BUDGET,
    PROFILE_CHARACTER_BUDGET,
    canonicalize_ledger_slot,
    normalize_playbook_handle,
    render_bounded_profile,
)
from models.memory_evidence import MemoryEvidence
from models.memory_contracts import deterministic_contract_id
from models.memory_operations import MemoryLedgerReopenReceipt
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
    is_direct_user_write_authority,
    memory_item_to_memorydb,
    read_canonical_memory_item,
    write_canonical_direct_user_knowledge_ledger_memory,
    write_canonical_knowledge_ledger_memory,
)
from utils.memory.memory_system import ensure_canonical_apply_control_state

LEDGER_SCHEMA_VERSION = "knowledge_ledger.v1"
DEFAULT_PROFILE_CHARACTER_BUDGET = PROFILE_CHARACTER_BUDGET
MAX_PLAYBOOK_BODY_CHARACTERS = MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS
MAX_TRIGGER_CONDITION_KEYS = MAX_LEDGER_TRIGGER_CONDITION_KEYS
_DIRECT_USER_AMEND_AUTHORITY = object()


def _is_review_visible(item: MemoryItem) -> bool:
    """Reuse the canonical compatibility projection for tri-state review."""

    return memory_item_to_memorydb(item).user_review is not False


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
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    sensitivity_labels: List[str] = Field(default_factory=list)
    valid_from: Optional[datetime] = None
    user_asserted: bool = False
    visibility: Literal["private", "public", "shared"] = "private"
    supersedes: List[str] = Field(default_factory=list)
    preserved_evidence: List[MemoryEvidence] = Field(default_factory=list, exclude=True)

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
        if self.kind == MemoryKind.document and self.write_reason != LedgerWriteReason.recurring_workflow:
            raise ValueError("playbooks require recurring_workflow authority")
        if self.kind == MemoryKind.document and self.subject_scope != MemorySubjectScope.primary_user:
            raise ValueError("playbooks require primary_user scope")
        if self.kind == MemoryKind.document:
            description = normalize_playbook_handle(self.content)
            if len(description) > PLAYBOOK_HANDLE_CHARACTER_LIMIT:
                raise ValueError("playbook description exceeds the compact handle limit")
            self.content = description
        if self.kind != MemoryKind.document and self.body is not None:
            raise ValueError("only playbooks may define a body")
        if self.kind != MemoryKind.fact and self.slot is not None:
            raise ValueError("only facts may define a slot")
        if self.kind == MemoryKind.fact and self.slot is not None:
            # Preserve unknown historical migration labels as unslotted facts;
            # every new semantic write must use the stable registry.
            self.slot = canonicalize_ledger_slot(
                self.slot,
                strict=self.write_reason != LedgerWriteReason.legacy_migration,
            )
        if self.kind == MemoryKind.fact and self.write_reason in {
            LedgerWriteReason.recurring_workflow,
            LedgerWriteReason.standing_trigger,
        }:
            raise ValueError("facts cannot use document or trigger authority")
        if self.kind == MemoryKind.trigger and self.write_reason != LedgerWriteReason.standing_trigger:
            raise ValueError("triggers require standing_trigger authority")
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


def evidence_id_for_ledger_provenance(uid: str, provenance: LedgerProvenance) -> str:
    """Return the stable evidence identity used by one ledger write.

    Retry-aware product mutations use this to recognize their own already
    committed append without relying on content equality or mutable lineage
    position.
    """

    return _evidence_id(uid, provenance)


def save_ledger_write(
    uid: str,
    write: LedgerWrite,
    *,
    db_client: Any = None,
    required_source_item: Optional[MemoryItem] = None,
    ledger_reopen_receipt: Optional[MemoryLedgerReopenReceipt] = None,
    _direct_user_authority: object | None = None,
) -> str:
    """Commit one idempotent semantic row through canonical apply."""
    memory_id = _row_id(uid, write)
    evidence_id = _evidence_id(uid, write.provenance)
    evidence = [
        {
            "evidence_id": evidence_id,
            "source_id": write.provenance.source_id,
            "source_type": write.provenance.source_type,
            "source_version": write.provenance.source_version,
            "artifact_ref": write.provenance.artifact_ref,
            "quote_refs": write.provenance.quote_refs,
        },
        *[item.model_dump(mode="python") for item in write.preserved_evidence if item.evidence_id != evidence_id],
    ]
    write_kwargs: Dict[str, Any] = {
        "db_client": db_client,
        "required_source_item": required_source_item,
    }
    if ledger_reopen_receipt is not None:
        write_kwargs["ledger_reopen_receipt"] = ledger_reopen_receipt
    direct_user_authorized = _direct_user_authority is _DIRECT_USER_AMEND_AUTHORITY or is_direct_user_write_authority(
        _direct_user_authority
    )
    if _direct_user_authority is not None and not direct_user_authorized:
        raise ValueError("unrecognized direct user write authority")
    write_memory = (
        write_canonical_direct_user_knowledge_ledger_memory
        if direct_user_authorized
        else write_canonical_knowledge_ledger_memory
    )
    return write_memory(
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
            "predicate": write.predicate,
            "arguments": write.arguments,
            "sensitivity_labels": write.sensitivity_labels,
            "trigger_condition": write.trigger_condition,
            "intent_backed": True,
            "write_reason": write.write_reason.value,
            "manually_added": write.user_asserted,
            "user_asserted": write.user_asserted,
            "visibility": write.visibility,
            "supersedes": sorted(set(write.supersedes)),
            "extractor_id": "knowledge_ledger",
            "evidence": evidence,
        },
        **write_kwargs,
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
    predicate: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
    valid_from: Optional[datetime] = None,
    visibility: Literal["private", "public", "shared"] = "private",
    db_client: Any = None,
    _direct_user_authority: object | None = None,
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
            predicate=predicate,
            arguments=dict(arguments or {}),
            valid_from=valid_from,
            visibility=visibility,
        ),
        db_client=db_client,
        _direct_user_authority=_direct_user_authority,
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
    valid_from: Optional[datetime] = None,
    visibility: Literal["private", "public", "shared"] = "private",
    db_client: Any = None,
    required_source_item: Optional[MemoryItem] = None,
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
            valid_from=valid_from,
            visibility=visibility,
            supersedes=[prior_memory_id],
        ),
        db_client=db_client,
        required_source_item=required_source_item,
    )


def reopen_standalone_fact(
    uid: str,
    source: MemoryItem,
    *,
    operation_id: str,
    provenance: LedgerProvenance,
    db_client: Any = None,
) -> str:
    """Append one current tail from a standalone closed fact.

    The source is fenced by the canonical Firestore apply transaction.  A
    source-keyed receipt makes a second client operation fail closed even when
    it races the first append; the operation journal makes the same request
    UUID an exact retry no-op.
    """

    if (
        source.ledger_schema_version != LEDGER_SCHEMA_VERSION
        or source.kind != MemoryKind.fact
        or not source.intent_backed
        or source.status != MemoryItemStatus.superseded
        or source.valid_to is None
        or source.superseded_by
        or source.canonical_memory_id
        or source.source_state.value != "active"
        or source.processing_state.value != "processed"
    ):
        raise ValueError("only standalone closed knowledge ledger facts may be reopened")
    write = LedgerWrite(
        kind=MemoryKind.fact,
        content=(source.content or "").strip(),
        provenance=provenance,
        write_reason=LedgerWriteReason.direct_user_statement,
        subject_scope=source.subject_scope,
        subject_entity_id=source.subject_entity_id,
        slot=source.slot,
        curation_weight=source.curation_weight,
        predicate=source.predicate,
        arguments=dict(source.arguments or {}),
        sensitivity_labels=list(source.sensitivity_labels),
        user_asserted=True,
        visibility=cast(Literal["private", "public", "shared"], source.visibility),
        preserved_evidence=list(source.evidence),
    )
    replacement_id = _row_id(uid, write)
    control = ensure_canonical_apply_control_state(
        uid,
        db_client=db_client,
    )
    receipt = MemoryLedgerReopenReceipt(
        uid=uid,
        source_memory_id=source.memory_id,
        replacement_memory_id=replacement_id,
        operation_id=operation_id,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        source_item_revision=source.item_revision,
        source_content_hash=source.content_hash or "",
    )
    # The row id is deterministic from the source and request action.  A
    # response lost after the transaction commits can therefore read back the
    # exact append before attempting another write.
    existing = read_canonical_memory_item(uid, replacement_id, db_client=db_client)
    if existing is not None:
        return replacement_id
    return save_ledger_write(
        uid,
        write,
        db_client=db_client,
        required_source_item=source,
        ledger_reopen_receipt=receipt,
        _direct_user_authority=_DIRECT_USER_AMEND_AUTHORITY,
    )


def amend_user_fact(
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
    visibility: Literal["private", "public", "shared"] = "private",
    db_client: Any = None,
    required_source_item: Optional[MemoryItem] = None,
) -> str:
    """Append a fact only through the explicit user correction/revert path."""

    if write_reason != LedgerWriteReason.direct_user_statement or provenance.source_type not in {
        "explicit_user_correction",
        "explicit_user_revert",
    }:
        raise ValueError("direct user amendments require correction or revert provenance")
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
            visibility=visibility,
            supersedes=[prior_memory_id],
        ),
        db_client=db_client,
        required_source_item=required_source_item,
        _direct_user_authority=_DIRECT_USER_AMEND_AUTHORITY,
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
    arguments: Optional[Dict[str, Any]] = None,
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
            arguments=arguments or {},
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
        and _is_review_visible(item)
        and item.valid_to is None
        and item.slot
        and (item.content or "").strip()
    ]
    return render_bounded_profile(eligible, character_budget=character_budget)


def render_playbook_index(
    items: Iterable[MemoryItem],
    *,
    character_budget: int = PLAYBOOK_INDEX_CHARACTER_BUDGET,
) -> str:
    """Render one-line progressive-disclosure handles, never playbook bodies."""
    active = [
        item
        for item in items
        if item.ledger_schema_version == LEDGER_SCHEMA_VERSION
        and item.kind == MemoryKind.document
        and item.subject_scope == MemorySubjectScope.primary_user
        and item.status == MemoryItemStatus.active
        and _is_review_visible(item)
        and item.valid_to is None
    ]
    active.sort(key=lambda item: (-(item.curation_weight), item.content or "", item.memory_id))
    lines: List[str] = []
    used = 0
    for item in active:
        description = normalize_playbook_handle(item.content)[:PLAYBOOK_HANDLE_CHARACTER_LIMIT]
        if not description:
            continue
        line = f"{item.memory_id}: {description}"
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
    "amend_user_fact",
    "close_fact",
    "create_trigger",
    "evidence_id_for_ledger_provenance",
    "read_playbook",
    "render_playbook_index",
    "render_profile",
    "reopen_standalone_fact",
    "save_fact",
    "save_ledger_write",
    "write_playbook",
]
