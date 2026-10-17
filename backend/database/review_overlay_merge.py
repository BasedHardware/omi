"""Explicit conversation merge moves correction anchors and their Undo receipts atomically."""

from copy import deepcopy
from google.cloud import firestore
from database import review_store as store
from utils.agent_capabilities.transcripts import original_fingerprint, apply_entries


def transfer(uid, source_ids, destination_id, *, firestore_client=None):
    database = firestore_client or store.client()
    owner = database.collection('users').document(uid)
    target = owner.collection('conversations').document(destination_id)

    @firestore.transactional
    def commit(tx):
        from database.conversations import decode_transcript_segments_verified

        if database.collection('account_deletions').document(uid).get(transaction=tx).exists:
            raise store.ReviewConflict('Account deletion fences correction transfer')
        raw_target = target.get(transaction=tx).to_dict()
        if not raw_target or raw_target.get('deleted') or raw_target.get('is_locked'):
            raise store.ReviewConflict('Merged correction destination unavailable')
        segments = decode_transcript_segments_verified(
            uid, raw_target.get('transcript_segments') or [], bool(raw_target.get('transcript_segments_compressed'))
        )
        combined, journals, sources = [], {}, []
        offset = 0
        for source_id in source_ids:
            source_ref = owner.collection('conversations').document(source_id)
            source = source_ref.get(transaction=tx).to_dict() or {}
            if source.get('deleted') or source.get('is_locked'):
                raise store.ReviewConflict('Merge source unavailable')
            if source.get('transcript_corrections_moved_to'):
                raise store.ReviewConflict('Correction anchors already moved by another merge')
            sources.append(source_ref)
            captured = decode_transcript_segments_verified(
                uid, source.get('transcript_segments') or [], bool(source.get('transcript_segments_compressed'))
            )
            if any(
                offset + i >= len(segments) or segment.get('text') != segments[offset + i].get('text')
                for i, segment in enumerate(captured)
            ):
                raise store.ReviewConflict('Captured speech changed during merge')
            if source.get('has_transcript_corrections'):
                overlay = owner.collection('transcript_corrections').document(source_id).get(transaction=tx).to_dict()
                rows = store.require_doc(uid, overlay)['source']
                for row in rows:
                    moved = deepcopy(row)
                    moved['segment_index'] += offset
                    anchor = segments[moved['segment_index']]
                    moved.update(
                        segment_id=anchor.get('id'),
                        start=anchor.get('start'),
                        legacy_anchor=False,
                        conversation_id=destination_id,
                    )
                    combined.append(moved)
                    if moved['change_id'] not in journals:
                        ref = owner.collection('review_changes').document(store.safe_id(moved['change_id']))
                        data = store.require_doc(uid, ref.get(transaction=tx).to_dict())
                        if 'transcript_overlay' not in data:
                            raise store.ReviewConflict('Correction receipt unavailable during merge')
                        journals[moved['change_id']] = (ref, data)
            offset += len(captured)
        if offset != len(segments):
            raise store.ReviewConflict('Merged speech shape changed')
        if not combined:
            # Seal every source against a correction arriving between merge
            # finalization and deletion, even when no overlay existed at read time.
            for source_ref in sources:
                tx.update(
                    source_ref,
                    {
                        'transcript_corrections_moved_to': destination_id,
                        'dream_duplicate': True,
                        'dream_duplicate_of': destination_id,
                    },
                )
            return True
        apply_entries(segments, combined)  # Strict validation before any writes.
        for change_id, (ref, data) in journals.items():
            corrections = [row for row in combined if row['change_id'] == change_id]
            indices = sorted({row['segment_index'] for row in corrections})
            receipt = data['transcript_overlay']
            # The merged summary is newly generated, not owned by an old source
            # edit. Undo retains that summary and reverses only the moved overlay.
            data['transcript_overlay'] = {
                **receipt,
                'conversation_id': destination_id,
                'corrections': corrections,
                'original_anchor_indices': indices,
                'original_fingerprint': original_fingerprint(uid, raw_target, indices),
                'before': {},
                'after': {},
            }
            for change_ref in data['change'].get('refs', []):
                if change_ref.get('type') == 'conversation' and change_ref.get('id') in source_ids:
                    change_ref['id'] = destination_id
            data['overlay_merged_from'] = receipt['conversation_id']
        encoded = store.encode_doc(uid, {'source': combined})
        tx.update(
            target,
            {
                'has_transcript_corrections': True,
                'has_user_transcript_corrections': any(row.get('source') != 'dream' for row in combined),
                'transcript_correction_overlay': encoded,
            },
        )
        tx.set(owner.collection('transcript_corrections').document(destination_id), encoded)
        for source_ref in sources:
            tx.update(
                source_ref,
                {
                    'transcript_corrections_moved_to': destination_id,
                    'dream_duplicate': True,
                    'dream_duplicate_of': destination_id,
                },
            )
        for ref, data in journals.values():
            tx.set(ref, store.encode_doc(uid, data))
        return True

    return commit(database.transaction())
