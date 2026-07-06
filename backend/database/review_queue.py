import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config.memory_confidence import CONFIDENCE_BANDS
from database import memories as memories_db
from database import memory_ledger
from database import short_term_memories as short_term_db
from database.memory_non_active_routes import (
    NonActiveRoute,
    NonActiveRouteOutcome,
    persist_non_active_route_outcome,
)
from ._client import db

users_collection = 'users'
review_queue_collection = 'memory_review_queue'
corrections_collection = 'memory_corrections'
memories_collection = 'memories'

ACTION_POLICY = {
    'accepted': {'answers', 'actions'},
    'pending': {'answers_with_disclaimer'},
    'pending_review': {'answers_with_disclaimer'},
    'contradicted': {'uncertainty_history'},
    'rejected': {'audit_debug'},
    'dropped': set(),
    'tombstoned': set(),
    'source_tombstoned': set(),
}


def permitted_uses(status: str) -> set[str]:
    return ACTION_POLICY.get(status or 'accepted', ACTION_POLICY['accepted'])


def can_use_for_action(status: str, action_kind: str) -> bool:
    if action_kind == 'irreversible':
        return 'actions' in permitted_uses(status)
    return bool(permitted_uses(status))


def impact_score(new_fact: Dict[str, Any], conflict_fact: Dict[str, Any]) -> float:
    importance = (new_fact.get('qualifiers') or {}).get('importance', new_fact.get('importance', 0.5))
    new_veracity = new_fact.get('veracity') or 0.0
    conflict_veracity = conflict_fact.get('veracity') or 0.0
    return float(importance) * abs(conflict_veracity - new_veracity)


def should_escalate_conflict(new_fact: Dict[str, Any], conflict_fact: Dict[str, Any]) -> bool:
    new_veracity = new_fact.get('veracity') or 0.0
    conflict_veracity = conflict_fact.get('veracity') or 0.0
    ambiguous = new_veracity < CONFIDENCE_BANDS['medium'] and conflict_veracity >= CONFIDENCE_BANDS['high']
    return ambiguous and impact_score(new_fact, conflict_fact) >= 0.1


def create_review_conflict(
    uid: str,
    *,
    fact: Dict[str, Any],
    conflict_with: List[str],
    source_commit_id: Optional[str] = None,
    source_short_term_id: Optional[str] = None,
    impact: Optional[float] = None,
    ttl_hours: int = 72,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    review_id = f"review:{fact.get('id')}:{','.join(conflict_with)}"
    item = {
        'review_id': review_id,
        'fact_id': fact.get('id'),
        'candidate': fact,
        'conflict_with': conflict_with,
        'veracity': fact.get('veracity'),
        'impact': impact if impact is not None else fact.get('importance', 0.5),
        'status': 'pending',
        'source_commit_id': source_commit_id,
        'source_short_term_id': source_short_term_id,
        'created_at': now,
        'updated_at': now,
        'expires_at': now + timedelta(hours=ttl_hours),
        'permitted_uses': sorted(permitted_uses('pending_review')),
    }
    db.collection(users_collection).document(uid).collection(review_queue_collection).document(review_id).set(item)
    return item


def purge_stale_review_conflicts_for_memories(
    uid: str,
    memory_ids: List[str],
    *,
    reason: str = "source_memory_deleted",
    db_client=None,
) -> List[str]:
    """Drop pending review items that reference tombstoned/superseded/deleted memories."""
    target_ids = {memory_id for memory_id in memory_ids if memory_id}
    if not target_ids:
        return []

    now = datetime.now(timezone.utc)
    purged: List[str] = []
    client = db_client if db_client is not None else db
    users_ref = client.collection(users_collection)
    if hasattr(users_ref, 'document'):
        queue_ref = users_ref.document(uid).collection(review_queue_collection)
    else:
        queue_ref = client.collection(f'{users_collection}/{uid}/{review_queue_collection}')
    for doc in queue_ref.stream():
        item = doc.to_dict() or {}
        if item.get('status') not in ('pending', 'pending_review'):
            continue
        fact_id = item.get('fact_id')
        conflict_with = item.get('conflict_with') or []
        candidate_id = (item.get('candidate') or {}).get('id')
        referenced = {fact_id, candidate_id, *conflict_with}
        referenced.discard(None)
        if not referenced & target_ids:
            continue
        review_id = item.get('review_id') or doc.id
        doc.reference.update(
            {
                'status': 'dropped',
                'decision': 'drop',
                'reason': reason,
                'resolved_at': now,
                'updated_at': now,
            }
        )
        purged.append(review_id)
    return purged


def list_review_conflicts(uid: str, status: str = 'pending', limit: int = 100) -> List[Dict[str, Any]]:
    queue_ref = db.collection(users_collection).document(uid).collection(review_queue_collection)
    items = []
    for doc in queue_ref.stream():
        item = doc.to_dict() or {}
        if status and item.get('status') != status:
            continue
        item.setdefault('review_id', doc.id)
        items.append(item)
    items.sort(key=lambda item: (item.get('impact') or 0.0, item.get('created_at') or datetime.min), reverse=True)
    return items[:limit]


def get_review_conflict(uid: str, review_id: str) -> Optional[Dict[str, Any]]:
    doc = db.collection(users_collection).document(uid).collection(review_queue_collection).document(review_id).get()
    if not doc.exists:
        return None
    item = doc.to_dict() or {}
    item.setdefault('review_id', review_id)
    return item


def timeout_decision(item: Dict[str, Any], current_veracity: float) -> str:
    if current_veracity >= CONFIDENCE_BANDS['high']:
        return 'accept'
    return 'drop'


def accepted_fact(candidate: Dict[str, Any]) -> Dict[str, Any]:
    fact = copy.deepcopy(candidate)
    fact['status'] = 'accepted'
    fact.pop('review_conflict', None)
    qualifiers = fact.setdefault('qualifiers', {})
    qualifiers['status'] = 'accepted'
    qualifiers['epistemic_status'] = 'accepted'
    return fact


def resolution_mutations(
    item: Dict[str, Any], decision: str, correction: Optional[Dict[str, Any]] = None
) -> List[Dict]:
    fact_id = item.get('fact_id')
    candidate = item.get('candidate') or {}
    conflict_with = item.get('conflict_with') or []
    if decision == 'accept':
        return [memory_ledger.add_fact(accepted_fact(candidate))] + [
            memory_ledger.supersede_fact(existing_id, by=fact_id, kind='contradict') for existing_id in conflict_with
        ]
    if decision == 'reject':
        return [memory_ledger.retract_fact(fact_id, reason='review_rejected')]
    if decision == 'correct':
        target_id = (correction or {}).get('target_fact_id') or fact_id
        return [memory_ledger.refine_fact(target_id, (correction or {}).get('arg_changes') or {})]
    return []


def record_correction(
    uid: str,
    *,
    item: Dict[str, Any],
    decision: str,
    prior_head_diff: List[Dict],
    final_correction: Optional[Dict[str, Any]] = None,
    reason: str = '',
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    correction_id = f"correction:{item.get('review_id')}:{decision}"
    record = {
        'correction_id': correction_id,
        'review_id': item.get('review_id'),
        'candidate': item.get('candidate'),
        'evidence_set': (item.get('candidate') or {}).get('evidence', []),
        'prior_head_state': prior_head_diff,
        'final_correction': final_correction or {},
        'decision': decision,
        'reason': reason,
        'created_at': now,
    }
    db.collection(users_collection).document(uid).collection(corrections_collection).document(correction_id).set(record)
    return record


def resolve_review_conflict(
    uid: str,
    review_id: str,
    decision: str,
    *,
    correction: Optional[Dict[str, Any]] = None,
    reason: str = '',
    current_veracity: Optional[float] = None,
) -> Dict[str, Any]:
    item = get_review_conflict(uid, review_id)
    if item is None:
        return {'status': 'not_found', 'commit': None, 'correction': None}
    if item.get('status') not in ('pending', 'pending_review'):
        return {'status': 'already_resolved', 'commit': None, 'correction': None, 'item': item}

    effective_decision = decision
    if decision == 'timeout':
        effective_decision = timeout_decision(
            item, current_veracity if current_veracity is not None else item.get('veracity') or 0.0
        )

    mutations = [] if effective_decision == 'drop' else resolution_mutations(item, effective_decision, correction)
    commit_result = append_resolution_commit(uid, item, effective_decision, correction, mutations)
    _persist_non_active_review_resolution(uid, item, effective_decision, reason, commit_result)

    now = datetime.now(timezone.utc)
    status_by_decision = {
        'accept': 'accepted',
        'reject': 'rejected',
        'correct': 'accepted',
        'drop': 'dropped',
    }
    update = {
        'status': status_by_decision.get(effective_decision, effective_decision),
        'decision': effective_decision,
        'reason': reason,
        'resolved_at': now,
        'updated_at': now,
        'resolution_commit_id': ((commit_result or {}).get('commit') or {}).get('commit_id'),
    }
    db.collection(users_collection).document(uid).collection(review_queue_collection).document(review_id).update(update)
    if item.get('source_short_term_id'):
        short_term_db.mark_consolidated(uid, item['source_short_term_id'], update.get('resolution_commit_id'))

    correction_record = None
    if effective_decision in ('accept', 'reject', 'correct'):
        correction_record = record_correction(
            uid,
            item=item,
            decision=effective_decision,
            prior_head_diff=mutations,
            final_correction=correction,
            reason=reason,
        )

    return {
        'status': 'resolved',
        'decision': effective_decision,
        'commit': (commit_result or {}).get('commit'),
        'correction': correction_record,
        'item': {**item, **update},
    }


def _persist_non_active_review_resolution(
    uid: str,
    item: Dict[str, Any],
    decision: str,
    reason: str,
    commit_result: Optional[Dict[str, Any]],
) -> None:
    route_by_decision = {
        'reject': NonActiveRoute.reject,
        'drop': NonActiveRoute.skip,
    }
    route = route_by_decision.get(decision)
    if route is None:
        return

    review_id = item.get('review_id') or item.get('fact_id') or 'unknown_review'
    resolution_commit_id = ((commit_result or {}).get('commit') or {}).get('commit_id')
    persist_non_active_route_outcome(
        NonActiveRouteOutcome(
            uid=uid,
            route=route,
            idempotency_key=f"review_queue:{review_id}:{decision}",
            source_ids=_review_resolution_source_ids(item),
            reason=reason or f"review_queue_{decision}",
            run_id=f"review_queue:{review_id}",
            patch_id=None,
            audit_metadata={
                'route_store_source': 'review_queue',
                'decision': decision,
                'review_id': review_id,
                'fact_id': item.get('fact_id'),
                'conflict_with': item.get('conflict_with') or [],
                'source_commit_id': item.get('source_commit_id'),
                'source_short_term_id': item.get('source_short_term_id'),
                'resolution_commit_id': resolution_commit_id,
            },
        )
    )


def _review_resolution_source_ids(item: Dict[str, Any]) -> List[str]:
    source_ids = [
        item.get('review_id'),
        item.get('fact_id'),
        item.get('source_commit_id'),
        item.get('source_short_term_id'),
    ]
    candidate = item.get('candidate') or {}
    for evidence in candidate.get('evidence') or candidate.get('evidence_set') or []:
        if isinstance(evidence, dict):
            source_ids.append(evidence.get('evidence_id'))
            source_ids.append(evidence.get('source_id'))
        elif evidence:
            source_ids.append(str(evidence))
    return sorted({source_id for source_id in source_ids if source_id})


def append_resolution_commit(
    uid: str,
    item: Dict[str, Any],
    decision: str,
    correction: Optional[Dict[str, Any]],
    mutations: List[Dict],
) -> Optional[Dict[str, Any]]:
    if decision == 'drop' or not mutations:
        return None
    if decision == 'accept':
        return memories_db.merge_contradict_memory(
            uid,
            accepted_fact(item.get('candidate') or {}),
            item.get('conflict_with') or [],
        )
    if decision == 'correct':
        target_id = (correction or {}).get('target_fact_id') or item.get('fact_id')
        return memories_db.refine_memory(uid, target_id, (correction or {}).get('arg_changes') or {})
    if decision == 'reject':
        now = datetime.now(timezone.utc)
        fact_id = item.get('fact_id')
        memory_ref = db.collection(users_collection).document(uid).collection(memories_collection).document(fact_id)

        def write_projection(transaction):
            snapshot = memory_ref.get(transaction=transaction)
            if snapshot.exists:
                transaction.update(memory_ref, {'invalid_at': now, 'updated_at': now, 'review_status': 'rejected'})

        return memory_ledger.append_commit(
            uid,
            None,
            mutations,
            run_id=f"review_queue:{item.get('review_id')}",
            commit_time=now,
            projection_writer=write_projection,
            use_current_head=True,
        )
    return memory_ledger.append_commit(
        uid,
        None,
        mutations,
        run_id=f"review_queue:{item.get('review_id')}",
        use_current_head=True,
    )


def resolve_expired_review_conflicts(
    uid: str,
    *,
    now: Optional[datetime] = None,
    current_veracity_by_fact: Optional[Dict[str, float]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    current_veracity_by_fact = current_veracity_by_fact or {}
    resolved = []
    for item in list_review_conflicts(uid, status='pending', limit=limit):
        expires_at = item.get('expires_at')
        if expires_at and expires_at > now:
            continue
        fact_id = item.get('fact_id')
        current_veracity = current_veracity_by_fact.get(fact_id, item.get('veracity') or 0.0)
        resolved.append(
            resolve_review_conflict(
                uid,
                item.get('review_id'),
                'timeout',
                current_veracity=current_veracity,
                reason='review_timeout',
            )
        )
    return resolved
