import copy
import hashlib
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import knowledge_graph as kg_db
from database import memory_ledger
from models.memories import SubjectAttribution

USER_ENTITY_ID = 'user'


def person_entity_id(person_id: str) -> str:
    try:
        clean = person_id.strip()
    except (AttributeError, TypeError):
        raise ValueError("person_id must be a non-empty string")
    if not clean:
        raise ValueError("person_id must be a non-empty string")
    return f"person:{clean}"


def stable_entity_id(label: str, entity_type: str = 'concept') -> str:
    try:
        clean_label = (label or '').strip().lower()
        clean_type = (entity_type or 'concept').strip().lower()
    except (AttributeError, TypeError):
        raise ValueError("label must be a non-empty string")
    if not clean_label:
        raise ValueError("label must be a non-empty string")
    normalized = f"{clean_type}:{clean_label}"
    return f"entity:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"


def resolve_entity_id(
    uid: str,
    *,
    person_id: Optional[str] = None,
    label: Optional[str] = None,
    entity_type: str = 'person',
) -> Optional[str]:
    try:
        clean_uid = uid.strip()
    except (AttributeError, TypeError):
        return None
    if not clean_uid:
        return None

    clean_person_id = person_id.strip() if person_id and hasattr(person_id, 'strip') else None
    if clean_person_id:
        entity_id = person_entity_id(clean_person_id)
        clean_label = (label or '').strip() if label and hasattr(label, 'strip') else entity_id
        kg_db.upsert_knowledge_node(
            clean_uid,
            {
                'id': entity_id,
                'label': clean_label or entity_id,
                'node_type': entity_type,
                'aliases': [clean_label] if clean_label else [],
                'memory_ids': [],
            },
        )
        return entity_id

    clean_label = label.strip() if label and hasattr(label, 'strip') else None
    if not clean_label:
        return None

    existing = kg_db.find_node_by_label_or_alias(clean_uid, clean_label)
    if existing and hasattr(existing, 'get') and existing.get('id'):
        return existing['id']

    entity_id = stable_entity_id(clean_label, entity_type)
    kg_db.upsert_knowledge_node(
        clean_uid,
        {
            'id': entity_id,
            'label': clean_label,
            'node_type': entity_type,
            'aliases': [],
            'memory_ids': [],
        },
    )
    return entity_id


def apply_entity_mutations(
    entities: Dict[str, Dict[str, Any]], mutations: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    if not entities or not hasattr(entities, 'items'):
        return {}
    state = copy.deepcopy(entities)
    if not mutations or not hasattr(mutations, '__iter__') or hasattr(mutations, 'items'):
        return state
    for item in mutations:
        if not item or not hasattr(item, 'get'):
            continue
        mutation_type = item.get('type')
        if mutation_type == 'merge_entities':
            _apply_merge(state, item)
        elif mutation_type == 'split_entity':
            _apply_split(state, item)
    return state


def _apply_merge(state: Dict[str, Dict[str, Any]], item: Dict[str, Any]):
    entity_a = item.get('entity_a')
    entity_b = item.get('entity_b')
    if not entity_a or not entity_b or entity_a == entity_b or entity_a not in state or entity_b not in state:
        return

    primary = state[entity_a]
    secondary = state.pop(entity_b)
    if not primary or not hasattr(primary, 'get'):
        primary = {}
        state[entity_a] = primary
    if not secondary or not hasattr(secondary, 'get'):
        secondary = {}

    primary_aliases = set(primary.get('aliases', [])) if hasattr(primary.get('aliases'), '__iter__') else set()
    if secondary.get('label'):
        primary_aliases.add(secondary.get('label'))
    if hasattr(secondary.get('aliases'), '__iter__'):
        primary_aliases.update(secondary.get('aliases', []))
    primary['aliases'] = sorted(alias for alias in primary_aliases if alias)

    current_merged = (
        set(primary.get('merged_entity_ids', [])) if hasattr(primary.get('merged_entity_ids'), '__iter__') else set()
    )
    primary['merged_entity_ids'] = sorted(current_merged | {entity_b})
    primary['updated_at'] = datetime.now(timezone.utc)


def _apply_split(state: Dict[str, Dict[str, Any]], item: Dict[str, Any]):
    entity_id = item.get('entity_id')
    into = item.get('into')
    if not entity_id or not into:
        return
    valid_into = (
        [e for e in into if hasattr(e, 'get') and e.get('id')]
        if hasattr(into, '__iter__') and not hasattr(into, 'items')
        else []
    )
    if not valid_into:
        return
    if entity_id in state:
        state.pop(entity_id)
    for entity in valid_into:
        state[entity['id']] = copy.deepcopy(entity)


def merge_entities(
    uid: str,
    entity_a: str,
    entity_b: str,
    *,
    evidence: Optional[Dict[str, Any]] = None,
    confidence: float = 0.5,
):
    try:
        clean_uid = uid.strip()
    except (AttributeError, TypeError):
        clean_uid = ''
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")

    try:
        clean_a = entity_a.strip()
    except (AttributeError, TypeError):
        clean_a = ''
    if not clean_a:
        raise ValueError("entity_a must be a non-empty string")

    try:
        clean_b = entity_b.strip()
    except (AttributeError, TypeError):
        clean_b = ''
    if not clean_b:
        raise ValueError("entity_b must be a non-empty string")

    if clean_a == clean_b:
        raise ValueError("Cannot merge an entity into itself")

    try:
        conf_val = float(confidence)
        if not math.isfinite(conf_val):
            conf_val = 0.5
        else:
            conf_val = max(0.0, min(conf_val, 1.0))
    except (ValueError, TypeError):
        conf_val = 0.5

    clean_evidence = evidence if evidence and hasattr(evidence, 'items') else None

    user_ref = kg_db.db.collection(kg_db.users_collection).document(clean_uid)
    nodes_ref = user_ref.collection(kg_db.knowledge_nodes_collection)
    entity_a_ref = nodes_ref.document(clean_a)
    entity_b_ref = nodes_ref.document(clean_b)

    def write_projection(transaction: Any) -> None:
        a_snapshot = entity_a_ref.get(transaction=transaction)
        b_snapshot = entity_b_ref.get(transaction=transaction)
        if not a_snapshot.exists or not b_snapshot.exists:
            return
        a_dict = a_snapshot.to_dict() or {}
        b_dict = b_snapshot.to_dict() or {}
        merged = apply_entity_mutations(
            {clean_a: a_dict, clean_b: b_dict},
            [memory_ledger.merge_entities(clean_a, clean_b, evidence=clean_evidence, confidence=conf_val)],
        )
        if clean_a in merged:
            transaction.set(entity_a_ref, merged[clean_a])
        transaction.delete(entity_b_ref)

    return memory_ledger.append_commit(
        clean_uid,
        None,
        [memory_ledger.merge_entities(clean_a, clean_b, evidence=clean_evidence, confidence=conf_val)],
        projection_writer=write_projection,
        use_current_head=True,
    )


def split_entity(uid: str, entity_id: str, into: List[Dict[str, Any]], *, reason: str = ''):
    try:
        clean_uid = uid.strip()
    except (AttributeError, TypeError):
        clean_uid = ''
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")

    try:
        clean_id = entity_id.strip()
    except (AttributeError, TypeError):
        clean_id = ''
    if not clean_id:
        raise ValueError("entity_id must be a non-empty string")

    if not into or not hasattr(into, '__iter__') or hasattr(into, 'items'):
        raise ValueError("into must be a non-empty list of entity dicts")
    valid_into = [e for e in into if hasattr(e, 'get') and e.get('id')]
    if not valid_into:
        raise ValueError("into must contain at least one valid entity dict with an 'id'")

    user_ref = kg_db.db.collection(kg_db.users_collection).document(clean_uid)
    nodes_ref = user_ref.collection(kg_db.knowledge_nodes_collection)
    entity_ref = nodes_ref.document(clean_id)

    def write_projection(transaction: Any) -> None:
        transaction.delete(entity_ref)
        for entity in valid_into:
            transaction.set(nodes_ref.document(entity['id']), copy.deepcopy(entity))

    return memory_ledger.append_commit(
        clean_uid,
        None,
        [memory_ledger.split_entity(clean_id, valid_into, reason=str(reason or ''))],
        projection_writer=write_projection,
        use_current_head=True,
    )


def reassign_fact_subject(uid: str, fact_id: str, old: Optional[str], new: Optional[str]):
    try:
        clean_uid = uid.strip()
    except (AttributeError, TypeError):
        clean_uid = ''
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")

    try:
        clean_fact_id = fact_id.strip()
    except (AttributeError, TypeError):
        clean_fact_id = ''
    if not clean_fact_id:
        raise ValueError("fact_id must be a non-empty string")

    clean_old = old.strip() if old and hasattr(old, 'strip') and old.strip() else None
    clean_new = new.strip() if new and hasattr(new, 'strip') and new.strip() else None

    memory_ref = (
        kg_db.db.collection(kg_db.users_collection).document(clean_uid).collection('memories').document(clean_fact_id)
    )
    if clean_new == USER_ENTITY_ID:
        attribution = SubjectAttribution.user
    elif clean_new and clean_new.startswith('person:'):
        attribution = SubjectAttribution.third_party
    else:
        attribution = SubjectAttribution.unknown

    def write_projection(transaction: Any) -> None:
        transaction.update(
            memory_ref,
            {
                'subject_entity_id': clean_new,
                'subject_attribution': attribution.value,
                'updated_at': datetime.now(timezone.utc),
            },
        )

    return memory_ledger.append_commit(
        clean_uid,
        None,
        [memory_ledger.reassign_fact_subject(clean_fact_id, clean_old, clean_new)],
        projection_writer=write_projection,
        use_current_head=True,
    )
