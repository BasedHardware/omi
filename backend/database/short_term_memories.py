"""Legacy shadow short_term collection helpers (data drain only).

Canonical cohort uses memory_items; these helpers remain for historical shadow rows
on cascade conversation delete (tombstone_source) and review-queue resolve (mark_consolidated).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeGuard, cast

from database.store import get_document_store

users_collection = 'users'
short_term_collection = 'short_term'

Payload = Dict[str, Any]


def _store():
    return get_document_store()


def _short_term_path(uid: str) -> str:
    return f'{users_collection}/{uid}/{short_term_collection}'


def _is_payload(value: object) -> TypeGuard[Payload]:
    return isinstance(value, dict)


def mark_consolidated(uid: str, short_term_id: str, commit_id: Optional[str]) -> None:
    store = _store()
    path = f'{_short_term_path(uid)}/{short_term_id}'
    # A conflict's source_short_term_id can point at an absent short-term doc (canonical cohorts write
    # memory_items, not short_term). Update-if-exists (ADR-0021): guard with exists() and no-op on a
    # missing doc instead of relying on an adapter-defined update-on-missing raise.
    if not store.exists(path):
        return
    now = datetime.now(timezone.utc)
    store.update(
        path,
        {
            'status': 'consolidated',
            'consolidated_at': now,
            'consolidated_commit_id': commit_id,
            'soft_pruned_at': now,
            'updated_at': now,
        },
    )


def tombstone_source(uid: str, source_id: str) -> List[str]:
    store = _store()
    now = datetime.now(timezone.utc)
    tombstoned_ids: List[str] = []
    for doc in store.query(_short_term_path(uid)):
        memory = cast(Payload, doc.to_dict() or {})
        raw_evidence: object = memory.get('evidence') or []
        evidence: List[object] = cast(List[object], raw_evidence) if isinstance(raw_evidence, list) else []
        if not any(_is_payload(item) and item.get('source_id') == source_id for item in evidence):
            continue
        tombstoned_evidence: List[object] = []
        for item in evidence:
            if not _is_payload(item):
                tombstoned_evidence.append(item)
                continue
            next_item: Payload = dict(item)
            if next_item.get('source_id') == source_id:
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
        store.update(doc.path, update_payload)
        tombstoned_ids.append(doc.id)
    return tombstoned_ids
