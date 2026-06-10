from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ._client import db

users_collection = 'users'
projection_repairs_collection = 'projection_repairs'
PROJECTION_VERSION = 1

DANGEROUS_REASONS = {'retract_fact', 'tombstone_evidence', 'source_tombstoned'}


def affected_fact_ids(mutations: List[Dict[str, Any]]) -> List[str]:
    fact_ids = []
    for mutation in mutations or []:
        fact_id = mutation.get('fact_id') or (mutation.get('fact') or {}).get('id')
        if fact_id and fact_id not in fact_ids:
            fact_ids.append(fact_id)
    return fact_ids


def repair_reason(mutation: Dict[str, Any]) -> str:
    mutation_type = mutation.get('type', 'unknown')
    if mutation_type == 'retract_fact' and mutation.get('reason') == 'source_tombstoned':
        return 'source_tombstoned'
    return mutation_type


def enqueue_projection_repairs(uid: str, commit: Optional[Dict[str, Any]]) -> List[str]:
    if not commit:
        return []
    mutations = commit.get('mutations') or []
    fact_ids = affected_fact_ids(mutations)
    if not fact_ids:
        return []

    now = datetime.now(timezone.utc)
    batch = db.batch()
    collection_ref = db.collection(users_collection).document(uid).collection(projection_repairs_collection)
    repair_ids = []
    reasons_by_fact = _reasons_by_fact(mutations)
    for fact_id in fact_ids:
        reasons = reasons_by_fact.get(fact_id, ['unknown'])
        repair_id = f"{commit.get('commit_id')}:{fact_id}"
        repair_ids.append(repair_id)
        batch.set(
            collection_ref.document(repair_id),
            {
                'repair_id': repair_id,
                'fact_id': fact_id,
                'source_commit_id': commit.get('commit_id'),
                'projection_version': PROJECTION_VERSION,
                'reasons': reasons,
                'dangerous': any(reason in DANGEROUS_REASONS for reason in reasons),
                'status': 'queued',
                'created_at': now,
                'updated_at': now,
            },
        )
    batch.commit()
    return repair_ids


def process_projection_repairs(
    uid: str,
    *,
    fact_loader: Callable[[str], Optional[Dict[str, Any]]],
    repair_func: Callable[[str, Optional[Dict[str, Any]]], str],
    limit: int = 100,
) -> Dict[str, Any]:
    collection_ref = db.collection(users_collection).document(uid).collection(projection_repairs_collection)
    queued_docs = collection_ref.where('status', '==', 'queued').limit(limit).stream()
    repaired = []
    failed = []
    for doc in queued_docs:
        repair = doc.to_dict() or {}
        fact_id = repair.get('fact_id')
        try:
            action = repair_func(uid, fact_loader(fact_id))
            doc.reference.update(
                {
                    'status': 'repaired',
                    'repair_action': action,
                    'updated_at': datetime.now(timezone.utc),
                }
            )
            repaired.append(repair.get('repair_id') or doc.id)
        except Exception as exc:
            doc.reference.update(
                {
                    'status': 'failed',
                    'error': str(exc),
                    'updated_at': datetime.now(timezone.utc),
                }
            )
            failed.append(repair.get('repair_id') or doc.id)
    return {'repaired': repaired, 'failed': failed, 'processed': len(repaired) + len(failed)}


def projection_metadata_for_fact(fact: Dict[str, Any], source_commit_id: Optional[str] = None) -> Dict[str, Any]:
    qualifiers = fact.get('qualifiers') or {}
    return {
        'fact_id': fact.get('id'),
        'memory_id': fact.get('id'),
        'source_commit_id': source_commit_id,
        'projection_version': PROJECTION_VERSION,
        'entity_ids': _entity_ids(fact),
        'valid_time': qualifiers.get('valid_from') or fact.get('valid_at'),
        'scope': qualifiers.get('scope') or fact.get('scope') or 'global',
        'epistemic_status': fact.get('status') or qualifiers.get('status') or 'accepted',
        'source_tombstone_state': fact.get('redaction_status', 'active'),
    }


def projection_action_for_fact(fact: Dict[str, Any]) -> str:
    status = fact.get('status') or (fact.get('qualifiers') or {}).get('status')
    if fact.get('invalid_at') is not None:
        return 'delete'
    if fact.get('redaction_status') in ('payload_tombstoned', 'pending_tombstone'):
        return 'delete'
    if status == 'pending_review':
        return 'upsert_pending'
    return 'upsert'


def reconcile_memory_projection(uid: str, facts: List[Dict[str, Any]], vector_fact_ids: List[str]) -> Dict[str, Any]:
    facts_by_id = {fact.get('id'): fact for fact in facts if fact.get('id')}
    expected_active = {
        fact_id for fact_id, fact in facts_by_id.items() if projection_action_for_fact(fact).startswith('upsert')
    }
    actual = set(vector_fact_ids)
    missing = sorted(expected_active - actual)
    stale = sorted(actual - expected_active)
    return {
        'uid': uid,
        'missing_upserts': missing,
        'stale_deletes': stale,
        'drift_count': len(missing) + len(stale),
        'projection_fail_count': 0 if not missing and not stale else len(missing) + len(stale),
    }


def _reasons_by_fact(mutations: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    reasons: Dict[str, List[str]] = {}
    for mutation in mutations:
        fact_id = mutation.get('fact_id') or (mutation.get('fact') or {}).get('id')
        if not fact_id:
            continue
        reasons.setdefault(fact_id, [])
        reason = repair_reason(mutation)
        if reason not in reasons[fact_id]:
            reasons[fact_id].append(reason)
    return reasons


def _entity_ids(fact: Dict[str, Any]) -> List[str]:
    entity_ids = []
    if fact.get('subject_entity_id'):
        entity_ids.append(fact['subject_entity_id'])
    for entity_id in fact.get('object_entity_ids') or []:
        if entity_id and entity_id not in entity_ids:
            entity_ids.append(entity_id)
    return entity_ids
