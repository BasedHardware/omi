"""Atomic summary edits, immutable speech overlays, journal and overlay Undo."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace

from google.cloud import firestore
import json

from database import memory_ledger, review_store as store
from database.review_field_states import read_field_state, write_field_state
from database.read_boundary import parse_payload_strict
from models.transcript_segment import legacy_conversation_segment_id
from models.review import ReviewChange, ChangeRef
from models.client_processing import PROJECTION_FAMILY_FIELDS
from utils.conversations.transcript_hash import transcript_sha256_for_binding
from models.review_context import build_context, question_source
from utils.review_projection import sync_conversations, sync_transcript_chunks
from utils.agent_capabilities.transcripts import original_fingerprint, apply_entries


class _AlreadySettled(Exception):
    pass


def record_change(
    uid,
    change,
    patch,
    corrections,
    *,
    edit_key,
    expected_records,
    expected_document,
    authority='dream',
    firestore_client=None
):
    if authority not in {'user', 'dream'}:
        raise ValueError('agent_invalid_authority')
    if authority == 'dream':
        store.require_enabled(uid)
    from database.conversations import guard_match_score_size

    patch = {**patch, **{field: firestore.DELETE_FIELD for field in PROJECTION_FAMILY_FIELDS}}
    guard_match_score_size(patch, expected_document)
    conversation_id = change.refs[0].id
    database = firestore_client or store.client()
    owner = database.collection('users').document(uid)
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
        if existing or (blocked and authority == 'dream'):
            raise store.ReviewConflict('Transcript correction already applied or undone')
        if current and current.get('transcript_corrections_moved_to'):
            raise store.ReviewConflict('Transcript correction anchors moved to a merged capture')
        if current != expected_document or not current or current.get('deleted') or current.get('is_locked'):
            raise store.ReviewConflict('Transcript changed while preparing a correction')
        # Read and validate the current overlay in this transaction too. Captured
        # text alone cannot fence a second correction of the same segment.
        from database.conversations import decode_transcript_segments_verified

        segments = decode_transcript_segments_verified(
            uid, current.get('transcript_segments') or [], bool(current.get('transcript_segments_compressed'))
        )
        projected = apply_entries(segments, data['source'])
        enriched = deepcopy(corrections)
        for correction in enriched:
            index = correction['segment_index']
            if index >= len(projected) or correction['before'] not in projected[index]['text']:
                raise store.ReviewConflict('Transcript correction input changed')
            if correction['kind'] == 'transcript' and correction['before'] != projected[index]['text']:
                raise store.ReviewConflict('Transcript correction input changed')
            correction['depends_on'] = sorted(
                {
                    row['change_id']
                    for row in data['source']
                    if not row['undone']
                    and row['segment_index'] == index
                    and (
                        correction['kind'] == 'transcript'
                        or row['kind'] == 'transcript'
                        or row['after'] in correction['before']
                    )
                }
            )
        combined = [*data['source'], *enriched]
        if (authority == 'dream' and sum(row.get('source') == 'dream' for row in combined) > 500) or len(
            json.dumps(combined, default=str).encode()
        ) > 700000:
            raise ValueError('dream_transcript_overlay_budget')
        anchor_indices = sorted({row['segment_index'] for row in enriched})
        receipt = {
            'conversation_id': conversation_id,
            'original_anchor_indices': anchor_indices,
            'original_fingerprint': original_fingerprint(uid, current, anchor_indices),
            'corrections': enriched,
            'before': {field: read_field_state(current, field) for field in patch},
            'after': {
                field: {'present': False} if value is firestore.DELETE_FIELD else {'present': True, 'value': value}
                for field, value in patch.items()
            },
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
            transaction.update(
                target,
                {
                    **patch,
                    'has_transcript_corrections': True,
                    'transcript_correction_overlay': store.encode_doc(uid, {'source': combined}),
                },
            )
            transaction.set(overlay, store.encode_doc(uid, {'source': combined}))
            transaction.set(journal, store.encode_doc(uid, result))

        return {
            'mutations': [memory_ledger.mutation('agent_edit', change_id=change.change_id, edit_key=edit_key)],
            'projection_writer': write,
        }

    memory_ledger.append_commit_with_builder(uid, None, build, use_current_head=True, firestore_client=database)
    sync_conversations(
        uid, [{'collection': 'conversations', 'document_id': conversation_id}], firestore_client=database
    )
    sync_transcript_chunks(uid, conversation_id, firestore_client=database)
    return parse_payload_strict(ReviewChange, result['change'], document_path=journal.path)


def set_undone(uid, change_id, undone):
    owner = store.user(uid)
    journal = owner.collection('review_changes').document(store.safe_id(change_id))
    result = {}

    def build(tx):
        data = store.require_doc(uid, journal.get(transaction=tx).to_dict())
        if data['change']['undone'] == undone:
            result.update(data)
            raise _AlreadySettled
        receipt = data['transcript_overlay']
        target = owner.collection('conversations').document(receipt['conversation_id'])
        overlay = owner.collection('transcript_corrections').document(receipt['conversation_id'])
        current = target.get(transaction=tx).to_dict()
        rows = store.require_doc(uid, overlay.get(transaction=tx).to_dict())['source']
        if not current or current.get('deleted') or current.get('is_locked'):
            raise store.ReviewConflict('Transcript no longer available')
        if (
            original_fingerprint(uid, current, receipt.get('original_anchor_indices'))
            != receipt['original_fingerprint']
        ):
            raise store.ReviewConflict('Original speech changed after this correction')
        expected, destination = ('after', 'before') if undone else ('before', 'after')
        if any(
            read_field_state(current, field) != value
            for field, value in receipt[expected].items()
            if field not in PROJECTION_FAMILY_FIELDS
        ):
            raise store.ReviewConflict('Conversation has a newer edit')
        selected = [row for row in rows if row['change_id'] == change_id]
        if len(selected) != len(receipt['corrections']):
            raise store.ReviewConflict('Transcript correction receipt changed')
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
                    and (
                        row['kind'] == 'transcript'
                        or change_id in later.get('depends_on', [])
                        or later['before'] == row['after']
                    )
                ):
                    raise store.ReviewConflict('Transcript has a dependent newer correction')
        if not undone and any(
            dependency == row['change_id'] and row['undone']
            for selected_row in selected
            for dependency in selected_row.get('depends_on', [])
            for row in rows
        ):
            raise store.ReviewConflict('Transcript correction depends on an undone correction')
        updated = deepcopy(rows)
        for row in updated:
            if row['change_id'] == change_id:
                row['undone'] = undone
        result.update(data)
        result['change'] = {**data['change'], 'undone': undone}

        restored_fields = {field: write_field_state(value) for field, value in receipt[destination].items()}
        # Client output is a derived cache. A fresh result for corrected speech
        # must not block Undo, and an older cache may only return when its digest
        # matches the projection after this reversal.
        candidate = restored_fields.get('client_processing')
        if isinstance(candidate, dict) and isinstance(candidate.get('transcript_sha256'), str):
            from database.conversations import decode_transcript_segments_verified

            speech = decode_transcript_segments_verified(
                uid, current.get('transcript_segments') or [], bool(current.get('transcript_segments_compressed'))
            )
            if candidate['transcript_sha256'] != transcript_sha256_for_binding(apply_entries(speech, updated)):
                restored_fields['client_processing'] = firestore.DELETE_FIELD

        def write(transaction):
            transaction.update(
                target, {**restored_fields, 'transcript_correction_overlay': store.encode_doc(uid, {'source': updated})}
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

    try:
        memory_ledger.append_commit_with_builder(
            uid, None, build, use_current_head=True, firestore_client=store.client()
        )
    except _AlreadySettled:
        return parse_payload_strict(ReviewChange, result['change'], document_path=journal.path)
    sync_conversations(
        uid,
        [{'collection': 'conversations', 'document_id': result['transcript_overlay']['conversation_id']}],
        firestore_client=store.client(),
    )
    sync_transcript_chunks(uid, result['transcript_overlay']['conversation_id'], firestore_client=store.client())
    return parse_payload_strict(ReviewChange, result['change'], document_path=journal.path)


def edit_user_segment(uid, conversation_id, segment_id, text, *, firestore_client=None):
    """Existing signed-in manual edit API, with encrypted overlay and atomic Undo.

    Source references and client projections are invalidated in the same commit.
    A concurrent correction is retried from the latest projection, preserving
    corrections on other segments. This explicit owner action works with Review
    disabled; autonomous Dream still requires the Review gate.
    """
    from database import conversations

    text = text.strip()
    database = firestore_client or store.client()
    target = database.collection('users').document(uid).collection('conversations').document(conversation_id)
    for _attempt in range(3):
        raw = target.get().to_dict()
        if raw and raw.get('transcript_corrections_moved_to'):
            return 'conflict'
        if not raw or raw.get('deleted'):
            return 'not_found'
        if raw.get('is_locked'):
            return 'locked'
        expected = deepcopy(raw)
        raw = {**raw, 'id': conversation_id}
        current = conversations.prepare_conversation_for_read(raw, uid, firestore_client=database)
        if current is None:
            return 'not_found'
        selected = next(
            (
                (i, segment)
                for i, segment in enumerate(current.get('transcript_segments') or [])
                if (segment.get('id') or legacy_conversation_segment_id(conversation_id, i)) == segment_id
            ),
            None,
        )
        if selected is None:
            return 'segment_not_found'
        index, segment = selected
        before = segment.get('text', '')
        if before == text:
            return 'ok'
        now = datetime.now(timezone.utc)
        change_id = str(uuid4())
        item = SimpleNamespace(
            kind='spelling', source_ref='conversations/' + conversation_id + '#' + segment_id, quote=before
        )
        display = deepcopy(current)
        display['transcript_segments'][index]['id'] = segment_id
        context = build_context(item, question_source(item, {'conversations/' + conversation_id: display}))
        change = ReviewChange(
            change_id=change_id,
            kind='other',
            edit_kind='transcript',
            title='Edit transcript',
            before=before[:4000],
            after=text[:4000],
            created_at=now,
            context=context,
            refs=[
                ChangeRef(
                    type='conversation',
                    id=conversation_id,
                    label=(current.get('structured') or {}).get('title') or 'Conversation',
                )
            ],
        )
        correction = dict(
            segment_id=segment_id,
            legacy_anchor=not bool(segment.get('id')),
            conversation_id=conversation_id,
            segment_index=index,
            start=segment.get('start'),
            before=before,
            after=text,
            kind='transcript',
            source='user',
            change_id=change_id,
            created_at=now,
            undone=False,
        )
        patch = conversations.summary_source_reference_invalidations(current.get('structured'), segment_id)
        patch.update(updated_at=now, has_user_transcript_corrections=True)
        conversations.clear_client_processing(patch)
        try:
            record_change(
                uid,
                change,
                patch,
                [correction],
                edit_key='user:transcript:' + change_id,
                expected_records=None,
                expected_document=expected,
                authority='user',
                firestore_client=database,
            )
            return 'ok'
        except store.ReviewConflict:
            if _attempt == 2:
                return 'conflict'
        except ValueError as error:
            if str(error) == 'dream_transcript_overlay_budget':
                return 'correction_limit'
            raise
    raise AssertionError('unreachable transcript retry')
