"""Deterministic legacy disposition apply for retention and owed intake; no model planner."""

from __future__ import annotations
from datetime import datetime
from dataclasses import dataclass, field
from google.cloud.firestore_v1 import FieldFilter, transactional
from database.firestore_index_registry import CANONICAL_CONSOLIDATION_QUERY
from database.memory_collections import MemoryCollections
from database.read_boundary import parse_snapshot_strict
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from models.memory_admission import valid_required_processing_receipt
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from database.memory_apply_store import apply_long_term_patch_firestore
from models.memory_evidence import SourceState
from models.memory_apply import ApplyStatus, MemoryControlState, build_patch_mutation_identity, memory_content_hash
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.memory_promotion import PromotionGraphPlan, build_promotion_admission_receipt
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.log_sanitizer import sanitize_pii
from utils.memory.memory_system import ensure_canonical_apply_control_state
from utils.memory.canonical_required_processing import (
    ProcessedRequiredMemory,
    commit_required_processing,
    is_pending_required_processing,
)
from utils.memory.belief_model import HALF_LIFE_DAYS_BY_CLASS, belief_model_enabled

CONSOLIDATION_BY = "canonical_batched_consolidation"


Payload = Dict[str, Any]


def _read_control_state(uid: str, *, db_client: Any) -> MemoryControlState:
    return ensure_canonical_apply_control_state(uid, db_client=db_client)


class ConsolidationAgentDecision(BaseModel):
    """One total, item-addressed L2 route for a pending Short-term memory."""

    source_memory_id: str = Field(description="Pending memory_id this decision settles")
    route: Literal["promote", "archive", "review", "reject"]
    reconciliation: Literal["create", "replace", "merge", "duplicate", "keep_both"] = "create"
    target_memory_id: Optional[str] = Field(
        default=None,
        description="Existing memory used for duplicate/replace/merge reasoning",
    )
    supersedes: List[str] = Field(default_factory=list, description="Active memory_ids replaced by this source")
    memory_text: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    subject_entity_id: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    relationship_to_user: Literal[
        "self",
        "owned_work",
        "adopted",
        "asking_about",
        "encountered",
        "other_speaker",
        "unclear",
    ] = "unclear"
    aboutness: Literal[
        "primary_user",
        "user_owned_project",
        "user_relationship",
        "third_party",
        "unclear",
    ] = "unclear"
    basis_for_memory: Literal["explicit", "recurring", "inferred_pattern", "weak_or_none"] = "weak_or_none"
    confidence: Literal["high", "medium", "low"] = "medium"
    rationale: str = ""

    @model_validator(mode="after")
    def validate_route(self):
        if not self.source_memory_id.strip():
            raise ValueError("source_memory_id is required")
        self.supersedes = sorted({value.strip() for value in self.supersedes if value and value.strip()})
        if self.source_memory_id in self.supersedes:
            raise ValueError("a promotion cannot supersede its source item")
        if self.target_memory_id == self.source_memory_id:
            raise ValueError("target_memory_id cannot point to the source item")
        if self.reconciliation in {"replace", "merge", "duplicate"} and not self.target_memory_id:
            raise ValueError("replace/merge/duplicate requires target_memory_id")
        if self.route == "promote":
            if not (self.memory_text or "").strip():
                raise ValueError("promote requires memory_text")
            if not self.evidence_ids:
                raise ValueError("promote requires exact evidence_ids")
            PromotionGraphPlan(
                subject_entity_id=self.subject_entity_id or "",
                predicate=self.predicate or "",
                arguments=self.arguments,
            )
            if self.basis_for_memory == "weak_or_none":
                raise ValueError("promote requires a defensible relationship-to-user basis")
            if self.reconciliation == "duplicate":
                raise ValueError("duplicate observations must not be promoted")
            if self.reconciliation in {"replace", "merge"} and self.target_memory_id not in self.supersedes:
                raise ValueError("replace/merge promotion must supersede its target_memory_id")
            if self.reconciliation in {"create", "keep_both"} and self.supersedes:
                raise ValueError("create/keep_both promotion cannot supersede existing memories")
        elif self.supersedes:
            raise ValueError("only promote routes may supersede active memories")
        return self


class ConsolidationApplySkipped(Exception):
    """A route could not be safely validated or committed."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _consolidation_decision_identity(
    *,
    uid: str,
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
    quarantine: bool = False,
) -> Payload:
    """Stable consolidation identity for idempotency across maintenance passes."""
    return {
        "uid": uid,
        "source_memory_id": source.memory_id,
        "source_item_revision": source.item_revision,
        "source_content_hash": source.content_hash,
        "decision": decision.model_dump(mode="json"),
        "quarantine": quarantine,
    }


def _ordered_route_evidence_ids(
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
) -> List[str]:
    requested = set(decision.evidence_ids)
    if decision.route != "promote":
        requested = {evidence.evidence_id for evidence in source.evidence}
    ordered = [evidence.evidence_id for evidence in source.evidence if evidence.evidence_id in requested]
    if not ordered:
        raise ConsolidationApplySkipped(f"route has no active source evidence: {source.memory_id}")
    if set(ordered) != requested:
        raise ConsolidationApplySkipped(f"route evidence changed after planning: {source.memory_id}")
    return ordered


def _route_result_status(decision: ConsolidationAgentDecision) -> LifecycleState:
    if decision.route == "reject" and not belief_model_enabled():
        return LifecycleState.hidden
    return LifecycleState.active


def _route_target_tier(decision: ConsolidationAgentDecision, *, quarantine: bool) -> MemoryLayer:
    # explicit_archive_memory: non-durable L2 outcomes are retained only outside default reads.
    if quarantine:
        return MemoryLayer.short_term
    return MemoryLayer.long_term if decision.route == "promote" else MemoryLayer.archive


def _route_logical_payload(
    *,
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
    quarantine: bool,
) -> Payload:
    promote = decision.route == "promote"
    return {
        "decision": DurablePatchDecision.update.value,
        "target_memory_id": source.memory_id,
        "memory_text": decision.memory_text if promote else None,
        "result_status": _route_result_status(decision).value,
        "supersedes": sorted(decision.supersedes),
        "subject_entity_id": decision.subject_entity_id if promote else None,
        "predicate": decision.predicate if promote else None,
        "arguments": decision.arguments if promote else {},
        "target_tier": _route_target_tier(decision, quarantine=quarantine).value,
    }


def _new_consolidation_operation(
    *,
    uid: str,
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
    control: MemoryControlState,
    evidence_ids: List[str],
    logical_payload: Payload,
    quarantine: bool,
) -> MemoryOperation:
    source_packet_id = deterministic_contract_id(
        "canonical-promotion-route",
        _consolidation_decision_identity(
            uid=uid,
            source=source,
            decision=decision,
            quarantine=quarantine,
        ),
    )
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.synthesis,
        source_packet_id=source_packet_id,
        target_memory_id=source.memory_id,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    return operation


def _promotion_audit(
    *,
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
    evidence_ids: List[str],
    now: datetime,
    quarantine: bool,
) -> Payload:
    audit: Payload = {
        **(source.promotion or {}),
        "route": decision.route,
        "reconciliation": decision.reconciliation,
        "target_memory_id": decision.target_memory_id,
        "relationship_to_user": decision.relationship_to_user,
        "aboutness": decision.aboutness,
        "basis_for_memory": decision.basis_for_memory,
        "confidence": decision.confidence,
        "rationale": sanitize_pii(decision.rationale or "")[:500],
        "processing_status": "processing_blocked" if quarantine else "processed",
        "processed_at": now,
        "processed_by": CONSOLIDATION_BY,
    }
    if decision.route != "promote":
        return audit

    graph_plan = PromotionGraphPlan(
        subject_entity_id=decision.subject_entity_id or "",
        predicate=decision.predicate or "",
        arguments=decision.arguments,
    )
    output_hash = memory_content_hash(
        content=decision.memory_text,
        evidence_ids=evidence_ids,
    )
    receipt = build_promotion_admission_receipt(
        memory_id=source.memory_id,
        source_item_revision=source.item_revision,
        output_content_hash=output_hash,
        evidence_ids=evidence_ids,
        graph_plan=graph_plan,
        supersedes=decision.supersedes,
    )
    audit.update(
        {
            "from_tier": MemoryLayer.short_term.value,
            "to_tier": MemoryLayer.long_term.value,
            "promoted_at": now,
            "graph_plan": graph_plan.model_dump(mode="json"),
            "admission_receipt": receipt.model_dump(mode="json"),
        }
    )
    return audit


def _processed_from_consolidation_decision(
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
) -> ProcessedRequiredMemory:
    content = (decision.memory_text or source.content or "").strip()
    if not content:
        raise ConsolidationApplySkipped(f"required source has no normalizable content: {source.memory_id}")
    predicate = (decision.predicate or source.predicate or "remembered_fact").strip()
    subject = (decision.subject_entity_id or source.subject_entity_id or "user").strip()
    try:
        return ProcessedRequiredMemory(
            content=content[:1000],
            subject_entity_id=subject,
            predicate=predicate,
            arguments=dict(decision.arguments or source.arguments or {}),
            sensitivity_labels=list(source.sensitivity_labels or []),
            rationale=(decision.rationale or "normalized during consolidation")[:500],
        )
    except Exception as exc:
        raise ConsolidationApplySkipped(
            f"required source could not be normalized from the consolidation decision: {source.memory_id}"
        ) from exc


def _bind_required_promote_memory_text(
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
) -> ConsolidationAgentDecision:
    """Keep promote text identical to L2 content so INV-MEM-4 receipt hashes match.

    L2 commit and the promote patch are separate ledger applies. After a successful
    L2 write the item is already processed with ``required=True``; a later pass or
    mixed batch must still bind ``memory_text`` to that stored content, not a
    rewritten planner string.
    """
    if decision.route != "promote":
        return decision
    if not (source.promotion or {}).get("required"):
        return decision
    return decision.model_copy(update={"memory_text": source.content})


def apply_consolidation_decision(
    uid: str,
    *,
    decision: ConsolidationAgentDecision,
    pending_by_id: Dict[str, MemoryItem],
    control: MemoryControlState,
    run_id: str,
    now: datetime,
    db_client: Any,
    quarantine: bool = False,
) -> List[str]:
    """Atomically settle one source item, including LT graph assertion/supersedes."""
    source = pending_by_id.get(decision.source_memory_id)
    if source is None:
        raise ConsolidationApplySkipped(f"missing pending source: {decision.source_memory_id}")
    if is_pending_required_processing(source):
        processed = _processed_from_consolidation_decision(source, decision)
        try:
            source = commit_required_processing(source, processed, db_client=db_client, now=now)
        except Exception as exc:
            raise ConsolidationApplySkipped(
                f"required processing apply failed for {decision.source_memory_id}"
            ) from exc
        pending_by_id[source.memory_id] = source
        control = _read_control_state(uid, db_client=db_client)
    decision = _bind_required_promote_memory_text(source, decision)
    if (
        source.tier != MemoryLayer.short_term
        or source.status != MemoryItemStatus.active
        or source.processing_state != ProcessingState.processed
        or source.source_state != SourceState.active
    ):
        raise ConsolidationApplySkipped(f"source is no longer promotable: {source.memory_id}")

    evidence_ids = _ordered_route_evidence_ids(source, decision)
    idempotency_key = deterministic_contract_id(
        "canonical-promotion-route",
        _consolidation_decision_identity(
            uid=uid,
            source=source,
            decision=decision,
            quarantine=quarantine,
        ),
    )
    logical_payload = _route_logical_payload(
        source=source,
        decision=decision,
        quarantine=quarantine,
    )
    patch_payload: Dict[str, Any] = {
        "patch_id": f"patch_cons_{idempotency_key[:24]}",
        "packet_id": f"consolidation_{run_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        **logical_payload,
        "evidence_ids": evidence_ids,
        "expected_item_revision": source.item_revision,
        "expected_content_hash": source.content_hash,
        "promotion_audit": _promotion_audit(
            source=source,
            decision=decision,
            evidence_ids=evidence_ids,
            now=now,
            quarantine=quarantine,
        ),
    }
    if belief_model_enabled() and decision.route == "reject":
        carried = getattr(decision, "belief_class", None)
        patch_payload["belief_class"] = carried if carried in HALF_LIFE_DAYS_BY_CLASS else "meta_residue"
    mutation_identity = build_patch_mutation_identity(patch_payload)
    patch_payload["mutation_metadata"] = mutation_identity
    logical_payload["mutation_metadata"] = mutation_identity
    operation = _new_consolidation_operation(
        uid=uid,
        source=source,
        decision=decision,
        control=control,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        quarantine=quarantine,
    )

    result = None
    for _attempt in range(3):
        result = apply_long_term_patch_firestore(
            uid=uid,
            operation_id=operation.operation_id,
            patch_payload=patch_payload,
            proposed_operation=operation,
            db_client=db_client,
        )
        if result.status != ApplyStatus.retryable_head_mismatch:
            break
    assert result is not None
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise ConsolidationApplySkipped(
            f"promotion route failed for {source.memory_id}: {result.status} ({result.reason})"
        )
    return [source.memory_id, *decision.supersedes]


@dataclass
class RequiredIntakeCompletion:
    uid: str
    promoted_memory_ids: list[str] = field(default_factory=list)
    failed_memory_ids: list[str] = field(default_factory=list)


def _required_intake_page(uid, *, db_client, cursor=None):
    """Bounded processed-intake query with stable capture/id pagination."""
    cursor = cursor or {}
    query = (
        CANONICAL_CONSOLIDATION_QUERY.build(
            db_client.collection(MemoryCollections(uid=uid).memory_items),
            {
                'tier': MemoryLayer.short_term.value,
                'status': MemoryItemStatus.active.value,
                'processing_state': ProcessingState.processed.value,
                'source_state': SourceState.active.value,
            },
            field_filter_factory=FieldFilter,
        )
        .order_by('captured_at')
        .order_by('memory_id')
    )
    active_query = query
    if cursor.get('captured_at') is not None:
        if not isinstance(cursor['captured_at'], datetime) or not isinstance(cursor.get('memory_id'), str):
            raise ValueError('Required intake cursor is invalid')
        active_query = query.start_after({'captured_at': cursor['captured_at'], 'memory_id': cursor['memory_id']})
    snapshots = list(active_query.limit(100).stream())
    if not snapshots and cursor:
        snapshots = list(query.limit(100).stream())
    return snapshots


def complete_required_intake(uid, *, db_client, now, run_id, limit=25, job_budget_guard=None):
    """Complete receipted durable-required intake, with no cleanup model.

    A rotating bounded cursor skips ordinary observations without starving
    explicit submissions behind them. Existing facts are never candidates.
    Every disposition retains the existing revision, source, generation and
    graph-admission transaction fences and durable projection outbox.
    """
    report = RequiredIntakeCompletion(uid=uid)
    if limit <= 0:
        return report
    cursor_ref = db_client.document(f'{MemoryCollections(uid=uid).memory_runs}/required_intake_cursor')
    cursor = cursor_ref.get().to_dict() or {}
    snapshots = _required_intake_page(uid, db_client=db_client, cursor=cursor)
    visited = None
    for snapshot in snapshots:
        if len(report.promoted_memory_ids) + len(report.failed_memory_ids) >= min(25, limit):
            break
        if job_budget_guard is not None:
            job_budget_guard()
        item = parse_snapshot_strict(MemoryItem, snapshot)
        if item.uid != uid:
            raise ValueError('Required intake owner mismatch')
        visited = {'captured_at': item.captured_at, 'memory_id': item.memory_id}
        audit = item.promotion or {}
        if not audit.get('required') or audit.get('processing_status') != 'processed':
            continue
        if not valid_required_processing_receipt(
            content=item.content or '', item_revision=item.item_revision, promotion=audit
        ):
            continue
        decision = ConsolidationAgentDecision(
            source_memory_id=item.memory_id,
            route='promote',
            memory_text=item.content,
            evidence_ids=[e.evidence_id for e in item.evidence],
            subject_entity_id=item.subject_entity_id,
            predicate=item.predicate,
            arguments=item.arguments,
            basis_for_memory='explicit',
            confidence='high',
            rationale='Complete receipted durable-required intake',
        )
        try:
            apply_consolidation_decision(
                uid,
                decision=decision,
                pending_by_id={item.memory_id: item},
                control=_read_control_state(uid, db_client=db_client),
                run_id=run_id,
                now=now,
                db_client=db_client,
            )
            report.promoted_memory_ids.append(item.memory_id)
        except ConsolidationApplySkipped:
            report.failed_memory_ids.append(item.memory_id)
    if visited is not None:

        @transactional
        def save_cursor(tx):
            current = cursor_ref.get(transaction=tx).to_dict() or {}
            if current != cursor:
                raise RuntimeError('Required intake cursor changed')
            tx.set(cursor_ref, visited)

        run_with_transaction_contention_retry(
            db_client.transaction, save_cursor, operation_name='required_intake_cursor'
        )
    return report
