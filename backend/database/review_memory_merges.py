"""Recoverable duplicate-fact merge journal; undo appends two direct-user tails."""

from datetime import datetime, timezone
from typing import Literal, cast

from google.cloud import firestore

from database import review_store as store
from database.read_boundary import parse_payload_strict
from models.product_memory import LedgerWriteReason, MemoryKind, MemoryItem
from models.review import ReviewChange
from utils.memory.canonical_memory_adapter import read_canonical_memory_item
from utils.memory.canonical_memory_adapter import mint_direct_user_write_authority
from utils.memory.knowledge_ledger import LedgerWrite, LedgerProvenance, save_ledger_write, amend_user_fact, save_fact


def record_merge(uid, change, edit, edit_key):
    ref = store.user(uid).collection('review_changes').document(store.safe_id(change.change_id))
    marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(edit_key))
    sources = [
        read_canonical_memory_item(uid, key, db_client=store.client())
        for key in (edit.memory_id, edit.duplicate_memory_id)
    ]

    @firestore.transactional
    def reserve(tx):
        current = store.decode_doc(uid, ref.get(transaction=tx).to_dict())
        blocked = marker.get(transaction=tx).exists
        if current:
            if current['edit_key'] != edit_key or current['memory_edit'] != edit.model_dump():
                raise store.ReviewConflict('Memory merge identity conflict')
            return current
        if blocked or any(
            s is None
            or s.status.value != 'active'
            or s.kind != MemoryKind.fact
            or s.ledger_schema_version != 'knowledge_ledger.v1'
            for s in sources
        ):
            raise store.ReviewConflict('Only active canonical facts can merge')
        valid_sources = [source for source in sources if source is not None]
        if len(valid_sources) != 2:
            raise store.ReviewConflict('Canonical merge sources missing')
        if valid_sources[0].memory_id == valid_sources[1].memory_id or any(
            getattr(valid_sources[0], field) != getattr(valid_sources[1], field)
            for field in ('visibility', 'subject_scope', 'subject_entity_id', 'slot')
        ):
            raise store.ReviewConflict('Duplicate facts must share visibility and subject')
        data = {
            'change': change.model_dump(mode='python'),
            'created_at': change.created_at,
            'edit_key': edit_key,
            'memory_edit': edit.model_dump(),
            'memory_merge': True,
            'before': [s.model_dump(mode='python') for s in valid_sources],
            'phase': 'applying',
        }
        tx.set(ref, store.encode_doc(uid, data))
        return data

    data = reserve(store.client().transaction())
    if data['phase'] == 'applied':
        return parse_payload_strict(ReviewChange, data['change'], document_path=ref.path)
    target = _merge(uid, data['before'], edit.content, 'review:' + change.change_id)
    ref.update({'phase': 'applied', 'active_memory_ids': [target]})
    return change


def _merge(uid, rows, content, action_id):
    source = parse_payload_strict(MemoryItem, rows[0], document_path=f'users/{uid}/review_memory_merge/source')
    return save_ledger_write(
        uid,
        LedgerWrite(
            kind=MemoryKind.fact,
            content=content,
            provenance=LedgerProvenance(
                source_id=source.memory_id, source_type='agent_conclusion', action_id=action_id
            ),
            write_reason=LedgerWriteReason.agent_reusable_conclusion,
            subject_scope=source.subject_scope,
            subject_entity_id=source.subject_entity_id,
            slot=source.slot,
            visibility=cast(Literal['private', 'public', 'shared'], source.visibility),
            supersedes=[r['memory_id'] for r in rows],
            preserved_evidence=[
                ev
                for row in rows
                for ev in parse_payload_strict(
                    MemoryItem, row, document_path=f'users/{uid}/review_memory_merge/source'
                ).evidence
            ],
        ),
        db_client=store.client(),
        required_source_item=source,
    )


def set_undone(uid, change_id, undone, data):
    ref = store.user(uid).collection('review_changes').document(store.safe_id(change_id))
    marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(data['edit_key']))
    phase = 'undo' if undone else 'redo'

    @firestore.transactional
    def reserve(tx):
        latest = store.require_doc(uid, ref.get(transaction=tx).to_dict())
        if latest['change']['undone'] == undone and latest['phase'] == 'applied':
            return latest, False
        if latest['phase'] not in {'applied', phase}:
            raise store.ReviewConflict('Merge reversal in progress')
        if latest['phase'] == 'applied':
            sources = []
            for key in latest['active_memory_ids']:
                row = store.user(uid).collection('memory_items').document(key).get(transaction=tx).to_dict()
                if not row or row.get('status') != 'active':
                    raise store.ReviewConflict('Memory has a newer edit')
                sources.append(row)
            latest['source'] = sources
            latest['revision'] = latest.get('revision', 0) + 1
        tx.update(
            ref, store.encode_doc(uid, {'phase': phase, 'source': latest['source'], 'revision': latest['revision']})
        )
        if undone:
            tx.set(
                marker,
                {'edit_key': latest['edit_key'], 'change_id': change_id, 'created_at': datetime.now(timezone.utc)},
            )
        return latest, True

    latest, apply = reserve(store.client().transaction())
    if not apply:
        return parse_payload_strict(ReviewChange, latest['change'], document_path=ref.path)
    action = f"review:{change_id}:{latest['revision']}:{phase}"
    if undone:
        source = latest['source'][0]
        original, duplicate = latest['before']
        first = amend_user_fact(
            uid,
            source['memory_id'],
            original['content'],
            provenance=LedgerProvenance(
                source_id=source['memory_id'], source_type='explicit_user_revert', action_id=action + ':first'
            ),
            write_reason=LedgerWriteReason.direct_user_statement,
            slot=original.get('slot'),
            subject_scope=original['subject_scope'],
            subject_entity_id=original.get('subject_entity_id'),
            visibility=original['visibility'],
            db_client=store.client(),
            required_source_item=parse_payload_strict(
                MemoryItem, source, document_path=f'users/{uid}/review_memory_merge/source'
            ),
        )
        second = save_fact(
            uid,
            duplicate['content'],
            provenance=LedgerProvenance(
                source_id=duplicate['memory_id'], source_type='explicit_user_statement', action_id=action + ':second'
            ),
            write_reason=LedgerWriteReason.direct_user_statement,
            user_asserted=True,
            slot=duplicate.get('slot'),
            subject_scope=duplicate['subject_scope'],
            subject_entity_id=duplicate.get('subject_entity_id'),
            visibility=duplicate['visibility'],
            db_client=store.client(),
            _direct_user_authority=mint_direct_user_write_authority(),
        )
        active = [first, second]
    else:
        active = [_merge(uid, latest['source'], latest['memory_edit']['content'], action)]
    change = dict(latest['change'], undone=undone)
    ref.update(store.encode_doc(uid, {'change': change, 'phase': 'applied', 'active_memory_ids': active}))
    return parse_payload_strict(ReviewChange, change, document_path=ref.path)
