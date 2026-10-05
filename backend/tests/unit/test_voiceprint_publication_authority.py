"""Publication authority across codecs, label round-trips, conversation-wide resolution and clip overlap."""

from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pytest

from database import conversations, users, voice_profiles
from models.conversation import Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import speaker_resolution as stage
from utils.manual_speaker_assignments import manual_assignment
from utils.owner_voice_evidence import authorized_owner_segments, pool_owner_vectors
from utils.speaker_learning_policy import authorized_teaching_segments
from utils.speaker_tag_prompts import service

USER = ('users', 'u')
CONV = (*USER, 'conversations', 'c')
PERSON = (*USER, 'people', 'p')
NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def owner_source(training=True, generation=1):
    return {
        'id': 'c',
        'transcript_segments': [
            {
                'id': 's',
                'speaker_id': 1,
                'speaker_id_scope': 'sync:a',
                'start': 0,
                'end': 8,
                'text': 'Synthetic owner speech',
                'is_user': True,
            }
        ],
        'manual_speaker_assignments': {
            'generation': generation,
            'segments': {'s': {'generation': generation, 'is_user': True, 'use_for_speech_training': training}},
        },
    }


def pool(store, generation=1, segment_ids=('s',), card_generation=None):
    return voice_profiles.add_owner_voice_confirmation(
        'u',
        [0.0, 1.0],
        pool_owner_vectors,
        conversation_id='c',
        expected_receipt_generation=generation,
        segment_ids=list(segment_ids) if segment_ids is not None else None,
        card_generation=card_generation,
        firestore_client=store,
    )


@pytest.mark.parametrize('level', ['raw', 'standard', 'enhanced'])
@pytest.mark.parametrize(
    'training,decision_generation,expected_generation,card_generation,allowed',
    [
        (True, 1, 1, None, True),
        (False, 1, 1, None, False),
        (False, 1, 1, 1, True),
        (False, 2, 1, 1, False),
        (True, 3, 1, None, True),  # Explicit reconsent after a label changed and changed back.
    ],
)
def test_owner_publication_real_codec_matrix(
    level, training, decision_generation, expected_generation, card_generation, allowed
):
    conv = owner_source(training, decision_generation)
    if level != 'raw':
        conv = conversations._prepare_conversation_for_write(conv, 'u', level)
    store = StrictFirestore({USER: {}, CONV: conv})
    assert bool(pool(store, expected_generation, card_generation=card_generation)) is allowed
    assert bool(store.rows[USER].get('speaker_embedding')) is allowed


@pytest.mark.parametrize('level', ['raw', 'standard', 'enhanced'])
def test_owner_unrelated_edit_retains_exact_card_permission(level):
    conv = owner_source(False)
    conv['manual_speaker_assignments']['generation'] = 2
    conv['manual_speaker_assignments']['segments']['other'] = {
        'generation': 2,
        'person_id': 'p',
        'is_user': False,
    }
    if level != 'raw':
        conv = conversations._prepare_conversation_for_write(conv, 'u', level)
    store = StrictFirestore({USER: {}, CONV: conv})
    assert pool(store, card_generation=1) == 1


@pytest.mark.parametrize('level', ['raw', 'standard', 'enhanced'])
@pytest.mark.parametrize('changed', [False, True])
def test_legacy_no_contributors_requires_unchanged_receipt(level, changed):
    conv = owner_source(False)
    conv['manual_speaker_assignments']['generation'] = 2 if changed else 1
    if level != 'raw':
        conv = conversations._prepare_conversation_for_write(conv, 'u', level)
    store = StrictFirestore({USER: {}, CONV: conv})
    assert bool(pool(store, segment_ids=None)) is (not changed)


@pytest.mark.parametrize('flag', ['deleted', 'discarded', 'is_locked'])
def test_owner_publication_source_status(flag):
    conv = owner_source()
    conv[flag] = True
    store = StrictFirestore({USER: {}, CONV: conv})
    assert pool(store) == 0


@pytest.mark.parametrize('blob,compressed', [(b'corrupt', True), ('corrupt', True), (None, False)])
def test_bad_transcript_denies_without_write(blob, compressed):
    conv = owner_source()
    conv.update(transcript_segments=blob, transcript_segments_compressed=compressed)
    store = StrictFirestore({USER: {}, CONV: conv})
    assert pool(store) == 0


@pytest.mark.parametrize('renew_training,allowed', [(True, True), (False, False)])
def test_real_owner_label_changed_and_changed_back(monkeypatch, renew_training, allowed):
    store = StrictFirestore({USER: {}, CONV: owner_source(False), PERSON: {'id': 'p'}})
    monkeypatch.setattr(conversations, 'record_speaker_review', lambda *a: None)
    conversations.assign_conversation_speaker(
        'u',
        'c',
        segment_ids=['s'],
        person_id='p',
        firestore_client=store,
    )
    conversations.assign_conversation_speaker(
        'u',
        'c',
        segment_ids=['s'],
        is_user=True,
        use_for_speech_training=renew_training,
        firestore_client=store,
    )
    # Generation 1 belonged to the old card. Generation 3 can independently reconsent.
    assert bool(pool(store, generation=1, card_generation=1)) is allowed


@pytest.mark.parametrize('target', ['person', 'owner'])
def test_manual_teaching_survives_real_resolution(monkeypatch, target):
    conv = {
        'id': 'c',
        'transcript_segments': [
            {
                'id': 's',
                'speaker': 'SPEAKER_1',
                'speaker_id': 1,
                'speaker_id_scope': 'sync:a',
                'start': 0,
                'end': 12,
                'text': 'Synthetic person speech',
                'is_user': False,
            },
            {
                'id': 'other',
                'speaker': 'SPEAKER_2',
                'speaker_id': 2,
                'speaker_id_scope': 'sync:b',
                'start': 15,
                'end': 27,
                'text': 'Synthetic guest speech',
                'is_user': False,
            },
        ],
    }
    segments, receipt, _, _ = manual_assignment(
        conv, person_id='p' if target == 'person' else None, is_user=target == 'owner', speaker_id=1
    )
    assert receipt['speakers']['1']['speaker_id_scope'] == 'sync:a'
    conv.update(transcript_segments=segments, manual_speaker_assignments=receipt)
    if target == 'person':
        assert [s['id'] for s in authorized_teaching_segments(conv, 'p')] == ['s']
    else:
        assert authorized_owner_segments(conv, ['s']) == ['s']
    model = Conversation(
        id='c',
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        structured=Structured(),
        transcript_segments=[TranscriptSegment(**s) for s in segments],
        private_cloud_sync_enabled=True,
    )
    cache = stage.encode_cache(
        {
            's': (12.0, np.array([1.0, 0.0], dtype=np.float32)),
            'other': (12.0, np.array([0.0, 1.0], dtype=np.float32)),
        }
    )
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *a: deepcopy(receipt))
    monkeypatch.setattr(stage, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(stage, 'download_speaker_embedding_cache', lambda *a: cache)
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda *a: {})
    monkeypatch.setattr(stage, '_embed_missing', lambda *a, **kw: (0, 'complete'))
    assert stage.resolve_speakers_for_processing('u', model)
    resolved = [s.model_dump() for s in model.transcript_segments]
    conv['transcript_segments'] = resolved
    assert resolved[0]['person_id'] == ('p' if target == 'person' else None)
    assert resolved[0]['is_user'] is (target == 'owner')
    assert resolved[0]['speaker_id'] == 1
    assert resolved[0]['speaker_id_scope'] == 'conversation:c'
    store = StrictFirestore({USER: {}, CONV: conv, PERSON: {'id': 'p'}})
    if target == 'owner':
        assert pool(store) == 1, 'valid manual owner teaching was refused after scope normalization'
        return
    monkeypatch.setattr(users, 'db', store)
    result = users.replace_person_speech_profile(
        'u',
        'p',
        None,
        'sample',
        'Synthetic person speech',
        [1.0, 0.0],
        'c',
        ['s'],
        expected_receipt_generation=1,
    )
    assert result == [], 'valid manual teaching was refused solely because resolution changed capture scope'


def test_owner_window_must_not_include_opted_out_same_voice_segment():
    conv = owner_source()
    overlapping = dict(conv['transcript_segments'][0], id='optout', start=2, end=6)
    conv['transcript_segments'].append(overlapping)
    conv['manual_speaker_assignments']['generation'] = 2
    conv['manual_speaker_assignments']['segments']['optout'] = {
        'generation': 2,
        'is_user': True,
        'use_for_speech_training': False,
    }
    assert authorized_owner_segments(conv, ['s', 'optout']) == ['s']
    consented = set(authorized_owner_segments(conv, ['s', 'optout']))
    assert service.owner_clip_window(conv, ['s'], consented=consented) is None, 'clip contains opted-out speech'
    assert service.owner_clip_window(conv, ['s'], consented={'s', 'optout'}) is not None
