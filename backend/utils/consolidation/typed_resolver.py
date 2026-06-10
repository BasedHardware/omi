from typing import Any, Dict, List, Optional

from config.memory_confidence import CONFIDENCE_BANDS
from database import memory_ledger
from models.memories import Memory, MemoryDB
from utils.llm.memories import TypedMemoryResolution


def resolve_typed_relationship(new_fact: Dict, candidates: List[Dict]) -> TypedMemoryResolution:
    if not candidates:
        return TypedMemoryResolution(relationship='extend', reasoning='No candidates retrieved.')

    comparable = [_candidate for _candidate in candidates if _same_subject(new_fact, _candidate)]
    if not comparable:
        return TypedMemoryResolution(relationship='extend', reasoning='No same-subject candidates retrieved.')

    duplicate = next((_candidate for _candidate in comparable if _same_proposition(new_fact, _candidate)), None)
    if duplicate:
        return TypedMemoryResolution(
            relationship='duplicate',
            candidate_id=duplicate.get('id'),
            reasoning='Candidate already captures the same predicate and arguments.',
        )

    same_predicate = [
        _candidate for _candidate in comparable if _candidate.get('predicate') == new_fact.get('predicate')
    ]
    refinement = next((_candidate for _candidate in same_predicate if _is_refinement(new_fact, _candidate)), None)
    if refinement:
        return TypedMemoryResolution(
            relationship='refine',
            candidate_id=refinement.get('id'),
            arg_changes=_arg_changes(new_fact, refinement),
            reasoning='New fact narrows or enriches an existing proposition without falsifying it.',
        )

    contradiction = next(
        (_candidate for _candidate in same_predicate if _has_conflicting_arguments(new_fact, _candidate)), None
    )
    if contradiction:
        if _requires_review(new_fact, contradiction):
            return TypedMemoryResolution(
                relationship='review_conflict',
                candidate_id=contradiction.get('id'),
                supersedes=[contradiction.get('id')],
                review_required=True,
                valid_interval=_valid_interval_for_supersession(new_fact),
                reasoning='Low-veracity new contradiction does not outweigh a high-veracity existing fact.',
            )
        return TypedMemoryResolution(
            relationship='contradict',
            candidate_id=contradiction.get('id'),
            supersedes=[contradiction.get('id')],
            valid_interval=_valid_interval_for_supersession(new_fact),
            reasoning='Same predicate has incompatible arguments and evidence is strong enough to supersede.',
        )

    return TypedMemoryResolution(
        relationship='coexist',
        candidate_id=comparable[0].get('id'),
        reasoning='Retrieved candidates can remain true alongside the new fact.',
    )


def mutations_for_typed_resolution(
    new_fact: Dict,
    resolution: TypedMemoryResolution,
    *,
    candidate_by_id: Optional[Dict[str, Dict]] = None,
) -> List[Dict[str, Any]]:
    if resolution.relationship == 'duplicate' or resolution.review_required:
        return []
    if resolution.relationship == 'refine' and resolution.candidate_id:
        return [memory_ledger.refine_fact(resolution.candidate_id, resolution.arg_changes)]

    mutations = [memory_ledger.add_fact(new_fact)]
    if resolution.relationship == 'contradict':
        for fact_id in resolution.supersedes:
            mutations.append(
                memory_ledger.supersede_fact(
                    fact_id,
                    by=new_fact.get('id'),
                    kind='contradict',
                    valid_interval=resolution.valid_interval,
                )
            )
    return mutations


def pending_review_fact(new_fact: Dict, resolution: TypedMemoryResolution) -> Dict:
    pending = dict(new_fact)
    qualifiers = dict(pending.get('qualifiers') or {})
    qualifiers['status'] = 'pending_review'
    qualifiers['review_reason'] = 'low_veracity_contradiction'
    pending['qualifiers'] = qualifiers
    pending['status'] = 'pending_review'
    pending['review_conflict'] = {
        'candidate_id': resolution.candidate_id,
        'supersedes': resolution.supersedes,
        'reasoning': resolution.reasoning,
    }
    return pending


def fact_from_short_term(uid: str, short_term: Dict, *, extractor_id: str) -> Dict:
    fact = MemoryDB.from_memory(
        _memory_from_short_term_dict(short_term),
        uid,
        short_term.get('id'),
        False,
        source_id=short_term.get('id'),
        source_type='short_term',
        source_signal=short_term.get('source_signal', 'unknown'),
        artifact_ref={'kind': 'short_term', 'short_term_id': short_term.get('id')},
        extractor_id=extractor_id,
        subject_entity_id=short_term.get('subject_entity_id'),
        subject_attribution=short_term.get('subject_attribution'),
    )
    fact.evidence = short_term.get('evidence', [])
    fact.capture_confidence = short_term.get('capture_confidence')
    fact.veracity = short_term.get('veracity')
    fact.uncertainty_reasons = short_term.get('uncertainty_reasons', [])
    return fact.model_dump()


def _memory_from_short_term_dict(short_term: Dict):
    return Memory(
        content=short_term.get('content', ''),
        category=short_term.get('category', 'system'),
        visibility=short_term.get('visibility', 'private'),
        tags=short_term.get('tags', []),
        headline=short_term.get('headline'),
        predicate=short_term.get('predicate'),
        arguments=short_term.get('arguments') or {},
        subject_entity_id=short_term.get('subject_entity_id'),
        subject_attribution=short_term.get('subject_attribution', 'unknown'),
        object_entity_ids=short_term.get('object_entity_ids') or [],
        qualifiers=short_term.get('qualifiers') or {},
        capture_confidence=short_term.get('capture_confidence'),
        veracity=short_term.get('veracity'),
        uncertainty_reasons=short_term.get('uncertainty_reasons') or [],
        durability=short_term.get('durability'),
    )


def _same_subject(new_fact: Dict, candidate: Dict) -> bool:
    new_subject = new_fact.get('subject_entity_id')
    candidate_subject = candidate.get('subject_entity_id')
    return not new_subject or not candidate_subject or new_subject == candidate_subject


def _same_proposition(new_fact: Dict, candidate: Dict) -> bool:
    return new_fact.get('predicate') == candidate.get('predicate') and (new_fact.get('arguments') or {}) == (
        candidate.get('arguments') or {}
    )


def _is_refinement(new_fact: Dict, candidate: Dict) -> bool:
    new_args = new_fact.get('arguments') or {}
    candidate_args = candidate.get('arguments') or {}
    if not new_args or not candidate_args:
        return False
    for key, value in candidate_args.items():
        if key in new_args and new_args[key] != value:
            return False
    return len(new_args) > len(candidate_args)


def _has_conflicting_arguments(new_fact: Dict, candidate: Dict) -> bool:
    new_args = new_fact.get('arguments') or {}
    candidate_args = candidate.get('arguments') or {}
    shared_keys = set(new_args).intersection(candidate_args)
    return any(new_args[key] != candidate_args[key] for key in shared_keys)


def _arg_changes(new_fact: Dict, candidate: Dict) -> Dict[str, Any]:
    changes = {}
    candidate_args = candidate.get('arguments') or {}
    for key, value in (new_fact.get('arguments') or {}).items():
        if candidate_args.get(key) != value:
            changes[key] = {'to': value}
    if new_fact.get('content') and new_fact.get('content') != candidate.get('content'):
        changes['content'] = {'to': new_fact.get('content')}
    return changes


def _requires_review(new_fact: Dict, candidate: Dict) -> bool:
    new_veracity = new_fact.get('veracity')
    candidate_veracity = candidate.get('veracity')
    return (
        new_veracity is not None
        and candidate_veracity is not None
        and new_veracity < CONFIDENCE_BANDS['medium']
        and candidate_veracity >= CONFIDENCE_BANDS['high']
    )


def _valid_interval_for_supersession(new_fact: Dict) -> Dict[str, Any]:
    valid_from = (new_fact.get('qualifiers') or {}).get('valid_from') or new_fact.get('valid_at')
    if valid_from is None:
        return {}
    return {'valid_to': valid_from}
