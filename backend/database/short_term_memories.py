"""Legacy shadow short_term collection helpers (data drain only).

The universal runtime uses memory_items; these helpers remain for historical shadow rows
on cascade conversation delete (tombstone_source) and review-queue resolve (mark_consolidated).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeGuard, cast

from google.api_core.exceptions import NotFound

from ._client import db

users_collection = 'users'
short_term_collection = 'short_term'

Payload = Dict[str, Any]


def _is_payload(value: object) -> TypeGuard[Payload]:
    return isinstance(value, dict)


def mark_consolidated(uid: str, short_term_id: str, commit_id: Optional[str]) -> None:
    if (
        not uid
        or not isinstance(uid, str)
        or not uid.strip()
        or not short_term_id
        or not isinstance(short_term_id, str)
        or not short_term_id.strip()
    ):
        return
    clean_uid = uid.strip()
    clean_short_term_id = short_term_id.strip()
    doc_ref = (
        db.collection(users_collection)
        .document(clean_uid)
        .collection(short_term_collection)
        .document(clean_short_term_id)
    )
    # A conflict's source_short_term_id can point at an absent short-term doc (the universal runtime writes
    # memory_items, not short_term). Firestore .update() raises NotFound on a missing doc (unlike set),
    # which would surface as a 500 on resolve; no-op instead, mirroring memory_app_key_grants.
    try:
        if not doc_ref.get().exists:
            return
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
    except NotFound:
        return


def tombstone_source(uid: str, source_id: str) -> List[str]:
    if (
        not uid
        or not isinstance(uid, str)
        or not uid.strip()
        or not source_id
        or not isinstance(source_id, str)
        or not source_id.strip()
    ):
        return []
    clean_uid = uid.strip()
    clean_source_id = source_id.strip()
    collection_ref = db.collection(users_collection).document(clean_uid).collection(short_term_collection)
    now = datetime.now(timezone.utc)
    tombstoned_ids: List[str] = []
    for doc in collection_ref.stream():
        memory = cast(Payload, doc.to_dict() or {})
        raw_evidence: object = memory.get('evidence') or []
        evidence: List[object] = cast(List[object], raw_evidence) if isinstance(raw_evidence, list) else []
        if not any(_is_payload(item) and item.get('source_id') == clean_source_id for item in evidence):
            continue
        tombstoned_evidence: List[object] = []
        for item in evidence:
            if not _is_payload(item):
                tombstoned_evidence.append(item)
                continue
            next_item: Payload = dict(item)
            if next_item.get('source_id') == clean_source_id:
                next_item['redaction_status'] = 'tombstoned'
                next_item['tombstoned_at'] = now
            tombstoned_evidence.append(next_item)
        active_evidence: List[Payload] = [
            item
            for item in tombstoned_evidence
            if _is_payload(item) and item.get('redaction_status', 'active') != 'tombstoned'
        ]
        update_payload: Payload = {'evidence': tombstoned_evidence, 'updated_at': now}
        if not active_evidence:
            update_payload.update(
                {
                    'status': 'source_tombstoned',
                    'soft_pruned_at': now,
                    'content': None,
                    'redaction_status': 'payload_tombstoned',
                }
            )
        try:
            doc.reference.update(update_payload)
            tombstoned_ids.append(doc.id)
        except NotFound:
            continue
    return tombstoned_ids
