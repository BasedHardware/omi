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
    if not person_id or not isinstance(person_id, str) or not person_id.strip():
        raise ValueError("person_id must be a non-empty string")
    return f"person:{person_id.strip()}"


def stable_entity_id(label: str, entity_type: str = 'concept') -> str:
    clean_label = (label or '').strip().lower()
    clean_type = (entity_type or 'concept').strip().lower()
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
    if not uid or not isinstance(uid, str) or not uid.strip():
        return None
    clean_uid = uid.strip()

    if person_id and isinstance(person_id, str) and person_id.strip():
        entity_id = person_entity_id(person_id.strip())
        clean_label = (label or '').strip() or entity_id
        kg_db.upsert_knowledge_node(
            clean_uid,
            {
                'id': entity_id,
                'label': clean_label,
                'node_type': entity_type,
                'aliases': [clean_label] if clean_label else [],
                'memory_ids': [],
            },
        )
        return entity_id

    if not label or not isinstance(label, str) or not label.strip():
        return None
    clean_label = label.strip()

    existing = kg_db.find_node_by_label_or_alias(clean_uid, clean_label)
    if existing and isinstance(existing, dict) and existing.get('id'):
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
    if not isinstance(entities, dict):
        return {}
    state = copy.deepcopy(entities)
    if not isinstance(mutations, (list, tuple)):
        return state
    for item in mutations:
        if not isinstance(item, dict):
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
    if not isinstance(primary, dict):
        primary = {}
        state[entity_a] = primary
    if not isinstance(secondary, dict):
        secondary = {}

    primary_aliases = set(primary.get('aliases', [])) if isinstance(primary.get('aliases'), (list, set, tuple)) else set()
    if secondary.get('label'):
        primary_aliases.add(secondary.get('label'))
    if isinstance(secondary.get('aliases'), (list, set, tuple)):
        primary_aliases.update(secondary.get('aliases', []))
    primary['aliases'] = sorted(alias for alias in primary_aliases if alias)

    current_merged = set(primary.get('merged_entity_ids', [])) if isinstance(primary.get('merged_entity_ids'), (list, set, tuple)) else set()
    primary['merged_entity_ids'] = sorted(current_merged | {entity_b})
    primary['updated_at'] = datetime.now(timezone.utc)


def _apply_split(state: Dict[str, Dict[str, Any]], item: Dict[str, Any]):
    entity_id = item.get('entity_id')
    into: List[Dict[str, Any]] = item.get('into') or []
    if not entity_id or not into or not isinstance(into, (list, tuple)):
        return
    valid_into = [e for e in into if isinstance(e, dict) and e.get('id')]
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
    if not uid or not isinstance(uid, str) or not uid.strip():
        raise ValueError("uid must be a non-empty string")
    if not entity_a or not isinstance(entity_a, str) or not entity_a.strip():
        raise ValueError("entity_a must be a non-empty string")
    if not entity_b or not isinstance(entity_b, str) or not entity_b.strip():
        raise ValueError("entity_b must be a non-empty string")
    clean_uid = uid.strip()
    clean_a = entity_a.strip()
    clean_b = entity_b.strip()
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

    clean_evidence = evidence if isinstance(evidence, dict) else None

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
    if not uid or not isinstance(uid, str) or not uid.strip():
        raise ValueError("uid must be a non-empty string")
    if not entity_id or not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("entity_id must be a non-empty string")
    if not into or not isinstance(into, (list, tuple)):
        raise ValueError("into must be a non-empty list of entity dicts")
    clean_uid = uid.strip()
    clean_id = entity_id.strip()
    valid_into = [e for e in into if isinstance(e, dict) and e.get('id')]
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
    if not uid or not isinstance(uid, str) or not uid.strip():
        raise ValueError("uid must be a non-empty string")
    if not fact_id or not isinstance(fact_id, str) or not fact_id.strip():
        raise ValueError("fact_id must be a non-empty string")
    clean_uid = uid.strip()
    clean_fact_id = fact_id.strip()
    clean_old = old.strip() if isinstance(old, str) and old.strip() else None
    clean_new = new.strip() if isinstance(new, str) and new.strip() else None

    memory_ref = kg_db.db.collection(kg_db.users_collection).document(clean_uid).collection('memories').document(clean_fact_id)
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
