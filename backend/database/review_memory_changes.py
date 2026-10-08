"""Canonical fact replacement journal; history is reversed by append/supersede.

The canonical apply owns its ledger, lineage, privacy and outboxes. A durable
intent is written before it; a stable provenance action makes interrupted
applications recoverable without ever writing legacy memory projections.
"""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from google.cloud import firestore
from pydantic import BaseModel, Field

from database import review_store as store
from models.review import ReviewChange


class MemoryEdit(BaseModel):
    memory_id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    content: str = Field(min_length=1, max_length=2000)


def record_memory_change(uid: str, change: ReviewChange, edit: MemoryEdit, edit_key: str) -> ReviewChange:
    from models.product_memory import LedgerWriteReason, MemorySubjectScope
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item
    from utils.memory.knowledge_ledger import LedgerProvenance, amend_fact

    ref = store.user(uid).collection('review_changes').document(store.safe_id(change.change_id))
    marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(edit_key))
    current = read_canonical_memory_item(uid, edit.memory_id, db_client=store.client())

    @firestore.transactional
    def prepare(tx):
        raw = ref.get(transaction=tx).to_dict()
        blocked = marker.get(transaction=tx).exists
        if raw:
            data = store.decode_doc(uid, raw)
            if data['edit_key'] != edit_key or data['memory_edit'] != edit.model_dump():
                raise store.ReviewConflict('Change identity conflict')
            return data
        if blocked or current is None:
            raise store.ReviewConflict('Memory unavailable or operation was undone')
        if current.ledger_schema_version != 'knowledge_ledger.v1' or current.kind.value != 'fact':
            raise store.ReviewConflict('Only canonical knowledge ledger facts may be replaced')
        data = {
            'change': change.model_dump(mode='python'),
            'created_at': change.created_at,
            'edit_key': edit_key,
            'memory_edit': edit.model_dump(),
            'before': current.model_dump(mode='python'),
            'phase': 'applying',
        }
        tx.set(ref, store.encode_doc(uid, data))
        return data

    data = prepare(store.client().transaction())
    if data['phase'] == 'applied':
        return ReviewChange.model_validate(data['change'])
    # The source snapshot fences an intervening correction in canonical apply.
    from models.product_memory import MemoryItem

    source = MemoryItem.model_validate(data['before'])
    target_id = amend_fact(
        uid,
        edit.memory_id,
        edit.content,
        provenance=LedgerProvenance(
            source_id=edit.memory_id, source_type='agent_conclusion', action_id=f'review:{change.change_id}'
        ),
        write_reason=LedgerWriteReason.agent_reusable_conclusion,
        slot=source.slot,
        subject_scope=source.subject_scope or MemorySubjectScope.primary_user,
        subject_entity_id=source.subject_entity_id,
        curation_weight=source.curation_weight,
        visibility=source.visibility,
        db_client=store.client(),
        required_source_item=source,
    )
    ref.update({'phase': 'applied', 'active_memory_id': target_id, 'after_memory_id': target_id})
    return change


def set_memory_undone(uid: str, change_id: str, undone: bool, data: dict) -> ReviewChange:
    from models.product_memory import LedgerWriteReason, MemoryItem, MemorySubjectScope
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item
    from utils.memory.knowledge_ledger import LedgerProvenance, amend_user_fact

    ref = store.user(uid).collection('review_changes').document(store.safe_id(change_id))
    if data['change']['undone'] == undone and data.get('phase') == 'applied':
        return ReviewChange.model_validate(data['change'])
    desired = 'undo' if undone else 'redo'
    marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(data['edit_key']))

    @firestore.transactional
    def reserve(tx):
        current = store.decode_doc(uid, ref.get(transaction=tx).to_dict())
        if current.get('phase') not in {'applied', desired}:
            raise store.ReviewConflict('Memory change is in progress')
        if current['phase'] == 'applied' and current['change']['undone'] == undone:
            return current, False
        active = store.user(uid).collection('memory_items').document(current['active_memory_id']).get(transaction=tx)
        if current['phase'] == 'applied':
            if not active.exists or active.to_dict().get('status') != 'active':
                raise store.ReviewConflict('Memory has a newer edit')
            current['source'] = active.to_dict()
        revision = current.get('revision', 0) + (1 if current.get('phase') == 'applied' else 0)
        current.update(phase=desired, revision=revision)
        tx.update(ref, store.encode_doc(uid, {'phase': desired, 'revision': revision, 'source': current['source']}))
        if undone:
            tx.set(
                marker, {'edit_key': data['edit_key'], 'change_id': change_id, 'created_at': datetime.now(timezone.utc)}
            )
        return current, True

    current, apply = reserve(store.client().transaction())
    if not apply:
        return ReviewChange.model_validate(current['change'])
    source = MemoryItem.model_validate(current['source'])
    operation_id = str(uuid5(NAMESPACE_URL, f"{uid}:{change_id}:{current['revision']}:{desired}"))
    content = current['before']['content'] if undone else current['memory_edit']['content']
    try:
        memory_id = amend_user_fact(
            uid,
            source.memory_id,
            content,
            provenance=LedgerProvenance(
                source_id=source.memory_id, source_type='explicit_user_revert', action_id=operation_id
            ),
            write_reason=LedgerWriteReason.direct_user_statement,
            slot=source.slot,
            subject_scope=source.subject_scope or MemorySubjectScope.primary_user,
            subject_entity_id=source.subject_entity_id,
            curation_weight=source.curation_weight,
            visibility=source.visibility,
            db_client=store.client(),
            required_source_item=source,
        )
    except (RuntimeError, ValueError) as exc:
        raise store.ReviewConflict('Memory has a newer edit') from exc
    # Revert appends a fresh direct-user tail; never resurrects an old row in place.
    if read_canonical_memory_item(uid, memory_id, db_client=store.client()) is None:
        raise store.ReviewConflict('Reverted memory readback unavailable')
    change = dict(current['change'], undone=undone)

    @firestore.transactional
    def finish(tx):
        latest = store.decode_doc(uid, ref.get(transaction=tx).to_dict())
        if latest['revision'] != current['revision'] or latest['phase'] not in {desired, 'applied'}:
            raise store.ReviewConflict('Memory change is in progress')
        tx.update(ref, store.encode_doc(uid, {'phase': 'applied', 'active_memory_id': memory_id, 'change': change}))

    finish(store.client().transaction())
    return ReviewChange.model_validate(change)
