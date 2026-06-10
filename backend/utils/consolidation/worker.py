from dataclasses import dataclass, field
from typing import Dict, List, Optional

from database import memories as memories_db
from database import memory_ledger
from database import short_term_memories as short_term_db
from database.vector_db import find_similar_memories
from models.memories import Memory, MemoryDB, ShortTermMemory
from utils.llm.memories import TypedMemoryResolution
from utils.consolidation.typed_resolver import (
    fact_from_short_term,
    mutations_for_typed_resolution,
    pending_review_fact,
    resolve_typed_relationship,
)


@dataclass
class CandidateRetrievalMetric:
    short_term_id: str
    candidate_ids: List[str]
    expected_candidate_id: Optional[str] = None
    failure: Optional[str] = None


@dataclass
class ConsolidationResult:
    processed: int = 0
    committed: int = 0
    candidate_metrics: List[CandidateRetrievalMetric] = field(default_factory=list)
    commit_ids: List[str] = field(default_factory=list)
    shadow_mutations: List[Dict] = field(default_factory=list)
    review_conflicts: List[Dict] = field(default_factory=list)


def retrieve_candidates(uid: str, short_term: Dict, *, limit: int = 8) -> List[Dict]:
    matches = find_similar_memories(
        uid,
        short_term.get('content', ''),
        threshold=0.0,
        limit=limit,
        subject_entity_id=short_term.get('subject_entity_id'),
    )
    candidates = []
    for match in matches:
        memory = memories_db.get_memory(uid, match['memory_id'])
        if memory and memory.get('invalid_at') is None:
            candidates.append(memory)
    return candidates


def candidate_recall_metric(short_term: Dict, candidates: List[Dict], expected_candidate_id: Optional[str] = None):
    candidate_ids = [candidate.get('id') for candidate in candidates if candidate.get('id')]
    failure = None
    if expected_candidate_id and expected_candidate_id not in candidate_ids:
        failure = 'candidate_retrieval_fail'
    return CandidateRetrievalMetric(
        short_term_id=short_term.get('id'),
        candidate_ids=candidate_ids,
        expected_candidate_id=expected_candidate_id,
        failure=failure,
    )


def consolidate_pending_window(
    uid: str,
    *,
    limit: int = 100,
    expected_candidates: Optional[Dict[str, str]] = None,
    apply_to_head: bool = False,
) -> ConsolidationResult:
    pending = short_term_db.get_short_term_memories(uid, status='pending_consolidation', limit=limit)
    result = ConsolidationResult()
    expected_candidates = expected_candidates or {}
    candidates_by_short_term = {}

    for short_term in pending:
        result.processed += 1
        candidates = retrieve_candidates(uid, short_term)
        candidates_by_short_term[short_term.get('id')] = candidates
        result.candidate_metrics.append(
            candidate_recall_metric(short_term, candidates, expected_candidates.get(short_term.get('id')))
        )

    result.shadow_mutations, result.review_conflicts = resolve_window_mutations(
        uid, pending, candidates_by_short_term=candidates_by_short_term
    )
    if not apply_to_head:
        return result

    for conflict in result.review_conflicts:
        short_term_db.mark_pending_review(
            uid,
            conflict['short_term_id'],
            conflict['fact'].get('review_conflict') or {},
        )

    resolution_by_short_term = _typed_resolutions(uid, pending, candidates_by_short_term)
    skip_add_ids = {
        short_term_id
        for short_term_id, resolution in resolution_by_short_term.items()
        if resolution.relationship in ('duplicate', 'refine', 'contradict', 'review_conflict')
        or resolution.review_required
    }
    active_short_terms = _active_short_terms_after_window_resolution(pending)
    active_short_terms = [
        short_term
        for short_term in active_short_terms
        if short_term.get('id') not in skip_add_ids
        and short_term.get('id') not in {conflict['short_term_id'] for conflict in result.review_conflicts}
    ]
    memory_dbs = [
        _memory_db_from_short_term(uid, short_term, extractor_id='rolling_consolidation')
        for short_term in active_short_terms
    ]
    if memory_dbs:
        commit_result = memories_db.save_memories(uid, [memory_db.model_dump() for memory_db in memory_dbs])
        commit_id = (commit_result or {}).get('commit', {}).get('commit_id')
        if commit_id:
            result.commit_ids.append(commit_id)
            active_ids = {short_term.get('id') for short_term in active_short_terms}
            no_candidate_window_ids = {
                short_term.get('id') for short_term in pending if not candidates_by_short_term.get(short_term.get('id'))
            }
            review_ids = {conflict['short_term_id'] for conflict in result.review_conflicts}
            for short_term in pending:
                if short_term.get('id') in review_ids:
                    continue
                if short_term.get('id') in active_ids or short_term.get('id') in no_candidate_window_ids:
                    short_term_db.mark_consolidated(uid, short_term['id'], commit_id)
        result.committed = len(memory_dbs)

    for short_term in pending:
        resolution = resolution_by_short_term.get(short_term.get('id'))
        if not resolution:
            continue
        if resolution.relationship == 'refine' and resolution.candidate_id:
            commit_result = memories_db.refine_memory(uid, resolution.candidate_id, resolution.arg_changes)
            commit_id = (commit_result or {}).get('commit', {}).get('commit_id')
            if commit_id:
                result.commit_ids.append(commit_id)
            short_term_db.mark_consolidated(uid, short_term['id'], commit_id)
        elif resolution.relationship == 'duplicate':
            short_term_db.mark_consolidated(uid, short_term['id'], None)
        elif resolution.relationship == 'contradict':
            commit_result = memories_db.merge_contradict_memory(
                uid,
                fact_from_short_term(uid, short_term, extractor_id='rolling_consolidation'),
                resolution.supersedes,
                valid_interval=resolution.valid_interval,
            )
            commit_id = (commit_result or {}).get('commit', {}).get('commit_id')
            if commit_id:
                result.commit_ids.append(commit_id)
                result.committed += 1
                short_term_db.mark_consolidated(uid, short_term['id'], commit_id)

    return result


def _memory_db_from_short_term(uid: str, short_term: Dict, *, extractor_id: str) -> MemoryDB:
    memory_db = MemoryDB.from_memory(
        _memory_from_short_term(short_term),
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
    memory_db.evidence = short_term.get('evidence', [])
    memory_db.capture_confidence = short_term.get('capture_confidence')
    memory_db.veracity = short_term.get('veracity')
    memory_db.uncertainty_reasons = short_term.get('uncertainty_reasons', [])
    return memory_db


def resolve_window_mutations(
    uid: str, short_terms: List[Dict], *, candidates_by_short_term: Optional[Dict[str, List[Dict]]] = None
) -> tuple[List[Dict], List[Dict]]:
    mutations = []
    review_conflicts = []
    candidates_by_short_term = candidates_by_short_term or {}
    for short_term in short_terms:
        candidates = candidates_by_short_term.get(short_term.get('id')) or []
        if not candidates:
            continue
        fact = fact_from_short_term(uid, short_term, extractor_id='rolling_consolidation_shadow')
        resolution = resolve_typed_relationship(fact, candidates)
        if resolution.review_required:
            review_conflicts.append(
                {
                    'short_term_id': short_term.get('id'),
                    'resolution': resolution.model_dump(),
                    'fact': pending_review_fact(fact, resolution),
                }
            )
        mutations.extend(mutations_for_typed_resolution(fact, resolution))

    active_ids = {item.get('id') for item in _active_short_terms_after_window_resolution(short_terms)}
    by_id = {item.get('id'): item for item in short_terms}
    for short_term in short_terms:
        if candidates_by_short_term.get(short_term.get('id')):
            continue
        fact = MemoryDB.from_memory(
            _memory_from_short_term(short_term),
            uid,
            short_term.get('id'),
            False,
            source_id=short_term.get('id'),
            source_type='short_term',
            source_signal=short_term.get('source_signal', 'unknown'),
            artifact_ref={'kind': 'short_term', 'short_term_id': short_term.get('id')},
            extractor_id='rolling_consolidation_shadow',
            subject_entity_id=short_term.get('subject_entity_id'),
            subject_attribution=short_term.get('subject_attribution'),
        ).model_dump()
        mutations.append(memory_ledger.add_fact(fact))
        if short_term.get('id') not in active_ids:
            superseded_by = _first_later_decision_id(short_term, short_terms)
            if superseded_by and superseded_by in by_id:
                replacement = MemoryDB.from_memory(
                    _memory_from_short_term(by_id[superseded_by]),
                    uid,
                    superseded_by,
                    False,
                    source_id=superseded_by,
                    source_type='short_term',
                    source_signal=by_id[superseded_by].get('source_signal', 'unknown'),
                    artifact_ref={'kind': 'short_term', 'short_term_id': superseded_by},
                    extractor_id='rolling_consolidation_shadow',
                    subject_entity_id=by_id[superseded_by].get('subject_entity_id'),
                    subject_attribution=by_id[superseded_by].get('subject_attribution'),
                )
                mutations.append(memory_ledger.supersede_fact(fact['id'], by=replacement.id, kind='contradict'))
    return mutations, review_conflicts


def _typed_resolutions(
    uid: str, short_terms: List[Dict], candidates_by_short_term: Dict[str, List[Dict]]
) -> Dict[str, TypedMemoryResolution]:
    resolutions = {}
    for short_term in short_terms:
        candidates = candidates_by_short_term.get(short_term.get('id')) or []
        if not candidates:
            continue
        fact = fact_from_short_term(uid, short_term, extractor_id='rolling_consolidation')
        resolutions[short_term.get('id')] = resolve_typed_relationship(fact, candidates)
    return resolutions


def _active_short_terms_after_window_resolution(short_terms: List[Dict]) -> List[Dict]:
    superseded = {item.get('id') for item in short_terms if _first_later_decision_id(item, short_terms)}
    return [item for item in short_terms if item.get('id') not in superseded]


def _first_later_decision_id(short_term: Dict, short_terms: List[Dict]) -> Optional[str]:
    if 'considering ' not in (short_term.get('content') or '').lower():
        return None
    for candidate in sorted(short_terms, key=lambda item: str(item.get('created_at') or '')):
        if candidate.get('id') == short_term.get('id'):
            continue
        if 'decided ' in (candidate.get('content') or '').lower():
            return candidate.get('id')
    return None


def _memory_from_short_term(short_term: Dict) -> Memory:
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


def short_term_from_memory(memory: Memory, uid: str, **kwargs) -> ShortTermMemory:
    return ShortTermMemory.from_memory(memory, uid, **kwargs)
