"""Source-scoped fragment labels must reach the serialized transcript."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from models.transcript_segment import TranscriptSegment
from models.conversation import Conversation
from models.structured import Structured
from utils.conversations.merge_conversations import _merge_transcript_segments
from utils.conversations.speaker_resolution import apply_speaker_resolution
from utils.stt.conversation_speakers import resolve_conversation_speakers


def test_same_integer_id_in_two_scopes_cannot_label_other_short_reply():
    segments = [
        {
            'id': 'owner',
            'speaker_id': 0,
            'speaker_id_scope': 'pendant:0',
            'start': 0.0,
            'end': 10.0,
            'is_user': False,
            'text': 'Owner',
        },
        {
            'id': 'other',
            'speaker_id': 0,
            'speaker_id_scope': 'desktop:0',
            'start': 11.0,
            'end': 17.0,
            'is_user': False,
            'text': 'Other',
        },
        {
            'id': 'short',
            'speaker_id': 0,
            'speaker_id_scope': 'desktop:0',
            'start': 18.0,
            'end': 18.5,
            'is_user': False,
            'text': 'Okay',
        },
    ]
    resolution = resolve_conversation_speakers(
        segments, {'owner': np.array([1.0, 0.0]), 'other': np.array([0.0, 1.0])}, voiceprints={'user': [1.0, 0.0]}
    )
    conversation = Conversation(
        id='merged',
        started_at=None,
        finished_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured=Structured(),
        transcript_segments=[TranscriptSegment(**s) for s in segments],
    )
    apply_speaker_resolution(
        conversation,
        resolution.speaker_ids,
        resolution.voice_identities,
        resolution.voice_identity_statuses,
        owner_voiceprint_available=resolution.owner_voiceprint_available,
    )
    assert [s['is_user'] for s in conversation.model_dump()['transcript_segments']] == [True, False, False]
    assert resolution.speaker_ids['short'] == resolution.speaker_ids['other']
    assert resolution.speaker_ids['short'] != resolution.speaker_ids['owner']


@pytest.mark.parametrize('speaker_id', [0, '0'])
def test_manual_merge_reallocates_automatic_donor_voice_ids_and_preserves_capture_clock(speaker_id):
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def row(cid, offset, owner):
        return {
            'id': cid,
            'started_at': at + timedelta(seconds=offset),
            'finished_at': at + timedelta(seconds=offset + 6),
            'transcript_segments': [
                {
                    'id': cid,
                    'text': cid,
                    'speaker': 'SPEAKER_0',
                    'speaker_id': speaker_id,
                    'is_user': owner,
                    'start': 0.0,
                    'end': 6.0,
                    'audio_capture_start': at.timestamp() + offset,
                    'audio_capture_end': at.timestamp() + offset + 6,
                }
            ],
        }

    merged = _merge_transcript_segments([row('first', 0, True), row('second', 10, False)])
    payload = [TranscriptSegment(**s).model_dump() for s in merged]
    assert payload[0]['speaker_id'] != payload[1]['speaker_id']
    assert payload[0]['speaker_id_scope'] != payload[1]['speaker_id_scope']
    assert payload[1]['audio_capture_start'] == at.timestamp() + 10
    assert payload[1]['start'] == 10


def test_short_reply_from_acoustically_contradicted_voice_withdraws_auto_owner():
    segments = [
        {
            'id': 'owner',
            'speaker_id': 0,
            'speaker_id_scope': 'conn:0',
            'start': 0.0,
            'end': 10.0,
            'is_user': False,
            'text': 'Owner',
        },
        {
            'id': 'other',
            'speaker_id': 0,
            'speaker_id_scope': 'conn:0',
            'start': 11.0,
            'end': 17.0,
            'is_user': False,
            'text': 'Other',
        },
        {
            'id': 'short',
            'speaker_id': 0,
            'speaker_id_scope': 'conn:0',
            'start': 18.0,
            'end': 18.5,
            'is_user': True,
            'speaker_label_source': 'auto',
            'text': 'Okay',
        },
    ]
    resolution = resolve_conversation_speakers(
        segments, {'owner': np.array([1.0, 0.0]), 'other': np.array([0.0, 1.0])}, voiceprints={'user': [1.0, 0.0]}
    )
    conversation = Conversation(
        id='merged',
        started_at=None,
        finished_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured=Structured(),
        transcript_segments=[TranscriptSegment(**s) for s in segments],
    )
    apply_speaker_resolution(
        conversation,
        resolution.speaker_ids,
        resolution.voice_identities,
        resolution.voice_identity_statuses,
        owner_voiceprint_available=resolution.owner_voiceprint_available,
        contradicted_segment_ids=resolution.contradicted_segment_ids,
    )
    assert conversation.model_dump()['transcript_segments'][-1]['is_user'] is False
