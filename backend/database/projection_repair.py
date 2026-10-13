from typing import Any, Dict, Iterable, List, Optional, Set, cast

PROJECTION_VERSION = 1


def _qualifiers(fact: Dict[str, Any]) -> Dict[str, Any]:
    """Narrow the optional qualifiers dict on a fact document."""
    raw = fact.get('qualifiers')
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


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


def _entity_ids(fact: Dict[str, Any]) -> List[str]:
    entity_ids: List[str] = []
    subject = fact.get('subject_entity_id')
    if subject:
        entity_ids.append(subject)
    for entity_id in cast(Iterable[Any], fact.get('object_entity_ids') or []):
        if entity_id and entity_id not in entity_ids:
            entity_ids.append(entity_id)
    return entity_ids
