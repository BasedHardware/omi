from datetime import datetime, timezone
from typing import Dict, List, Optional

from google.cloud.firestore_v1 import FieldFilter

from ._client import db

users_collection = 'users'
short_term_collection = 'short_term'


def save_short_term_memories(uid: str, memories: List[dict]):
    if not memories:
        return
    batch = db.batch()
    collection_ref = db.collection(users_collection).document(uid).collection(short_term_collection)
    for memory in memories:
        batch.set(collection_ref.document(memory['id']), memory)
    batch.commit()


def get_short_term_memories(
    uid: str,
    *,
    status: Optional[str] = None,
    include_soft_pruned: bool = False,
    limit: int = 100,
) -> List[Dict]:
    collection_ref = db.collection(users_collection).document(uid).collection(short_term_collection)
    if status:
        collection_ref = collection_ref.where(filter=FieldFilter('status', '==', status))
    collection_ref = collection_ref.order_by('created_at').limit(limit)
    rows = [doc.to_dict() for doc in collection_ref.stream()]
    if include_soft_pruned:
        return rows
    return [row for row in rows if row.get('soft_pruned_at') is None]


def mark_consolidated(uid: str, short_term_id: str, commit_id: Optional[str]):
    doc_ref = db.collection(users_collection).document(uid).collection(short_term_collection).document(short_term_id)
    now = datetime.now(timezone.utc)
    doc_ref.update(
        {
            'status': 'consolidated',
            'consolidated_at': now,
            'consolidated_commit_id': commit_id,
            'soft_pruned_at': now,
            'updated_at': now,
        }
    )


def mark_pending_review(uid: str, short_term_id: str, review_conflict: Dict):
    doc_ref = db.collection(users_collection).document(uid).collection(short_term_collection).document(short_term_id)
    now = datetime.now(timezone.utc)
    doc_ref.update(
        {
            'status': 'pending_review',
            'review_conflict': review_conflict,
            'updated_at': now,
        }
    )


def tombstone_source(uid: str, source_id: str) -> List[str]:
    collection_ref = db.collection(users_collection).document(uid).collection(short_term_collection)
    now = datetime.now(timezone.utc)
    tombstoned_ids = []
    for doc in collection_ref.stream():
        memory = doc.to_dict() or {}
        evidence = memory.get('evidence') or []
        if not any(isinstance(item, dict) and item.get('source_id') == source_id for item in evidence):
            continue
        tombstoned_evidence = []
        for item in evidence:
            if not isinstance(item, dict):
                tombstoned_evidence.append(item)
                continue
            next_item = dict(item)
            if next_item.get('source_id') == source_id:
                next_item['redaction_status'] = 'tombstoned'
                next_item['tombstoned_at'] = now
            tombstoned_evidence.append(next_item)
        active_evidence = [
            item
            for item in tombstoned_evidence
            if isinstance(item, dict) and item.get('redaction_status', 'active') != 'tombstoned'
        ]
        update_payload = {'evidence': tombstoned_evidence, 'updated_at': now}
        if not active_evidence:
            update_payload.update(
                {
                    'status': 'source_tombstoned',
                    'soft_pruned_at': now,
                    'content': None,
                    'redaction_status': 'payload_tombstoned',
                }
            )
        doc.reference.update(update_payload)
        tombstoned_ids.append(doc.id)
    return tombstoned_ids


def to_retrieval_record(memory: Dict) -> Dict:
    return {
        'id': memory.get('id'),
        'content': memory.get('content'),
        'evidence_refs': [item.get('artifact_ref') for item in memory.get('evidence', []) if isinstance(item, dict)],
        'valid_time': (memory.get('qualifiers') or {}).get('valid_from'),
        'scope': memory.get('scope', 'global'),
        'status': memory.get('status', 'pending_consolidation'),
        'capture_confidence': memory.get('capture_confidence'),
        'veracity': memory.get('veracity'),
        'importance': (memory.get('qualifiers') or {}).get('importance'),
        'allowed_uses': memory.get('allowed_uses', []),
        'source': 'short_term',
    }
