import hashlib
import json
from typing import Any, Dict, List

from database import memory_ledger
from models.v17_memory_contracts import DurableMemoryPatch, DurablePatchDecision


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
    return {
        "id": fact_id,
        "content": patch.memory_text,
        "predicate": patch.predicate,
        "arguments": dict(patch.arguments or {}),
        "qualifiers": {},
        "source": "v17_durable_memory_patch",
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
        return [
            memory_ledger.add_evidence(patch.target_memory_id, evidence) for evidence in _dedupe_evidence_refs(patch)
        ]

    if decision in {DurablePatchDecision.update, DurablePatchDecision.merge}:
        fact = _fact_from_patch(patch)
        kind = "merge" if decision == DurablePatchDecision.merge else "update"
        mutations = [memory_ledger.add_fact(fact)]
        mutations.append(memory_ledger.supersede_fact(patch.target_memory_id, by=fact["id"], kind=kind))
        for superseded_id in patch.supersedes:
            if superseded_id != patch.target_memory_id:
                mutations.append(memory_ledger.supersede_fact(superseded_id, by=fact["id"], kind=kind))
        return mutations

    return []


def apply_v17_patch_to_ledger_state(
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
