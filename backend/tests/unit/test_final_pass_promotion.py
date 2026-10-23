from datetime import datetime, timezone

import pytest

from database import conversations as db
from models.transcript_segment import TranscriptSegment
from models.conversation import Conversation
from utils.conversations import speaker_resolution as resolution
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot


@pytest.mark.parametrize(
    'fence', ['current', 'corrected', 'revision', 'deleted', 'account_deleting', 'locked', 'flag_off', 'rehomed']
)
def test_promotion_is_atomic_preserves_manual_edits_and_fences_current_revision(monkeypatch, fence):
    """``rehomed``: the race with a still-live final pass. The upload path moved the owner to
    batch_sync_v1 while this pass ran; its promotion is refused even at the revision it expects,
    so batch and the pass never both own the transcript (final_pass_rehome)."""
    uid, cid = 'synthetic-user', 'synthetic-conversation'
    revision = datetime(2026, 1, 1, tzinfo=timezone.utc)
    other = datetime(2026, 1, 2, tzinfo=timezone.utc)
    old = TranscriptSegment(
        id='old',
        text='a sufficiently long synthetic sentence edited',
        start=0,
        end=4,
        is_user=False,
        speaker_id=0,
        speaker_label_source='manual',
        translations=[{'lang': 'fr', 'text': 'synthetic translation'}],
    )
    candidate = TranscriptSegment(
        id='new', text='a sufficiently long synthetic sentence', start=0, end=4, is_user=True, speaker_id=1
    )
    data = db.encode_conversation_for_write(
        uid,
        {
            'status': 'completed',
            'data_protection_level': 'standard',
            'transcript_segments': [old.model_dump()],
            'structured': {'notes': [{'source_segment_ids': ['old']}]},
            'manual_speaker_assignments': {'segments': {'old': {'is_user': False, 'generation': 1}}},
        },
    )
    data['_test_revision'] = other if fence == 'revision' else revision
    if fence == 'corrected':
        from database import review_store

        data['has_transcript_corrections'] = True
        data['transcript_correction_overlay'] = review_store.encode_doc(
            uid,
            {
                'source': [
                    {
                        'segment_id': 'old',
                        'segment_index': 0,
                        'start': 0,
                        'before': 'sentence',
                        'after': 'workshop',
                        'kind': 'spelling',
                        'undone': False,
                    }
                ]
            },
        )
    if fence == 'deleted':
        data['deleted'] = True
    if fence == 'locked':
        data['is_locked'] = True
    if fence == 'rehomed':
        data['record_lane_owner'] = 'batch_sync_v1'
    path = ('users', uid, 'conversations', cid)
    client = StrictFirestore({path: data})
    if fence == 'account_deleting':
        client.rows[('account_deletions', uid)] = {'status': 'deleting'}
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda self: (self._data or {}).get('_test_revision')),
        raising=False,
    )
    monkeypatch.setattr(db, 'authoritative_for', lambda _uid: fence != 'flag_off')
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda _uid: None)
    written = db.promote_final_pass_if_current(
        uid, cid, [candidate], expected_updated_at=revision, clock_offset=0, firestore_client=client
    )
    assert written == (fence in {'current', 'corrected'})
    stored = db.prepare_conversation_for_read(client.rows[path], uid)
    if written:
        segment = stored['transcript_segments'][0]
        assert segment['id'] == 'old' and segment['is_user'] is False
        assert segment['text'] == (old.text.replace('sentence', 'workshop') if fence == 'corrected' else old.text)
        raw_speech = db.decode_transcript_segments_verified(
            uid, client.rows[path]['transcript_segments'], bool(client.rows[path].get('transcript_segments_compressed'))
        )
        assert raw_speech[0]['text'] == old.text
        assert segment['translations'] == (
            [] if fence == 'corrected' else [{'lang': 'fr', 'text': 'synthetic translation'}]
        )
        assert raw_speech[0]['translations'] == [{'lang': 'fr', 'text': 'synthetic translation'}]
        assert stored['structured']['notes'][0]['source_segment_ids'] == ['old']
        assert stored['manual_speaker_assignments']['segments']['old']['generation'] == 1
    else:
        assert stored['transcript_segments'][0]['id'] == 'old'


def test_authoritative_turns_bypass_legacy_rediarization_but_apply_manual_overlay(monkeypatch):

    monkeypatch.setattr(resolution, 'authoritative_for', lambda _uid: True)
    monkeypatch.setattr(resolution, 'resolution_enabled', lambda: True)
    monkeypatch.setattr(resolution, '_resolve', lambda *_a, **_kw: pytest.fail('legacy cannot overwrite final turns'))
    monkeypatch.setattr(
        resolution.conversations_db,
        'get_manual_speaker_receipt',
        lambda *_a: {'segments': {'new': {'is_user': False, 'generation': 1}}},
    )
    conversation = Conversation(
        id='synthetic',
        finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured={'title': '', 'overview': '', 'emoji': '', 'category': 'other', 'action_items': [], 'events': []},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        transcript_segments=[
            TranscriptSegment(
                id='new', text='synthetic', start=0, end=3, is_user=True, speaker_id_scope='final:pyannote'
            )
        ],
    )
    assert resolution.resolve_speakers_for_processing('synthetic', conversation)
    assert not conversation.transcript_segments[0].is_user
