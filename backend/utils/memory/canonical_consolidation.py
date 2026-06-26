"""Canonical batched short-term consolidation (WS-O).

Deterministic code retrieves candidates, hydrates active memory_items, and assembles
LLM context. A single batched LLM agent is the sole decider of consolidation outcomes;
decisions are applied via ``apply_long_term_patch_firestore``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Literal, Optional, Set

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from database._client import db as default_db_client
from database.memory_apply_store import apply_long_term_patch_firestore
from database.memory_collections import MemoryCollections
from database.review_queue import create_review_conflict, should_escalate_conflict
from database.vector_db import query_memory_vector_candidates
from jobs.short_term_lifecycle_worker import fetch_short_term_memory_items_firestore
from models.memory_evidence import SourceState
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.memory_search_gateway import SearchMode
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.llm.clients import get_llm
from utils.log_sanitizer import sanitize_pii
from utils.memory.atom_keyword_index import delete_atom_keyword_doc
from utils.memory.canonical_memory_adapter import invalidate_kg_for_memory_retraction
from utils.memory.canonical_vector_sync import delete_canonical_memory_vector
from utils.memory.memory_system import MemorySystem, resolve_memory_system

logger = logging.getLogger(__name__)

CONSOLIDATION_BY = "canonical_batched_consolidation"
DEFAULT_CONSOLIDATION_BATCH_THRESHOLD = 10
DEFAULT_CANDIDATES_PER_ITEM = 8
CONSOLIDATION_DAILY_INTERVAL = timedelta(hours=24)

MEMORY_CANONICAL_CONSOLIDATION_ENABLED_ENV = "MEMORY_CANONICAL_CONSOLIDATION_ENABLED"


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _read_control_state(uid: str, *, db_client) -> MemoryControlState:
    collections = MemoryCollections(uid=uid)
    ref = db_client.document(collections.memory_control_state)
    snapshot = ref.get()
    if getattr(snapshot, "exists", False):
        return MemoryControlState(**(snapshot.to_dict() or {}))
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    ref.set(control.model_dump(mode="json"))
    return control


def _persist_control_state(control: MemoryControlState, *, db_client) -> None:
    db_client.document(MemoryCollections(uid=control.uid).memory_control_state).set(control.model_dump(mode="json"))


def _is_promotable_for_consolidation(item: MemoryItem, *, now: datetime) -> bool:
    current_time = _coerce_aware_utc(now)
    if item.tier != MemoryLayer.short_term:
        return False
    if item.status != MemoryItemStatus.active:
        return False
    if item.processing_state != ProcessingState.processed:
        return False
    if item.source_state != SourceState.active:
        return False
    if item.expires_at is not None and item.expires_at <= current_time:
        return False
    return True


def consolidation_enabled() -> bool:
    raw = os.getenv(MEMORY_CANONICAL_CONSOLIDATION_ENABLED_ENV, "true")
    return raw.lower() == "true"


def consolidation_batch_threshold() -> int:
    raw = os.getenv("MEMORY_CANONICAL_CONSOLIDATION_BATCH_THRESHOLD", str(DEFAULT_CONSOLIDATION_BATCH_THRESHOLD))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_CONSOLIDATION_BATCH_THRESHOLD


def candidates_per_item_limit() -> int:
    raw = os.getenv("MEMORY_CANONICAL_CONSOLIDATION_CANDIDATES_PER_ITEM", str(DEFAULT_CANDIDATES_PER_ITEM))
    try:
        return max(1, min(20, int(raw)))
    except ValueError:
        return DEFAULT_CANDIDATES_PER_ITEM


def _is_active_consolidation_item(item: MemoryItem) -> bool:
    return item.status == MemoryItemStatus.active and item.processing_state == ProcessingState.processed


def list_pending_consolidation_items(
    uid: str,
    *,
    db_client=None,
    now: Optional[datetime] = None,
) -> List[MemoryItem]:
    """Active processed short_term items eligible for batched consolidation."""
    client = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    items = fetch_short_term_memory_items_firestore(uid=uid, db_client=client)
    pending = [
        item
        for item in items
        if _is_active_consolidation_item(item) and _is_promotable_for_consolidation(item, now=current_time)
    ]
    return sorted(pending, key=lambda item: item.captured_at)


def consolidation_trigger_reason(
    *,
    pending_count: int,
    last_consolidation_run_at: Optional[datetime],
    now: datetime,
    batch_threshold: Optional[int] = None,
) -> Optional[str]:
    if pending_count <= 0:
        return None
    threshold = batch_threshold if batch_threshold is not None else consolidation_batch_threshold()
    if pending_count >= threshold:
        return "batch_threshold"
    if pending_count <= 1:
        return None
    if last_consolidation_run_at is None:
        return None
    current_time = _coerce_aware_utc(now)
    if current_time - _coerce_aware_utc(last_consolidation_run_at) >= CONSOLIDATION_DAILY_INTERVAL:
        return "daily_elapsed"
    return None


@dataclass(frozen=True)
class ConsolidationCandidate:
    anchor_memory_id: str
    memory_id: str
    content: str
    score: float
    tier: str
    captured_at: str


@dataclass
class ConsolidationContext:
    uid: str
    pending_items: List[MemoryItem]
    candidates_by_anchor: Dict[str, List[ConsolidationCandidate]] = field(default_factory=dict)

    @property
    def hydrated_memory_ids(self) -> Set[str]:
        ids: Set[str] = {item.memory_id for item in self.pending_items}
        for candidates in self.candidates_by_anchor.values():
            for candidate in candidates:
                ids.add(candidate.memory_id)
        return ids


def _hydrate_memory_item(
    uid: str, memory_id: str, *, db_client, cache: Dict[str, Optional[MemoryItem]]
) -> Optional[MemoryItem]:
    if memory_id in cache:
        return cache[memory_id]
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    snapshot = db_client.document(path).get()
    if not getattr(snapshot, "exists", False):
        cache[memory_id] = None
        return None
    item = MemoryItem(**(snapshot.to_dict() or {}))
    if not _is_active_consolidation_item(item):
        cache[memory_id] = None
        return None
    cache[memory_id] = item
    return item


def gather_consolidation_candidates(
    uid: str,
    pending_items: List[MemoryItem],
    *,
    db_client=None,
    candidate_limit: Optional[int] = None,
) -> ConsolidationContext:
    """Vector-search similar memories and hydrate active items (deterministic only)."""
    client = db_client if db_client is not None else default_db_client
    per_item = candidate_limit if candidate_limit is not None else candidates_per_item_limit()
    context = ConsolidationContext(uid=uid, pending_items=list(pending_items))
    cache: Dict[str, Optional[MemoryItem]] = {item.memory_id: item for item in pending_items}

    for anchor in pending_items:
        content = (anchor.content or "").strip()
        if not content:
            context.candidates_by_anchor[anchor.memory_id] = []
            continue
        query_result = query_memory_vector_candidates(uid, content, mode=SearchMode.default, limit=per_item + 1)
        candidates: List[ConsolidationCandidate] = []
        seen: Set[str] = set()
        for hit in query_result.hits:
            if hit.memory_id == anchor.memory_id or hit.memory_id in seen:
                continue
            item = _hydrate_memory_item(uid, hit.memory_id, db_client=client, cache=cache)
            if item is None:
                continue
            seen.add(hit.memory_id)
            candidates.append(
                ConsolidationCandidate(
                    anchor_memory_id=anchor.memory_id,
                    memory_id=item.memory_id,
                    content=item.content or "",
                    score=hit.score,
                    tier=item.tier.value,
                    captured_at=item.captured_at.isoformat(),
                )
            )
            if len(candidates) >= per_item:
                break
        context.candidates_by_anchor[anchor.memory_id] = candidates
    return context


def format_consolidation_llm_context(context: ConsolidationContext) -> str:
    """Serialize pending batch + vector candidates for the consolidation agent."""
    payload: Dict[str, Any] = {"memories": [], "candidate_groups": []}
    for item in context.pending_items:
        payload["memories"].append(
            {
                "memory_id": item.memory_id,
                "content": item.content,
                "tier": item.tier.value,
                "captured_at": item.captured_at.isoformat(),
                "evidence_source_ids": sorted({ev.source_id for ev in item.evidence if ev.source_id}),
                "corroboration_count": getattr(item, "corroboration_count", 0) or 0,
                "subject_entity_id": getattr(item, "subject_entity_id", None),
                "predicate": getattr(item, "predicate", None),
            }
        )
    for anchor_id, candidates in context.candidates_by_anchor.items():
        if not candidates:
            continue
        payload["candidate_groups"].append(
            {
                "anchor_memory_id": anchor_id,
                "candidates": [
                    {
                        "memory_id": c.memory_id,
                        "content": c.content,
                        "score": round(c.score, 4),
                        "tier": c.tier,
                        "captured_at": c.captured_at,
                    }
                    for c in candidates
                ],
            }
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class ConsolidationAgentDecision(BaseModel):
    decision: Literal[
        "update",
        "merge",
        "skip_duplicate",
        "add_evidence",
        "keep_both",
        "review",
    ]
    survivor_memory_id: str = Field(description="The memory_id that remains active after this decision")
    supersedes: List[str] = Field(default_factory=list, description="memory_ids to mark superseded")
    memory_text: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    corroboration_increment: bool = Field(
        default=False,
        description="When true, increment corroboration_count on survivor (duplicate/corroboration)",
    )
    review_required: bool = False
    conflict_with: List[str] = Field(default_factory=list)
    rationale: str = ""


class ConsolidationAgentBatch(BaseModel):
    decisions: List[ConsolidationAgentDecision] = Field(default_factory=list)
    reasoning: str = ""


CONSOLIDATION_AGENT_PROMPT = """You are Omi's canonical memory consolidation agent.

You receive a BATCH of short-term memories plus vector-similar candidates. Decide how
they relate: duplicate, merge, refine, contradict/supersede, corroborate, or coexist.

Rules:
- Reason over the WHOLE batch — not one pair at a time.
- Only supersede when a fact is genuinely outdated or false (not when two facts can coexist).
- Use skip_duplicate when a pending memory repeats an existing active fact.
- Use add_evidence or merge to combine near-duplicates across sources onto one survivor row.
- Use update when newer information replaces older (contradiction) — list outdated ids in supersedes.
- Use keep_both when facts are compatible and distinct.
- Set review_required=true for ambiguous contradictions (low confidence vs high-confidence existing).
- survivor_memory_id is the row that stays active; supersedes lists memory_ids to invalidate.
- Emit one decision per pending memory that needs action; omit memories that need no change.

Reference conflict-resolution patterns (adapt for batch reasoning):
- Preference flip (loves→hates): update, supersede old.
- Location change (NYC→LA): update, supersede old.
- Duplicate text: skip_duplicate on the newer id, survivor=existing.
- Compatible preferences (tennis + basketball): keep_both or no decision.
- Cross-source same fact: add_evidence or merge onto one survivor, corroboration_increment=true.

Batch JSON:
{context_json}

{format_instructions}
"""


def invoke_consolidation_agent(
    context: ConsolidationContext,
    *,
    llm_invoke: Optional[Callable[[str], str]] = None,
) -> ConsolidationAgentBatch:
    """Single batched LLM call — sole decider for consolidation outcomes."""
    parser = PydanticOutputParser(pydantic_object=ConsolidationAgentBatch)
    prompt = CONSOLIDATION_AGENT_PROMPT.format(
        context_json=format_consolidation_llm_context(context),
        format_instructions=parser.get_format_instructions(),
    )
    if llm_invoke is not None:
        raw = llm_invoke(prompt)
    else:
        response = get_llm("memory_conflict").invoke(prompt)
        raw = getattr(response, "content", str(response))
    try:
        return parser.parse(raw)
    except Exception as exc:
        logger.warning(
            "consolidation_agent_parse_failed uid=%s error=%s",
            context.uid,
            type(exc).__name__,
        )
        return ConsolidationAgentBatch(decisions=[], reasoning=f"parse_failed:{type(exc).__name__}")


def _dedupe_evidence_ids(*ids: str) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for evidence_id in ids:
        if evidence_id and evidence_id not in seen:
            seen.add(evidence_id)
            ordered.append(evidence_id)
    return ordered


def _ensure_consolidation_operation(
    *,
    uid: str,
    decision: ConsolidationAgentDecision,
    control: MemoryControlState,
    run_id: str,
    db_client,
) -> MemoryOperation:
    logical_payload = {
        "decision": decision.decision,
        "target_memory_id": decision.survivor_memory_id,
        "memory_text": decision.memory_text,
        "result_status": LifecycleState.active.value,
        "supersedes": sorted(decision.supersedes),
    }
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=f"consolidation_{run_id}",
        target_memory_id=decision.survivor_memory_id,
        evidence_ids=decision.evidence_ids,
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    op_path = f"{MemoryCollections(uid=uid).memory_operations}/{operation.operation_id}"
    op_ref = db_client.document(op_path)
    if not op_ref.get().exists:
        op_ref.set(operation.model_dump(mode="json"))
    return operation


def _apply_superseded_item(
    uid: str,
    *,
    memory_id: str,
    superseded_by: str,
    control: MemoryControlState,
    run_id: str,
    db_client,
) -> None:
    idempotency_key = deterministic_contract_id(
        "canonical-consolidation-supersede",
        {"uid": uid, "memory_id": memory_id, "superseded_by": superseded_by},
    )
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=f"consolidation_supersede_{run_id}",
        target_memory_id=memory_id,
        evidence_ids=[],
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "target_memory_id": memory_id,
            "result_status": LifecycleState.superseded.value,
            "supersedes": [],
        },
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    op_path = f"{MemoryCollections(uid=uid).memory_operations}/{operation.operation_id}"
    op_ref = db_client.document(op_path)
    if not op_ref.get().exists:
        op_ref.set(operation.model_dump(mode="json"))

    patch_payload = {
        "patch_id": f"patch_sup_{idempotency_key[:24]}",
        "packet_id": f"consolidation_{run_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        "decision": DurablePatchDecision.update.value,
        "result_status": LifecycleState.superseded.value,
        "target_memory_id": memory_id,
        "memory_text": None,
        "evidence_ids": [],
        "supersedes": [],
        "superseded_by": superseded_by,
    }
    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=db_client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"supersede apply failed for {memory_id}: {result.status} ({result.reason})")

    item = result.memory_items[0] if result.memory_items else None
    if item is None:
        snapshot = db_client.document(f"{MemoryCollections(uid=uid).memory_items}/{memory_id}").get()
        if getattr(snapshot, "exists", False):
            item = MemoryItem(**(snapshot.to_dict() or {}))
    if item is not None and item.tier == MemoryLayer.long_term:
        delete_atom_keyword_doc(uid, item.memory_id)
    delete_canonical_memory_vector(uid, memory_id)
    invalidate_kg_for_memory_retraction(uid, [memory_id])


def _apply_corroboration_bump(
    uid: str,
    *,
    item: MemoryItem,
    control: MemoryControlState,
    run_id: str,
    now: datetime,
    db_client,
) -> None:
    current_count = getattr(item, "corroboration_count", 0) or 0
    idempotency_key = deterministic_contract_id(
        "canonical-consolidation-corroborate",
        {"uid": uid, "memory_id": item.memory_id, "count": current_count + 1},
    )
    evidence_ids = [ev.evidence_id for ev in item.evidence]
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=f"consolidation_corroborate_{run_id}",
        target_memory_id=item.memory_id,
        evidence_ids=evidence_ids,
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "target_memory_id": item.memory_id,
            "result_status": LifecycleState.active.value,
            "supersedes": [],
        },
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    op_path = f"{MemoryCollections(uid=uid).memory_operations}/{operation.operation_id}"
    op_ref = db_client.document(op_path)
    if not op_ref.get().exists:
        op_ref.set(operation.model_dump(mode="json"))

    patch_payload = {
        "patch_id": f"patch_corr_{idempotency_key[:24]}",
        "packet_id": f"consolidation_{run_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        "decision": DurablePatchDecision.update.value,
        "result_status": LifecycleState.active.value,
        "target_memory_id": item.memory_id,
        "memory_text": item.content,
        "evidence_ids": evidence_ids,
        "corroboration_count": current_count + 1,
        "last_corroborated_at": now.isoformat(),
    }
    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=db_client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"corroboration bump failed for {item.memory_id}: {result.status}")


def _escalate_to_review_queue(
    uid: str,
    *,
    decision: ConsolidationAgentDecision,
    survivor: MemoryItem,
    db_client,
) -> None:
    conflict_ids = decision.conflict_with or decision.supersedes
    fact = {
        "id": decision.survivor_memory_id,
        "content": decision.memory_text or survivor.content,
        "veracity": 0.4,
        "importance": 0.5,
    }
    conflict_fact = {"veracity": 0.85}
    if not decision.review_required and not should_escalate_conflict(fact, conflict_fact):
        return
    create_review_conflict(
        uid,
        fact=fact,
        conflict_with=conflict_ids,
        impact=0.5,
    )
    logger.info(
        "consolidation_review_escalated uid=%s survivor=%s conflicts=%d",
        uid,
        decision.survivor_memory_id,
        len(conflict_ids),
    )


def apply_consolidation_decision(
    uid: str,
    *,
    decision: ConsolidationAgentDecision,
    pending_by_id: Dict[str, MemoryItem],
    control: MemoryControlState,
    run_id: str,
    now: datetime,
    db_client,
) -> List[str]:
    """Apply one agent decision via durable patch apply + supersede side effects."""
    if decision.decision == "review" or decision.review_required:
        survivor = pending_by_id.get(decision.survivor_memory_id)
        if survivor is not None:
            _escalate_to_review_queue(uid, decision=decision, survivor=survivor, db_client=db_client)
        return []

    durable_decision = DurablePatchDecision(decision.decision)
    if durable_decision == DurablePatchDecision.keep_both:
        return []

    survivor = pending_by_id.get(decision.survivor_memory_id)
    evidence_ids = _dedupe_evidence_ids(
        *(decision.evidence_ids or []),
        *([ev.evidence_id for ev in survivor.evidence] if survivor else []),
    )
    if (
        durable_decision
        in {
            DurablePatchDecision.update,
            DurablePatchDecision.merge,
            DurablePatchDecision.add_evidence,
            DurablePatchDecision.skip_duplicate,
        }
        and not evidence_ids
    ):
        if survivor:
            evidence_ids = [ev.evidence_id for ev in survivor.evidence]

    operation = _ensure_consolidation_operation(
        uid=uid,
        decision=decision,
        control=control,
        run_id=run_id,
        db_client=db_client,
    )
    idempotency_key = deterministic_contract_id(
        "canonical-consolidation-decision",
        {
            "uid": uid,
            "survivor": decision.survivor_memory_id,
            "decision": decision.decision,
            "supersedes": sorted(decision.supersedes),
            "memory_text": (decision.memory_text or "")[:200],
        },
    )
    patch_payload: Dict[str, Any] = {
        "patch_id": f"patch_cons_{idempotency_key[:24]}",
        "packet_id": f"consolidation_{run_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        "decision": durable_decision.value,
        "result_status": LifecycleState.active.value,
        "target_memory_id": decision.survivor_memory_id,
        "memory_text": decision.memory_text,
        "evidence_ids": evidence_ids,
        "supersedes": sorted(decision.supersedes),
        "rationale": sanitize_pii(decision.rationale or "")[:500],
    }
    if decision.corroboration_increment and survivor is not None:
        current_count = getattr(survivor, "corroboration_count", 0) or 0
        patch_payload["corroboration_count"] = current_count + 1
        patch_payload["last_corroborated_at"] = now.isoformat()

    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=db_client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(
            f"consolidation apply failed for {decision.survivor_memory_id}: {result.status} ({result.reason})"
        )

    applied: List[str] = [decision.survivor_memory_id]
    control = _read_control_state(uid, db_client=db_client)
    for superseded_id in decision.supersedes:
        if superseded_id == decision.survivor_memory_id:
            continue
        _apply_superseded_item(
            uid,
            memory_id=superseded_id,
            superseded_by=decision.survivor_memory_id,
            control=control,
            run_id=run_id,
            db_client=db_client,
        )
        applied.append(superseded_id)
        control = _read_control_state(uid, db_client=db_client)
    return applied


@dataclass
class ConsolidationReport:
    uid: str
    skipped_reason: Optional[str] = None
    trigger_reason: Optional[str] = None
    pending_count: int = 0
    decisions_applied: int = 0
    superseded_memory_ids: List[str] = field(default_factory=list)
    review_escalations: int = 0
    last_consolidation_run_at: Optional[datetime] = None


def run_canonical_consolidation(
    uid: str,
    *,
    db_client=None,
    now: Optional[datetime] = None,
    run_id: str,
    llm_invoke: Optional[Callable[[str], str]] = None,
    batch_threshold: Optional[int] = None,
) -> ConsolidationReport:
    """Batched consolidation entry point for one canonical user."""
    client = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))

    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return ConsolidationReport(uid=uid, skipped_reason="not_canonical_cohort")
    if not consolidation_enabled():
        return ConsolidationReport(uid=uid, skipped_reason="consolidation_disabled")

    pending = list_pending_consolidation_items(uid, db_client=client, now=current_time)
    control = _read_control_state(uid, db_client=client)
    trigger = consolidation_trigger_reason(
        pending_count=len(pending),
        last_consolidation_run_at=control.last_consolidation_run_at,
        now=current_time,
        batch_threshold=batch_threshold,
    )
    if trigger is None:
        return ConsolidationReport(
            uid=uid,
            skipped_reason="consolidation_not_due",
            pending_count=len(pending),
            last_consolidation_run_at=control.last_consolidation_run_at,
        )

    report = ConsolidationReport(
        uid=uid,
        trigger_reason=trigger,
        pending_count=len(pending),
        last_consolidation_run_at=control.last_consolidation_run_at,
    )
    if not pending:
        return report

    context = gather_consolidation_candidates(uid, pending, db_client=client)
    agent_batch = invoke_consolidation_agent(context, llm_invoke=llm_invoke)
    pending_by_id = {item.memory_id: item for item in pending}

    for decision in agent_batch.decisions:
        if decision.decision == "review" or decision.review_required:
            survivor = pending_by_id.get(decision.survivor_memory_id)
            if survivor is not None:
                _escalate_to_review_queue(uid, decision=decision, survivor=survivor, db_client=client)
                report.review_escalations += 1
            continue
        control = _read_control_state(uid, db_client=client)
        applied_ids = apply_consolidation_decision(
            uid,
            decision=decision,
            pending_by_id=pending_by_id,
            control=control,
            run_id=run_id,
            now=current_time,
            db_client=client,
        )
        if applied_ids:
            report.decisions_applied += 1
            for memory_id in applied_ids:
                if memory_id in decision.supersedes:
                    report.superseded_memory_ids.append(memory_id)

    updated_control = _read_control_state(uid, db_client=client).model_copy(
        update={"last_consolidation_run_at": current_time, "updated_at": current_time}
    )
    _persist_control_state(updated_control, db_client=client)
    report.last_consolidation_run_at = current_time
    return report
