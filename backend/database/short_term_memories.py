"""Legacy shadow short_term collection helpers (data drain only).

Canonical cohort uses memory_items; these helpers remain for historical shadow rows
on cascade conversation delete (tombstone_source) and review-queue resolve (mark_consolidated).
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from ._client import db

users_collection = 'users'
short_term_collection = 'short_term'


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
