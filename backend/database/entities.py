import copy
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import knowledge_graph as kg_db
from database import memory_ledger
from models.memories import SubjectAttribution

USER_ENTITY_ID = 'user'


def person_entity_id(person_id: str) -> str:
    return f"person:{person_id}"


def stable_entity_id(label: str, entity_type: str = 'concept') -> str:
    normalized = f"{entity_type}:{(label or '').strip().lower()}"
    return f"entity:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"


def resolve_entity_id(
    uid: str,
    *,
    person_id: Optional[str] = None,
    label: Optional[str] = None,
    entity_type: str = 'person',
) -> Optional[str]:
    if person_id:
        entity_id = person_entity_id(person_id)
        kg_db.upsert_knowledge_node(
            uid,
            {
                'id': entity_id,
                'label': label or entity_id,
                'node_type': entity_type,
                'aliases': [label] if label else [],
                'memory_ids': [],
            },
        )
        return entity_id

    if not label:
        return None

    existing = kg_db.find_node_by_label_or_alias(uid, label)
    if existing:
        return existing['id']

    entity_id = stable_entity_id(label, entity_type)
    kg_db.upsert_knowledge_node(
        uid,
        {
            'id': entity_id,
            'label': label,
            'node_type': entity_type,
            'aliases': [],
            'memory_ids': [],
        },
    )
    return entity_id


def apply_entity_mutations(
    entities: Dict[str, Dict[str, Any]], mutations: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    state = copy.deepcopy(entities)
    for item in mutations:
        mutation_type = item.get('type')
        if mutation_type == 'merge_entities':
            _apply_merge(state, item)
        elif mutation_type == 'split_entity':
            _apply_split(state, item)
    return state


def _apply_merge(state: Dict[str, Dict[str, Any]], item: Dict[str, Any]):
    entity_a = item.get('entity_a')
    entity_b = item.get('entity_b')
    if not entity_a or not entity_b or entity_a not in state or entity_b not in state:
        return

    primary = state[entity_a]
    secondary = state.pop(entity_b)
    primary_aliases = set(primary.get('aliases', []))
    primary_aliases.add(secondary.get('label'))
    primary_aliases.update(secondary.get('aliases', []))
    primary['aliases'] = sorted(alias for alias in primary_aliases if alias)
    primary['merged_entity_ids'] = sorted(set(primary.get('merged_entity_ids', [])) | {entity_b})
    primary['updated_at'] = datetime.now(timezone.utc)


def _apply_split(state: Dict[str, Dict[str, Any]], item: Dict[str, Any]):
    entity_id = item.get('entity_id')
    into: List[Dict[str, Any]] = item.get('into') or []
    if entity_id in state:
        state.pop(entity_id)
    for entity in into:
        if entity.get('id'):
            state[entity['id']] = copy.deepcopy(entity)


def merge_entities(
    uid: str,
    entity_a: str,
    entity_b: str,
    *,
    evidence: Optional[Dict[str, Any]] = None,
    confidence: float = 0.5,
):
    user_ref = kg_db.db.collection(kg_db.users_collection).document(uid)
    nodes_ref = user_ref.collection(kg_db.knowledge_nodes_collection)
    entity_a_ref = nodes_ref.document(entity_a)
    entity_b_ref = nodes_ref.document(entity_b)

    def write_projection(transaction: Any) -> None:
        a_snapshot = entity_a_ref.get(transaction=transaction)
        b_snapshot = entity_b_ref.get(transaction=transaction)
        if not a_snapshot.exists or not b_snapshot.exists:
            return
        merged = apply_entity_mutations(
            {entity_a: a_snapshot.to_dict(), entity_b: b_snapshot.to_dict()},
            [memory_ledger.merge_entities(entity_a, entity_b, evidence=evidence, confidence=confidence)],
        )
        if entity_a in merged:
            transaction.set(entity_a_ref, merged[entity_a])
        transaction.delete(entity_b_ref)

    return memory_ledger.append_commit(
        uid,
        None,
        [memory_ledger.merge_entities(entity_a, entity_b, evidence=evidence, confidence=confidence)],
        projection_writer=write_projection,
        use_current_head=True,
    )


def split_entity(uid: str, entity_id: str, into: List[Dict[str, Any]], *, reason: str = ''):
    user_ref = kg_db.db.collection(kg_db.users_collection).document(uid)
    nodes_ref = user_ref.collection(kg_db.knowledge_nodes_collection)
    entity_ref = nodes_ref.document(entity_id)

    def write_projection(transaction: Any) -> None:
        transaction.delete(entity_ref)
        for entity in into:
            if entity.get('id'):
                transaction.set(nodes_ref.document(entity['id']), copy.deepcopy(entity))

    return memory_ledger.append_commit(
        uid,
        None,
        [memory_ledger.split_entity(entity_id, into, reason=reason)],
        projection_writer=write_projection,
        use_current_head=True,
    )


def reassign_fact_subject(uid: str, fact_id: str, old: Optional[str], new: Optional[str]):
    memory_ref = kg_db.db.collection(kg_db.users_collection).document(uid).collection('memories').document(fact_id)
    if new == USER_ENTITY_ID:
        attribution = SubjectAttribution.user
    elif new and new.startswith('person:'):
        attribution = SubjectAttribution.third_party
    else:
        attribution = SubjectAttribution.unknown

    def write_projection(transaction: Any) -> None:
        transaction.update(
            memory_ref,
            {
                'subject_entity_id': new,
                'subject_attribution': attribution.value,
                'updated_at': datetime.now(timezone.utc),
            },
        )

    return memory_ledger.append_commit(
        uid,
        None,
        [memory_ledger.reassign_fact_subject(fact_id, old, new)],
        projection_writer=write_projection,
        use_current_head=True,
    )
