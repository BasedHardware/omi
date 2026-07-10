"""Canonical durable-memory patch → ledger and non-active route adapter (WS-G / Wave A)."""

import hashlib
import json
from typing import Any, Dict, List, Optional

from database import memory_ledger
from database.memory_non_active_routes import (
    NonActiveRoute,
    NonActiveRouteOutcome,
    PersistedNonActiveRouteOutcome,
    persist_non_active_route_outcome,
)
from models.memory_contracts import DurableMemoryPatch, DurablePatchDecision


def _stable_id(prefix: str, payload: Dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:20]}"


def _dedupe_evidence_refs(patch: DurableMemoryPatch) -> List[Dict[str, Any]]:
    refs_by_id: Dict[str, Dict[str, Any]] = {}
    for evidence_ref in patch.evidence_refs:
        ref = evidence_ref.model_dump(exclude_none=True)
        refs_by_id.setdefault(evidence_ref.evidence_id, ref)
    for evidence_id in patch.evidence_ids:
        refs_by_id.setdefault(evidence_id, {"evidence_id": evidence_id})
    return list(refs_by_id.values())


def _fact_id_for_patch(patch: DurableMemoryPatch) -> str:
    if patch.new_memory_id:
        return patch.new_memory_id
    return _stable_id(
        "mem",
        {
            "patch_id": patch.patch_id,
            "packet_id": patch.packet_id,
            "memory_text": patch.memory_text,
            "idempotency_key": patch.idempotency_key,
        },
    )


def _fact_from_patch(patch: DurableMemoryPatch) -> Dict[str, Any]:
    fact_id = _fact_id_for_patch(patch)
    fact: Dict[str, Any] = {
        "id": fact_id,
        "content": patch.memory_text,
        "predicate": patch.predicate,
        "arguments": dict(patch.arguments or {}),
        "qualifiers": {},
        "source": "durable_memory_patch",
        "source_patch_id": patch.patch_id,
        "packet_id": patch.packet_id,
        "idempotency_key": patch.idempotency_key,
        "evidence_set": _dedupe_evidence_refs(patch),
        "metadata": {
            "decision": patch.decision.value,
            "result_status": patch.result_status.value,
            "rationale": patch.rationale,
        },
    }
    if patch.subject_entity_id:
        fact["subject_entity_id"] = patch.subject_entity_id
    if patch.subject_label:
        fact["subject_label"] = patch.subject_label
    if patch.aboutness:
        fact["aboutness"] = patch.aboutness
    if patch.relationship_to_user:
        fact["relationship_to_user"] = patch.relationship_to_user
    return fact


def _required_target_memory_id(patch: DurableMemoryPatch) -> str:
    if patch.target_memory_id is None:
        raise ValueError("target_memory_id is required for this patch decision")
    return patch.target_memory_id


def patch_to_ledger_mutations(patch: DurableMemoryPatch) -> List[Dict[str, Any]]:
    decision = patch.decision
    if decision in {
        DurablePatchDecision.skip_duplicate,
        DurablePatchDecision.context_only,
        DurablePatchDecision.reject,
        DurablePatchDecision.review,
    }:
        return []

    if decision == DurablePatchDecision.add or decision == DurablePatchDecision.keep_both:
        return [memory_ledger.add_fact(_fact_from_patch(patch))]

    if decision == DurablePatchDecision.add_evidence:
        target_memory_id = _required_target_memory_id(patch)
        return [memory_ledger.add_evidence(target_memory_id, evidence) for evidence in _dedupe_evidence_refs(patch)]

    if decision in {DurablePatchDecision.update, DurablePatchDecision.merge}:
        target_memory_id = _required_target_memory_id(patch)
        fact = _fact_from_patch(patch)
        kind = "merge" if decision == DurablePatchDecision.merge else "update"
        mutations = [memory_ledger.add_fact(fact)]
        mutations.append(memory_ledger.supersede_fact(target_memory_id, by=fact["id"], kind=kind))
        for superseded_id in patch.supersedes:
            if superseded_id != target_memory_id:
                mutations.append(memory_ledger.supersede_fact(superseded_id, by=fact["id"], kind=kind))
        return mutations

    return []


_NON_ACTIVE_ROUTE_BY_DECISION = {
    DurablePatchDecision.review: NonActiveRoute.review,
    DurablePatchDecision.context_only: NonActiveRoute.context_only,
    DurablePatchDecision.reject: NonActiveRoute.reject,
    DurablePatchDecision.skip_duplicate: NonActiveRoute.skip,
}


def persist_non_active_route_for_patch(
    uid: str,
    patch: DurableMemoryPatch,
    *,
    reason: Optional[str] = None,
    audit_metadata: Optional[Dict[str, Any]] = None,
    db_client: Any = None,
) -> Optional[PersistedNonActiveRouteOutcome]:
    route = _NON_ACTIVE_ROUTE_BY_DECISION.get(patch.decision)
    if route is None:
        return None

    outcome = NonActiveRouteOutcome(
        uid=uid,
        route=route,
        idempotency_key=f"memory_patch:{patch.idempotency_key}",
        source_ids=_source_ids_for_patch_route(patch),
        reason=reason or patch.rationale or f"{patch.decision.value} decision",
        run_id=patch.run_id,
        patch_id=patch.patch_id,
        audit_metadata={
            **(audit_metadata or {}),
            "route_store_source": "memory_patch_adapter",
            "decision": patch.decision.value,
            "result_status": patch.result_status.value,
            "confidence": patch.confidence,
            "packet_id": patch.packet_id,
            "target_memory_id": patch.target_memory_id,
            "new_memory_id": patch.new_memory_id,
        },
    )
    if db_client is not None:
        return persist_non_active_route_outcome(outcome, db_client=db_client)
    return persist_non_active_route_outcome(outcome)


def _source_ids_for_patch_route(patch: DurableMemoryPatch) -> List[str]:
    source_ids = [patch.packet_id]
    source_ids.extend(patch.evidence_ids or [])
    for evidence_ref in patch.evidence_refs:
        source_ids.append(evidence_ref.evidence_id)
        if evidence_ref.source_id:
            source_ids.append(evidence_ref.source_id)
    if patch.target_memory_id:
        source_ids.append(patch.target_memory_id)
    if patch.new_memory_id:
        source_ids.append(patch.new_memory_id)
    return sorted({source_id for source_id in source_ids if source_id})


def apply_memory_patch_to_ledger_state(
    state: Dict[str, Any], commits: Dict[str, Dict[str, Any]], patch: DurableMemoryPatch
) -> Dict[str, Any]:
    mutations = patch_to_ledger_mutations(patch)
    return memory_ledger.append_commit_to_history(
        state,
        commits,
        patch.observed_head_commit_id,
        mutations,
        run_id=patch.run_id,
        use_current_head=False,
    )


__all__ = [
    "apply_memory_patch_to_ledger_state",
    "patch_to_ledger_mutations",
    "persist_non_active_route_for_patch",
]
