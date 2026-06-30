from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from database import memory_ledger
from database.memory_ledger import HeadConflict
from models.memory_contracts import DurableMemoryPatch, DurablePatchDecision, LifecycleState
from utils.memory.patch_adapter import patch_to_ledger_mutations, persist_non_active_route_for_patch

_PREDICATE_RE = re.compile(r'^[a-z][a-z0-9_]{1,63}$')
_ACTIVE_WRITE_DECISIONS = {
    DurablePatchDecision.add,
    DurablePatchDecision.keep_both,
    DurablePatchDecision.add_evidence,
    DurablePatchDecision.update,
    DurablePatchDecision.merge,
}


class MemoryToolValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MemoryToolResult:
    patch_id: str
    decision: str
    commit_id: Optional[str]
    applied: bool
    mutations: List[Dict[str, Any]] = field(default_factory=list)
    non_active_route: Optional[Any] = None
    head_conflict_retry: bool = False


AppendCommit = Callable[..., Dict[str, Any]]
ReadHead = Callable[[str], Optional[str]]
RoutePersister = Callable[..., Any]


@dataclass
class MemoryToolContext:
    uid: str
    allowed_evidence_ids: set[str] = field(default_factory=set)
    existing_facts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    run_id: Optional[str] = None
    append_commit: AppendCommit = memory_ledger.append_commit
    read_head: ReadHead = memory_ledger.read_head
    route_persister: RoutePersister = persist_non_active_route_for_patch
    retry_on_head_conflict: bool = True

    def __post_init__(self):
        if not self.uid or not self.uid.strip():
            raise ValueError('uid is required')


def _is_active_write(patch: DurableMemoryPatch) -> bool:
    return patch.decision in _ACTIVE_WRITE_DECISIONS


def _evidence_ids_for_patch(patch: DurableMemoryPatch) -> set[str]:
    ids = set(patch.evidence_ids or [])
    ids.update(ref.evidence_id for ref in patch.evidence_refs)
    return {evidence_id for evidence_id in ids if evidence_id}


def _validate_evidence_refs(patch: DurableMemoryPatch, allowed_evidence_ids: set[str]) -> None:
    evidence_ids = _evidence_ids_for_patch(patch)
    if patch.result_status in {LifecycleState.active, LifecycleState.review} and not evidence_ids:
        raise MemoryToolValidationError('active/review write requires evidence refs')
    if allowed_evidence_ids and not evidence_ids.issubset(allowed_evidence_ids):
        missing = sorted(evidence_ids - allowed_evidence_ids)
        raise MemoryToolValidationError(f'unresolved evidence refs: {missing}')


def _validate_patch_shape(patch: DurableMemoryPatch) -> None:
    if not _is_active_write(patch):
        return
    if patch.decision in {
        DurablePatchDecision.add,
        DurablePatchDecision.keep_both,
        DurablePatchDecision.update,
        DurablePatchDecision.merge,
    }:
        if not (patch.memory_text or '').strip():
            raise MemoryToolValidationError('memory_text is required for fact writes')
        if len((patch.memory_text or '').strip()) < 3:
            raise MemoryToolValidationError('memory_text is too short')
        if not patch.subject_entity_id:
            raise MemoryToolValidationError('subject_entity_id is required for fact writes')
        if not patch.predicate or not _PREDICATE_RE.match(patch.predicate):
            raise MemoryToolValidationError('predicate is malformed')
    if (
        patch.decision
        in {
            DurablePatchDecision.add_evidence,
            DurablePatchDecision.update,
            DurablePatchDecision.merge,
            DurablePatchDecision.skip_duplicate,
        }
        and not patch.target_memory_id
    ):
        raise MemoryToolValidationError('target_memory_id is required')


def _validate_subject_integrity(patch: DurableMemoryPatch, existing_facts: Dict[str, Dict[str, Any]]) -> None:
    if not patch.target_memory_id or not patch.subject_entity_id:
        return
    target = existing_facts.get(patch.target_memory_id)
    if not target:
        return
    target_subject = target.get('subject_entity_id')
    if target_subject and target_subject != patch.subject_entity_id:
        raise MemoryToolValidationError('patch subject does not match target fact subject')


def validate_patch_for_memory_tools(patch: DurableMemoryPatch, context: MemoryToolContext) -> None:
    _validate_evidence_refs(patch, context.allowed_evidence_ids)
    _validate_patch_shape(patch)
    _validate_subject_integrity(patch, context.existing_facts)


def _commit_id(result: Dict[str, Any]) -> Optional[str]:
    commit = result.get('commit') or {}
    return commit.get('commit_id')


def apply_patch_with_memory_tools(patch: DurableMemoryPatch, context: MemoryToolContext) -> MemoryToolResult:
    validate_patch_for_memory_tools(patch, context)
    if not _is_active_write(patch):
        route = context.route_persister(
            context.uid,
            patch,
            audit_metadata={'memory_tool': 'l2_promotion_agent'},
        )
        return MemoryToolResult(
            patch_id=patch.patch_id,
            decision=patch.decision.value,
            commit_id=None,
            applied=False,
            non_active_route=route,
        )

    mutations = patch_to_ledger_mutations(patch)
    try:
        result = context.append_commit(
            context.uid,
            patch.observed_head_commit_id,
            mutations,
            run_id=context.run_id or patch.run_id,
            use_current_head=False,
        )
        return MemoryToolResult(
            patch_id=patch.patch_id,
            decision=patch.decision.value,
            commit_id=_commit_id(result),
            applied=bool(result.get('applied')),
            mutations=mutations,
        )
    except HeadConflict:
        if not context.retry_on_head_conflict:
            raise
        current_head = context.read_head(context.uid)
        rebased_patch = patch.model_copy(update={'observed_head_commit_id': current_head})
        validate_patch_for_memory_tools(rebased_patch, context)
        rebased_mutations = patch_to_ledger_mutations(rebased_patch)
        result = context.append_commit(
            context.uid,
            current_head,
            rebased_mutations,
            run_id=context.run_id or patch.run_id,
            use_current_head=False,
        )
        return MemoryToolResult(
            patch_id=patch.patch_id,
            decision=patch.decision.value,
            commit_id=_commit_id(result),
            applied=bool(result.get('applied')),
            mutations=rebased_mutations,
            head_conflict_retry=True,
        )


def evidence_ids_from_bundle(bundle: Dict[str, Any]) -> set[str]:
    ids = set()
    for packet in bundle.get('evidence_packets') or []:
        ids.update(packet.get('evidence_ids') or [])
        for ref in packet.get('source_refs') or []:
            if isinstance(ref, dict) and ref.get('evidence_id'):
                ids.add(ref['evidence_id'])
        for observation in packet.get('observations') or []:
            if isinstance(observation, dict):
                ids.update(observation.get('evidence_ids') or [])
    for item in bundle.get('l1_items') or []:
        ids.update(item.get('evidence_ids') or [])
        for ref in item.get('source_refs') or []:
            if isinstance(ref, dict) and ref.get('evidence_id'):
                ids.add(ref['evidence_id'])
    return {evidence_id for evidence_id in ids if evidence_id}


def facts_from_bundle(bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    facts = {}
    graph = bundle.get('graph_snapshot') or {}
    for edge in graph.get('edges') or []:
        if isinstance(edge, dict) and edge.get('fact_id'):
            facts[str(edge['fact_id'])] = edge
    for item in bundle.get('vector_seed') or []:
        if isinstance(item, dict):
            fact_id = item.get('id') or item.get('memory_id')
            if fact_id:
                facts[str(fact_id)] = item
    return facts


def apply_patches_with_memory_tools(
    patches: Iterable[DurableMemoryPatch],
    context: MemoryToolContext,
) -> List[MemoryToolResult]:
    return [apply_patch_with_memory_tools(patch, context) for patch in patches]
