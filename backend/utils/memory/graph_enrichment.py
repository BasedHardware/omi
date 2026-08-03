"""Canonical-apply-only graph enrichment contracts.

Planning may happen outside this module (including an LLM), but this module
accepts only a typed plan and an authoritative ``MemoryItem`` snapshot.  It
never writes graph documents directly and never parses model output.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.memory_apply import build_patch_mutation_identity
from models.memory_admission import valid_required_processing_receipt
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_migration import MigrationBlockCode
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.memory_promotion import PROMOTION_GRAPH_PLAN_VERSION, PromotionGraphPlan
from models.memory_promotion import MemoryGraphAssertion
from models.memory_evidence import SourceState
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    MemoryItem,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
)

SNAKE_CASE_PREDICATE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
GRAPH_ENRICHMENT_PLAN_VERSION = "canonical_memory_graph_enrichment_plan.v1"
GRAPH_ENRICHMENT_RECEIPT_VERSION = "canonical_memory_graph_enrichment_receipt.v1"


class GraphEnrichmentError(ValueError):
    """Typed validation failure; no apply should be attempted."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class GraphEnrichmentStatus(str, Enum):
    ready = "ready"
    already_enriched = "already_enriched"
    blocked = "blocked"


class GraphEnrichmentPlan(BaseModel):
    """Server-validated deterministic graph plan, not a raw LLM response."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["canonical_memory_graph_enrichment_plan.v1"] = GRAPH_ENRICHMENT_PLAN_VERSION
    subject_entity_id: str
    predicate: str
    arguments: Dict[str, Any]
    plan_hash: str = ""

    @field_validator("subject_entity_id")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("graph enrichment subject must not be blank")
        return value.strip()

    @field_validator("predicate")
    @classmethod
    def validate_predicate(cls, value: str) -> str:
        value = value.strip()
        if not SNAKE_CASE_PREDICATE.fullmatch(value):
            raise ValueError("graph enrichment predicate must be lower snake_case")
        return value

    @model_validator(mode="after")
    def normalize_and_hash(self) -> "GraphEnrichmentPlan":
        try:
            validated = PromotionGraphPlan(
                schema_version=PROMOTION_GRAPH_PLAN_VERSION,
                subject_entity_id=self.subject_entity_id,
                predicate=self.predicate,
                arguments=self.arguments,
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        self.arguments = validated.arguments
        # The canonical assertion builder consumes ``PromotionGraphPlan``;
        # share its hash namespace so the receipt, item promotion, and final
        # assertion all bind to one deterministic plan identity.
        expected = validated.plan_hash
        if self.plan_hash and self.plan_hash != expected:
            raise ValueError("graph enrichment plan hash mismatch")
        self.plan_hash = expected
        return self

    def promotion_plan(self) -> PromotionGraphPlan:
        return PromotionGraphPlan(
            subject_entity_id=self.subject_entity_id,
            predicate=self.predicate,
            arguments=self.arguments,
        )


class GraphEnrichmentReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["canonical_memory_graph_enrichment_receipt.v1"] = GRAPH_ENRICHMENT_RECEIPT_VERSION
    receipt_id: str = ""
    uid: str
    memory_id: str
    item_revision: int
    content_hash: str
    evidence_ids: List[str]
    account_generation: int
    source_generation: int
    plan_hash: str

    @field_validator("uid", "memory_id", "content_hash", "plan_hash")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("graph enrichment receipt identity must not be blank")
        return value.strip()

    @field_validator("item_revision", "account_generation", "source_generation")
    @classmethod
    def validate_counters(cls, value: int) -> int:
        if value < 0:
            raise ValueError("graph enrichment receipt counters must be nonnegative")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence(cls, value: List[str]) -> List[str]:
        normalized = sorted({item.strip() for item in value if item and item.strip()})
        if not normalized:
            raise ValueError("graph enrichment receipt requires evidence")
        return normalized

    @model_validator(mode="after")
    def derive_receipt_id(self) -> "GraphEnrichmentReceipt":
        expected = (
            "ger_"
            + deterministic_contract_id(
                "canonical-memory-graph-enrichment-receipt",
                {
                    "schema_version": self.schema_version,
                    "uid": self.uid,
                    "memory_id": self.memory_id,
                    "item_revision": self.item_revision,
                    "content_hash": self.content_hash,
                    "evidence_ids": self.evidence_ids,
                    "account_generation": self.account_generation,
                    "source_generation": self.source_generation,
                    "plan_hash": self.plan_hash,
                },
            )[:32]
        )
        if self.receipt_id and self.receipt_id != expected:
            raise ValueError("graph enrichment receipt id mismatch")
        self.receipt_id = expected
        return self


class GraphEnrichmentResult(BaseModel):
    status: GraphEnrichmentStatus
    plan: Optional[GraphEnrichmentPlan] = None
    receipt: Optional[GraphEnrichmentReceipt] = None
    operation: Optional[MemoryOperation] = None
    patch_payload: Dict[str, Any] = Field(default_factory=dict)
    block_code: Optional[str] = None
    reason: Optional[str] = None


def _blocked(code: str, reason: str) -> GraphEnrichmentResult:
    return GraphEnrichmentResult(status=GraphEnrichmentStatus.blocked, block_code=code, reason=reason)


def _coerce_plan(plan: GraphEnrichmentPlan | PromotionGraphPlan | Dict[str, Any]) -> GraphEnrichmentPlan:
    if isinstance(plan, GraphEnrichmentPlan):
        return plan
    if isinstance(plan, PromotionGraphPlan):
        return GraphEnrichmentPlan(
            subject_entity_id=plan.subject_entity_id,
            predicate=plan.predicate,
            arguments=plan.arguments,
        )
    try:
        return GraphEnrichmentPlan.model_validate(plan)
    except Exception as exc:
        raise GraphEnrichmentError("graph_plan_invalid", "graph enrichment plan is malformed") from exc


def _current_evidence_ids(item: MemoryItem) -> List[str]:
    evidence = item.evidence
    if not evidence:
        raise GraphEnrichmentError("evidence_missing", "graph enrichment requires at least one evidence record")
    ids: List[str] = []
    active_count = 0
    for record in evidence:
        evidence_id = getattr(record, "evidence_id", None)
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise GraphEnrichmentError("evidence_malformed", "graph enrichment evidence identity is malformed")
        evidence_id = evidence_id.strip()
        if evidence_id in ids:
            raise GraphEnrichmentError("duplicate_evidence", "graph enrichment evidence ids must be unique")
        ids.append(evidence_id)
        if getattr(record, "source_state", None) == SourceState.active:
            active_count += 1
    if active_count == 0 and not item.user_asserted:
        raise GraphEnrichmentError("evidence_not_active", "graph enrichment requires active evidence")
    return sorted(ids)


def _assertion_matches_current_item(
    *, item: MemoryItem, assertion: Any, evidence_ids: List[str], plan: GraphEnrichmentPlan
) -> bool:
    if assertion is None:
        return False
    if isinstance(assertion, dict):
        value = assertion.get
    else:
        value = lambda key, default=None: getattr(assertion, key, default)
    return (
        value("status", "active") == "active"
        and value("uid") == item.uid
        and value("memory_id") == item.memory_id
        and value("assertion_id") == item.graph_assertion_id
        and value("item_revision") == item.item_revision
        and value("content_hash") == item.content_hash
        and sorted(set(value("evidence_ids", []) or [])) == evidence_ids
        and value("graph_plan_hash") == plan.plan_hash
        and value("subject_entity_id") == plan.subject_entity_id
        and value("predicate") == plan.predicate
        and value("arguments") == plan.arguments
    )


def prepare_graph_enrichment(
    *,
    item: MemoryItem,
    plan: GraphEnrichmentPlan | PromotionGraphPlan | Dict[str, Any],
    account_generation: int,
    source_generation: int,
    expected_item_revision: Optional[int] = None,
    expected_content_hash: Optional[str] = None,
    expected_evidence_ids: Optional[List[str]] = None,
    observed_head_commit_id: Optional[str] = None,
    existing_graph_assertion: Optional[MemoryGraphAssertion | Dict[str, Any]] = None,
) -> GraphEnrichmentResult:
    """Validate a graph plan and build a canonical apply operation/payload.

    This function is pure.  A caller must submit the returned operation and
    payload to ``apply_long_term_patch_firestore``; writing an assertion or
    mutating a ``MemoryItem`` directly is intentionally unsupported.
    """
    if (
        item.status != MemoryItemStatus.active
        or item.tier != MemoryTier.long_term
        or item.source_state != SourceState.active
    ):
        return _blocked("target_not_active_long_term", "graph enrichment requires an active Long-term item")
    if item.processing_state != ProcessingState.processed:
        return _blocked("processing_not_complete", "graph enrichment requires processing_state=processed")
    if item.sensitivity_labels and set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS):
        return _blocked(MigrationBlockCode.restricted_item.value, "restricted memory items cannot be graph enriched")
    if (item.promotion or {}).get("user_review") is False:
        return _blocked(
            MigrationBlockCode.review_rejected.value, "review-rejected memory items cannot be graph enriched"
        )
    promotion = item.promotion or {}
    if promotion.get("required") and not valid_required_processing_receipt(
        content=item.content or "", item_revision=item.item_revision, promotion=promotion
    ):
        return _blocked(
            MigrationBlockCode.missing_required_processing_receipt.value,
            "required processing receipt is missing or stale; graph enrichment cannot fabricate one",
        )
    if expected_item_revision is not None and item.item_revision != expected_item_revision:
        return _blocked(MigrationBlockCode.stale_fence.value, "item revision fence does not match current item")
    if expected_content_hash is not None and item.content_hash != expected_content_hash:
        return _blocked(MigrationBlockCode.stale_fence.value, "content hash fence does not match current item")
    if not item.content_hash or not item.content_hash.strip():
        return _blocked("content_hash_missing", "graph enrichment requires a current content hash")
    try:
        evidence_ids = _current_evidence_ids(item)
    except GraphEnrichmentError as exc:
        return _blocked(exc.code, exc.message)
    if expected_evidence_ids is not None and evidence_ids != sorted(set(expected_evidence_ids)):
        return _blocked(MigrationBlockCode.stale_fence.value, "evidence fence does not match current item")
    if item.account_generation != account_generation:
        return _blocked(MigrationBlockCode.stale_fence.value, "account generation fence does not match current item")
    try:
        checked_plan = _coerce_plan(plan)
    except GraphEnrichmentError as exc:
        return _blocked(exc.code, exc.message)
    if item.graph_ready:
        try:
            current_plan = _coerce_plan((item.promotion or {}).get("graph_plan", {}))
        except GraphEnrichmentError as exc:
            return _blocked("graph_assertion_invalid", "graph_ready item has no valid current graph plan")
        if current_plan.plan_hash != checked_plan.plan_hash or not _assertion_matches_current_item(
            item=item, assertion=existing_graph_assertion, evidence_ids=evidence_ids, plan=current_plan
        ):
            return _blocked("graph_assertion_invalid", "graph_ready item lacks an exact current graph assertion")
        return GraphEnrichmentResult(status=GraphEnrichmentStatus.already_enriched, plan=current_plan)
    if not item.subject_entity_id or checked_plan.subject_entity_id != item.subject_entity_id:
        return _blocked("subject_overwrite", "graph enrichment cannot overwrite or invent the existing subject")
    receipt = GraphEnrichmentReceipt(
        uid=item.uid,
        memory_id=item.memory_id,
        item_revision=item.item_revision,
        content_hash=item.content_hash or "",
        evidence_ids=evidence_ids,
        account_generation=account_generation,
        source_generation=source_generation,
        plan_hash=checked_plan.plan_hash,
    )
    promotion = dict(item.promotion or {})
    promotion.update(
        {
            "graph_plan": checked_plan.promotion_plan().model_dump(mode="json"),
            "graph_enrichment_receipt": receipt.model_dump(mode="json"),
            "graph_enrichment": True,
        }
    )
    patch_payload: Dict[str, Any] = {
        "patch_id": f"patch_{receipt.receipt_id}",
        "packet_id": f"graph_enrichment:{item.memory_id}:{item.item_revision}",
        "run_id": f"graph_enrichment:{receipt.receipt_id}",
        "observed_head_commit_id": observed_head_commit_id,
        "idempotency_key": receipt.receipt_id,
        "decision": DurablePatchDecision.update.value,
        "result_status": LifecycleState.active.value,
        "target_memory_id": item.memory_id,
        "evidence_ids": evidence_ids,
        "subject_entity_id": checked_plan.subject_entity_id,
        "predicate": checked_plan.predicate,
        "arguments": checked_plan.arguments,
        "existing_item": item.model_dump(mode="python"),
        "expected_item_revision": item.item_revision,
        "expected_content_hash": item.content_hash,
        "promotion_audit": promotion,
        "mutation_metadata": {},
    }
    patch_payload["mutation_metadata"] = build_patch_mutation_identity(patch_payload)
    logical_payload = {
        "decision": DurablePatchDecision.update.value,
        "target_memory_id": item.memory_id,
        "result_status": LifecycleState.active.value,
        "subject_entity_id": checked_plan.subject_entity_id,
        "predicate": checked_plan.predicate,
        "arguments": checked_plan.arguments,
        "mutation_metadata": patch_payload["mutation_metadata"],
    }
    operation = MemoryOperation.new(
        uid=item.uid,
        operation_type=MemoryOperationType.graph_enrichment,
        source_packet_id=patch_payload["packet_id"],
        target_memory_id=item.memory_id,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        account_generation=account_generation,
        source_generation=source_generation,
        observed_head_commit_id=observed_head_commit_id,
    )
    return GraphEnrichmentResult(
        status=GraphEnrichmentStatus.ready,
        plan=checked_plan,
        receipt=receipt,
        operation=operation,
        patch_payload=patch_payload,
    )


def validate_graph_enrichment(**kwargs: Any) -> GraphEnrichmentResult:
    return prepare_graph_enrichment(**kwargs)


__all__ = [
    "GRAPH_ENRICHMENT_PLAN_VERSION",
    "GRAPH_ENRICHMENT_RECEIPT_VERSION",
    "GraphEnrichmentError",
    "GraphEnrichmentPlan",
    "GraphEnrichmentReceipt",
    "GraphEnrichmentResult",
    "GraphEnrichmentStatus",
    "SNAKE_CASE_PREDICATE",
    "prepare_graph_enrichment",
    "validate_graph_enrichment",
]
