"""Merging conversations that overlap in time keeps the merge and moves transcript corrections.

The merged transcript is sorted by time, so a recording made during a longer one lands between
the longer one's lines. The correction transfer expected each source's lines as one block in
merge order, so it rejected every such merge and the merge rolled back.
"""

from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from database import conversations, review_transcript_changes
import utils.conversations.merge_conversations as merge
import utils.conversations.process_conversation  # noqa: F401
import utils.notifications as notifications
from tests.unit.test_dream_cleanup_edits import store, UID

T0 = datetime(2026, 5, 30, 10, tzinfo=timezone.utc)


def _store_source(db, key, started_at, segments):
    row = {
        'id': key,
        'status': 'completed',
        'created_at': started_at,
        'started_at': started_at,
        'finished_at': started_at + timedelta(minutes=2),
        'language': 'en',
        'data_protection_level': 'enhanced',
        'structured': {'title': 'Synthetic planning call'},
        'transcript_segments': segments,
    }
    db.rows[('users', UID, 'conversations', key)] = conversations.encode_conversation_for_write(UID, row, 'enhanced')


def test_overlapping_merge_completes_and_keeps_the_correction_on_its_line(store, monkeypatch):
    monkeypatch.setattr(conversations, 'db', store)
    _store_source(
        store,
        'long',
        T0,
        [
            {'id': 'long-early', 'text': 'Early line from the long recording.', 'is_user': True, 'start': 0, 'end': 5},
            {'id': 'long-late', 'text': 'Late line from the long recording.', 'is_user': True, 'start': 60, 'end': 65},
        ],
    )
    # Recorded during the long conversation: its line sorts between the long one's two lines.
    _store_source(
        store,
        'short',
        T0 + timedelta(seconds=30),
        [{'id': 'short-only', 'text': 'Line from the short recording.', 'is_user': False, 'start': 0, 'end': 10}],
    )
    assert review_transcript_changes.edit_user_segment(UID, 'long', 'long-late', 'Corrected late line.') == 'ok'

    monkeypatch.setattr(
        merge.conversations_db,
        'get_conversation',
        lambda uid, conversation_id: conversations.prepare_conversation_for_read(
            store.rows[('users', uid, 'conversations', conversation_id)], uid
        ),
    )

    def create_processing_conversation(uid, data):
        # The production write stamps the owner's protection level, then runs this same codec.
        data = {**data, 'data_protection_level': 'enhanced'}
        store.rows[('users', uid, 'conversations', data['id'])] = conversations.encode_conversation_for_write(
            uid, data, 'enhanced'
        )

    monkeypatch.setattr(merge.lifecycle_service, 'create_processing_conversation', create_processing_conversation)
    monkeypatch.setattr(merge.lifecycle_service, 'complete', lambda *_a, **_k: None)
    monkeypatch.setattr(merge, '_collect_all_photos', lambda *_a, **_k: [])
    monkeypatch.setattr(merge, '_copy_audio_chunks_for_merge', lambda *_a, **_k: [])
    monkeypatch.setattr(merge, '_delete_conversation_and_related_data', lambda *_a, **_k: None)
    monkeypatch.setattr(merge, 'firestore_db', store)
    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)
    failures, completed = [], []
    monkeypatch.setattr(merge, '_handle_merge_failure', lambda *args, **_k: failures.append(args))
    monkeypatch.setattr(notifications, 'send_merge_completed_message', lambda *args, **_k: completed.append(args))

    merge.perform_merge_async(UID, ['long', 'short'], reprocess=False)

    assert failures == [] and len(completed) == 1
    merged_id = completed[0][1]
    merged = conversations.prepare_conversation_for_read(store.rows[('users', UID, 'conversations', merged_id)], UID)
    assert [segment['text'] for segment in merged['transcript_segments']] == [
        'Early line from the long recording.',
        'Line from the short recording.',
        'Corrected late line.',
    ]
    assert store.rows[('users', UID, 'conversations', 'long')]['transcript_corrections_moved_to'] == merged_id
