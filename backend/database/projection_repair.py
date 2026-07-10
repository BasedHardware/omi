from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, cast

from ._client import db

users_collection = 'users'
projection_repairs_collection = 'projection_repairs'
PROJECTION_VERSION = 1

DANGEROUS_REASONS = {'retract_fact', 'tombstone_evidence', 'source_tombstoned'}
TERMINAL_REPAIR_STATUSES = {'repaired', 'dead_letter'}
PROCESSABLE_REPAIR_STATUSES = ('queued', 'failed')


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for Firestore DocumentSnapshot.to_dict() (SDK stub gap)."""
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _qualifiers(fact: Dict[str, Any]) -> Dict[str, Any]:
    """Narrow the optional qualifiers dict on a fact document."""
    raw = fact.get('qualifiers')
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def affected_fact_ids(mutations: List[Dict[str, Any]]) -> List[str]:
    fact_ids: List[str] = []
    for mutation in mutations or []:
        fact_id = mutation.get('fact_id')
        if not fact_id:
            fact = mutation.get('fact')
            if isinstance(fact, dict):
                fact_id = cast(Dict[str, Any], fact).get('id')
        if fact_id and fact_id not in fact_ids:
            fact_ids.append(fact_id)
    return fact_ids


def repair_reason(mutation: Dict[str, Any]) -> str:
    mutation_type = mutation.get('type', 'unknown')
    if mutation_type == 'retract_fact' and mutation.get('reason') == 'source_tombstoned':
        return 'source_tombstoned'
    return mutation_type


def enqueue_projection_repairs(
    uid: str, commit: Optional[Dict[str, Any]], *, firestore_client: Any = None
) -> List[str]:
    if not commit:
        return []
    mutations: List[Dict[str, Any]] = commit.get('mutations') or []
    fact_ids = affected_fact_ids(mutations)
    if not fact_ids:
        return []

    now = datetime.now(timezone.utc)
    database: Any = firestore_client or db
    batch: Any = database.batch()
    collection_ref: Any = database.collection(users_collection).document(uid).collection(projection_repairs_collection)
    repair_ids: List[str] = []
    reasons_by_fact = _reasons_by_fact(mutations)
    for fact_id in fact_ids:
        reasons = reasons_by_fact.get(fact_id, ['unknown'])
        repair_id = f"{commit.get('commit_id')}:{fact_id}"
        repair_ids.append(repair_id)
        document_ref: Any = collection_ref.document(repair_id)
        existing: Any = document_ref.get()
        if getattr(existing, 'exists', False):
            continue
        batch.set(
            document_ref,
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
    firestore_client: Any = None,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    if limit < 1:
        raise ValueError('limit must be positive')
    if max_attempts < 1:
        raise ValueError('max_attempts must be positive')

    database: Any = firestore_client or db
    collection_ref: Any = database.collection(users_collection).document(uid).collection(projection_repairs_collection)
    repaired: List[str] = []
    failed: List[str] = []
    seen_doc_ids: Set[Any] = set()
    docs: List[Any] = []
    for status in PROCESSABLE_REPAIR_STATUSES:
        for doc in collection_ref.where('status', '==', status).limit(limit).stream():
            doc_id = getattr(doc, 'id', None)
            if doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            docs.append(doc)
            if len(docs) >= limit:
                break
        if len(docs) >= limit:
            break

    for doc in docs:
        repair: Dict[str, Any] = _typed_doc(doc)
        fact_id = repair.get('fact_id')
        try:
            action = repair_func(uid, fact_loader(cast(str, fact_id)))
            doc.reference.update(
                {
                    'status': 'repaired',
                    'repair_action': action,
                    'updated_at': datetime.now(timezone.utc),
                }
            )
            repaired.append(repair.get('repair_id') or doc.id)
        except Exception as exc:
            next_attempt_count = int(repair.get('attempt_count') or 0) + 1
            next_status = 'dead_letter' if next_attempt_count >= max_attempts else 'failed'
            doc.reference.update(
                {
                    'status': next_status,
                    'attempt_count': next_attempt_count,
                    'error': str(exc),
                    'updated_at': datetime.now(timezone.utc),
                }
            )
            failed.append(repair.get('repair_id') or doc.id)
    return {'repaired': repaired, 'failed': failed, 'processed': len(repaired) + len(failed)}


def projection_metadata_for_fact(fact: Dict[str, Any], source_commit_id: Optional[str] = None) -> Dict[str, Any]:
    qualifiers = _qualifiers(fact)
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
    qualifiers = _qualifiers(fact)
    status = fact.get('status') or qualifiers.get('status')
    if fact.get('invalid_at') is not None:
        return 'delete'
    if fact.get('redaction_status') in ('payload_tombstoned', 'pending_tombstone'):
        return 'delete'
    if status == 'pending_review':
        return 'upsert_pending'
    return 'upsert'


def reconcile_memory_projection(uid: str, facts: List[Dict[str, Any]], vector_fact_ids: List[str]) -> Dict[str, Any]:
    facts_by_id: Dict[str, Dict[str, Any]] = {}
    for fact in facts:
        fact_id = fact.get('id')
        if fact_id:
            facts_by_id[cast(str, fact_id)] = fact
    expected_active: Set[str] = {
        fact_id for fact_id, fact in facts_by_id.items() if projection_action_for_fact(fact).startswith('upsert')
    }
    actual: Set[str] = set(vector_fact_ids)
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
        fact_id = mutation.get('fact_id')
        if not fact_id:
            fact = mutation.get('fact')
            if isinstance(fact, dict):
                fact_id = cast(Dict[str, Any], fact).get('id')
        if not fact_id:
            continue
        reasons.setdefault(fact_id, [])
        reason = repair_reason(mutation)
        if reason not in reasons[fact_id]:
            reasons[fact_id].append(reason)
    return reasons


def _entity_ids(fact: Dict[str, Any]) -> List[str]:
    entity_ids: List[str] = []
    subject = fact.get('subject_entity_id')
    if subject:
        entity_ids.append(subject)
    for entity_id in cast(Iterable[Any], fact.get('object_entity_ids') or []):
        if entity_id and entity_id not in entity_ids:
            entity_ids.append(entity_id)
    return entity_ids
