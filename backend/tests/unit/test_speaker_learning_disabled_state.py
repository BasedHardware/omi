"""save_other_voice_profiles=False gates person voice-learning state at assignment time.

The real ``assign_conversation_speaker`` transaction reads the user settings doc and
writes ``disabled`` instead of ``pending`` when consent is off, so a label never
leaves a phantom pending state with no queued job. StrictFirestore only.
"""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import conversations as db
from models.other import Person
from models.speaker_tag_prompts import (
    SpeakerTagPromptAnswer,
    SpeakerTagPromptAnswerRequest,
    SpeakerTagPromptKind,
    SpeakerTagPromptOrigin,
)
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.speaker_tag_prompts import service

UID = 'uid-disabled-state'
CONV = 'conv-d'
PERSON = 'p1'
NOW = datetime(2026, 2, 1, tzinfo=timezone.utc)
USER_PATH = ('users', UID)
PERSON_PATH = ('users', UID, 'people', PERSON)
CONV_PATH = ('users', UID, 'conversations', CONV)


def _segment(seg_id, *, speaker_id=4, person_id=None):
    return {
        'id': seg_id,
        'start': 0.0,
        'end': 5.0,
        'speaker_id': speaker_id,
        'is_user': False,
        'person_id': person_id,
        'text': 'words',
    }


@pytest.fixture
def world(monkeypatch):
    store = StrictFirestore()
    store.rows[CONV_PATH] = dict(
        id=CONV,
        status='completed',
        transcript_segments=[_segment('s0'), _segment('s1'), _segment('s2', speaker_id=7)],
    )
    store.rows[USER_PATH] = {'save_other_voice_profiles': True}
    store.rows[PERSON_PATH] = dict(id=PERSON, name='Sam')
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    return SimpleNamespace(store=store)


def saved_person(world, pid=PERSON):
    return deepcopy(world.store.rows[('users', UID, 'people', pid)])


@pytest.mark.parametrize('use_for_speech_training', [True, False])
def test_consent_false_marks_target_disabled(world, use_for_speech_training):
    world.store.rows[USER_PATH]['save_other_voice_profiles'] = False
    db.assign_conversation_speaker(
        UID, CONV, person_id=PERSON, speaker_id=4, use_for_speech_training=use_for_speech_training
    )
    saved = saved_person(world)
    assert saved['voice_learning_state'] == 'disabled'
    assert saved['voice_learning_outcome'] == 'disabled'
    assert saved['voice_needed_seconds'] is None
    assert saved['updated_at'] is not None
    assert Person(**saved).voice_learning_state == 'disabled'


def test_consent_false_ready_person_keeps_profile_intact(world):
    world.store.rows[USER_PATH]['save_other_voice_profiles'] = False
    world.store.rows[PERSON_PATH].update(
        speaker_embedding=[0.1, 0.2],
        speech_samples=['a.wav'],
        speech_samples_version=3,
        voice_speech_seconds=12.0,
    )
    db.assign_conversation_speaker(UID, CONV, person_id=PERSON, speaker_id=4)
    saved = saved_person(world)
    assert saved['speech_samples'] == ['a.wav']
    assert saved['speaker_embedding'] == [0.1, 0.2]
    assert saved['voice_speech_seconds'] == 12.0, 'stored speech seconds are preserved'
    assert Person(**saved).voice_learning_state == 'disabled'


def test_consent_true_records_pending(world):
    db.assign_conversation_speaker(UID, CONV, person_id=PERSON, speaker_id=4)
    saved = saved_person(world)
    assert saved['voice_learning_state'] == 'pending'
    assert Person(**saved).voice_learning_state == 'pending'


def test_missing_flag_defaults_to_consent(world):
    del world.store.rows[USER_PATH]
    db.assign_conversation_speaker(UID, CONV, person_id=PERSON, speaker_id=4)
    assert saved_person(world)['voice_learning_state'] == 'pending'


def test_consent_true_ready_person_deserializes_learned(world):
    world.store.rows[PERSON_PATH].update(speaker_embedding=[0.1], speech_samples=['a.wav'], speech_samples_version=3)
    db.assign_conversation_speaker(UID, CONV, person_id=PERSON, speaker_id=4)
    assert Person(**saved_person(world)).voice_learning_state == 'learned'


def test_invalidated_profile_records_disabled_when_consent_off(world):
    donor = ('users', UID, 'people', 'p2')
    world.store.rows[donor] = {
        'id': 'p2',
        'name': 'Rae',
        'speech_samples': ['x.wav'],
        'speaker_embedding': [0.1],
        'speech_sample_source': {'conversation_id': CONV, 'segment_ids': ['s0', 's1']},
    }
    world.store.rows[CONV_PATH]['transcript_segments'] = [
        _segment('s0', person_id='p2'),
        _segment('s1', person_id='p2'),
        _segment('s2', speaker_id=7),
    ]
    world.store.rows[USER_PATH]['save_other_voice_profiles'] = False
    db.assign_conversation_speaker(UID, CONV, person_id=PERSON, speaker_id=4)
    saved = saved_person(world, 'p2')
    assert saved['speech_samples'] == []
    assert saved['speaker_embedding'] is None
    assert saved['voice_learning_state'] == 'disabled'


def test_tag_prompt_person_answer_consent_false_schedules_nothing(world, monkeypatch):
    world.store.rows[USER_PATH]['save_other_voice_profiles'] = False
    monkeypatch.setattr(service, 'named_speaker_prompts_allowed', lambda uid: True)
    monkeypatch.setattr(
        service.voice_profiles_db,
        'get_voice_profile_settings',
        lambda uid: {'save_other_voice_profiles': False},
    )
    monkeypatch.setattr(service.users_db, 'get_person', lambda uid, pid: saved_person(world, pid))
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompt_answered', lambda *a, **k: None)
    monkeypatch.setattr(service, 'emit_product_event', lambda **k: None)
    scheduled = []
    request = SpeakerTagPromptAnswerRequest(
        prompt_id='pid',
        kind=SpeakerTagPromptKind.identify,
        origin=SpeakerTagPromptOrigin.unnamed,
        conversation_id=CONV,
        speaker_id=4,
        segment_ids=['s0'],
        answer=SpeakerTagPromptAnswer.person,
        person_id=PERSON,
    )
    response = service.apply_answer(UID, request, lambda fn, **kwargs: scheduled.append((fn, kwargs)), NOW)
    assert scheduled == [], 'consent off queues no voice extraction job'
    assert response.voice_sample_queued is False
    assert Person(**saved_person(world)).voice_learning_state == 'disabled'
