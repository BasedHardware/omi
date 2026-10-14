"""Atomic summary edits, immutable speech overlays, journal and overlay Undo."""

from copy import deepcopy
import json

from database import memory_ledger, review_store as store
from database.review_changes import read_field_state, write_field_state
from models.review import ReviewChange
from utils.review_projection import sync_conversations
from utils.agent_capabilities.transcripts import original_fingerprint


def record_change(uid, change, patch, corrections, *, edit_key, expected_records, expected_document):
    store.require_enabled()
    conversation_id = change.refs[0].id
    owner = store.user(uid)
    target = owner.collection('conversations').document(conversation_id)
    overlay = owner.collection('transcript_corrections').document(conversation_id)
    journal = owner.collection('review_changes').document(store.safe_id(change.change_id))
    marker = owner.collection('review_do_not_redo').document(store.safe_id(edit_key))
    result = {}

    def build(tx):
        current = target.get(transaction=tx).to_dict()
        existing = store.decode_doc(uid, journal.get(transaction=tx).to_dict())
        blocked = marker.get(transaction=tx).exists
        data = store.decode_doc(uid, overlay.get(transaction=tx).to_dict()) or {'source': []}
        store.validate_records(uid, tx, expected_records)
        if existing or blocked:
            raise store.ReviewConflict('Transcript correction already applied or undone')
        if current != expected_document or not current or current.get('deleted') or current.get('is_locked'):
            raise store.ReviewConflict('Transcript changed while preparing a correction')
        combined = [*data['source'], *corrections]
        if len(combined) > 500 or len(json.dumps(combined, default=str).encode()) > 256000:
            raise ValueError('dream_transcript_overlay_budget')
        receipt = {
            'conversation_id': conversation_id,
            'original_fingerprint': original_fingerprint(uid, current),
            'corrections': corrections,
            'before': {field: read_field_state(current, field) for field in patch},
            'after': {field: {'present': True, 'value': value} for field, value in patch.items()},
        }
        result.update(
            {
                'change': change.model_dump(mode='python'),
                'created_at': change.created_at,
                'edit_key': edit_key,
                'transcript_overlay': receipt,
            }
        )

        def write(transaction):
            transaction.update(target, {**patch, 'has_transcript_corrections': True})
            transaction.set(overlay, store.encode_doc(uid, {'source': combined}))
            transaction.set(journal, store.encode_doc(uid, result))

        return {
            'mutations': [memory_ledger.mutation('agent_edit', change_id=change.change_id, edit_key=edit_key)],
            'projection_writer': write,
        }

    memory_ledger.append_commit_with_builder(uid, None, build, use_current_head=True, firestore_client=store.client())
    sync_conversations(
        uid, [{'collection': 'conversations', 'document_id': conversation_id}], firestore_client=store.client()
    )
    return ReviewChange.model_validate(result['change'])


def set_undone(uid, change_id, undone):
    owner = store.user(uid)
    journal = owner.collection('review_changes').document(store.safe_id(change_id))
    result = {}

    def build(tx):
        data = store.require_doc(uid, journal.get(transaction=tx).to_dict())
        receipt = data['transcript_overlay']
        target = owner.collection('conversations').document(receipt['conversation_id'])
        overlay = owner.collection('transcript_corrections').document(receipt['conversation_id'])
        current = target.get(transaction=tx).to_dict()
        rows = store.require_doc(uid, overlay.get(transaction=tx).to_dict())['source']
        if not current or current.get('deleted') or current.get('is_locked'):
            raise store.ReviewConflict('Transcript no longer available')
        if original_fingerprint(uid, current) != receipt['original_fingerprint']:
            raise store.ReviewConflict('Original speech changed after this correction')
        expected, destination = ('after', 'before') if undone else ('before', 'after')
        if any(read_field_state(current, field) != value for field, value in receipt[expected].items()):
            raise store.ReviewConflict('Conversation has a newer edit')
        selected = [row for row in rows if row['change_id'] == change_id]
        if len(selected) != len(receipt['corrections']):
            raise store.ReviewConflict('Transcript correction receipt changed')
        if data['change']['undone'] == undone:
            result.update(data)
            return {'mutations': [], 'projection_writer': lambda transaction: None}
        # Later active overlays may depend on this spelling; do not silently
        # disable a newer correction when Undo changes its input.
        for row in selected:
            if row['undone'] != (not undone):
                raise store.ReviewConflict('Transcript correction state changed')
            for later in rows[rows.index(row) + 1 :]:
                if (
                    not later['undone']
                    and later['change_id'] != change_id
                    and later['segment_index'] == row['segment_index']
                    and later['before'] == row['after']
                ):
                    raise store.ReviewConflict('Transcript has a dependent newer correction')
        updated = deepcopy(rows)
        for row in updated:
            if row['change_id'] == change_id:
                row['undone'] = undone
        result.update(data)
        result['change'] = {**data['change'], 'undone': undone}

        def write(transaction):
            if receipt[destination]:
                transaction.update(
                    target, {field: write_field_state(value) for field, value in receipt[destination].items()}
                )
            transaction.set(overlay, store.encode_doc(uid, {'source': updated}))
            transaction.update(journal, store.encode_doc(uid, {'change': result['change']}))
            if undone:
                transaction.set(
                    owner.collection('review_do_not_redo').document(store.safe_id(data['edit_key'])),
                    {'edit_key': data['edit_key'], 'change_id': change_id},
                )

        return {
            'mutations': [
                memory_ledger.mutation('undo_agent_edit' if undone else 'redo_agent_edit', change_id=change_id)
            ],
            'projection_writer': write,
        }

    memory_ledger.append_commit_with_builder(uid, None, build, use_current_head=True, firestore_client=store.client())
    sync_conversations(
        uid,
        [{'collection': 'conversations', 'document_id': result['transcript_overlay']['conversation_id']}],
        firestore_client=store.client(),
    )
    return ReviewChange.model_validate(result['change'])
