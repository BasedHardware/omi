import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from models.speaker_tag_prompts import (
    SpeakerTagPromptAnswer as A,
    SpeakerTagPromptAnswerRequest,
    SpeakerTagPromptKind as K,
    SpeakerTagPromptOrigin as O,
    SpeakerTagPromptQualityOutcome as Q,
)
from utils.speaker_tag_prompts import service

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


class World:
    def __init__(self, monkeypatch, *, paid=True, save_others=True, prompts_enabled=True, state=None):
        self.assignments = []
        self.scheduled = []
        self.answered = []
        self.events = []
        self.people = {'p1': {'id': 'p1', 'name': 'Sam', 'speaker_embedding': [0.1]}}
        self.created = []
        self.state = state or {}
        self.settings = {'speaker_tag_prompts_enabled': prompts_enabled, 'save_other_voice_profiles': save_others}
        db = service.voice_profiles_db
        monkeypatch.setattr(service, 'named_speaker_prompts_allowed', lambda uid: paid)
        monkeypatch.setattr(db, 'get_voice_profile_settings', lambda uid: dict(self.settings))
        monkeypatch.setattr(db, 'get_voice_profile_context', lambda uid: (dict(self.settings), True))
        monkeypatch.setattr(db, 'get_tag_prompt_state', lambda uid: dict(self.state))
        monkeypatch.setattr(db, 'record_tag_prompt_answered', lambda uid, pid, now: self.answered.append(pid))
        monkeypatch.setattr(db, 'mark_tag_prompts_empty', lambda uid, now: self.state.update(last_empty_check_at=now))
        monkeypatch.setattr(service.users_db, 'get_person', lambda uid, pid: self.people.get(pid))
        monkeypatch.setattr(service.users_db, 'get_person_by_name', lambda uid, name: None)
        monkeypatch.setattr(service.users_db, 'create_person', lambda uid, data: self.created.append(data) or data)
        monkeypatch.setattr(service.users_db, 'get_people', lambda uid: list(self.people.values()))
        monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: [])
        monkeypatch.setattr(
            service, 'emit_product_event', lambda **kwargs: self.events.append((kwargs['event'], kwargs['properties']))
        )

        def assign(uid, conversation_id, **kwargs):
            self.assignments.append(kwargs)
            segments = [{'id': 's1', 'start': 0, 'end': 9}, {'id': 's2', 'start': 9, 'end': 12}]
            return {'transcript_segments': segments}, ['s1', 's2'], [], []

        monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)

    def schedule(self, fn, **kwargs):
        self.scheduled.append((fn, kwargs))


def _request(kind, origin, answer, **extra):
    payload = dict(
        prompt_id='pid',
        kind=kind,
        origin=origin,
        conversation_id='c1',
        speaker_id=1,
        segment_ids=['s1'],
        answer=answer,
    )
    payload.update(extra)
    return SpeakerTagPromptAnswerRequest(**payload)


def test_thats_me_labels_owner_and_queues_owner_voice_sample(monkeypatch):
    world = World(monkeypatch, paid=False)
    response = service.apply_answer('u', _request(K.owner_check, O.unnamed, A.me), world.schedule, NOW)
    assert world.assignments == [
        {'person_id': None, 'is_user': True, 'speaker_id': 1, 'use_for_speech_training': False}
    ]
    assert world.scheduled[0][0] is service.store_owner_voice_sample
    assert response.voice_sample_queued and response.quality_outcome == Q.owner_missed
    assert world.answered == ['pid']
    name, properties = world.events[-1]
    assert name == 'Speaker Tag Prompt Answered'
    assert set(properties) == {'kind', 'origin', 'answer', 'quality_outcome', 'first_time', 'voice_sample_queued'}


def test_free_user_cannot_name_other_people(monkeypatch):
    world = World(monkeypatch, paid=False)
    with pytest.raises(service.TagPromptForbidden):
        service.apply_answer('u', _request(K.identify, O.unnamed, A.person, person_id='p1'), world.schedule, NOW)
    with pytest.raises(service.TagPromptForbidden):
        service.apply_answer('u', _request(K.owner_check, O.unnamed, A.new_person, name='Ana'), world.schedule, NOW)
    assert world.assignments == []


def test_naming_a_person_teaches_voice_when_allowed(monkeypatch):
    world = World(monkeypatch)
    response = service.apply_answer('u', _request(K.identify, O.unnamed, A.person, person_id='p1'), world.schedule, NOW)
    assert world.assignments[0]['person_id'] == 'p1' and world.assignments[0]['use_for_speech_training'] is True
    fn, kwargs = world.scheduled[0]
    assert fn is service.extract_speaker_samples and kwargs['segment_ids'] == ['s1', 's2']
    assert response.quality_outcome == Q.person_missed_known


def test_saving_other_voices_off_labels_without_teaching(monkeypatch):
    world = World(monkeypatch, save_others=False)
    response = service.apply_answer('u', _request(K.identify, O.unnamed, A.new_person, name='Ana'), world.schedule, NOW)
    assert world.created and world.created[0]['name'] == 'Ana'
    assert world.assignments[0]['use_for_speech_training'] is False
    assert world.scheduled == [] and not response.voice_sample_queued
    assert response.quality_outcome == Q.person_not_enrolled


def test_rejecting_an_automatic_label_clears_it(monkeypatch):
    world = World(monkeypatch)
    response = service.apply_answer('u', _request(K.owner_check, O.auto_user, A.not_me), world.schedule, NOW)
    assert world.assignments == [
        {'person_id': None, 'is_user': False, 'speaker_id': 1, 'use_for_speech_training': False}
    ]
    assert response.quality_outcome == Q.owner_auto_rejected


def test_unknown_voice_and_skip_write_nothing(monkeypatch):
    world = World(monkeypatch)
    service.apply_answer('u', _request(K.identify, O.unnamed, A.someone_else), world.schedule, NOW)
    service.apply_answer('u', _request(K.identify, O.unnamed, A.skip), world.schedule, NOW)
    assert world.assignments == [] and world.answered == ['pid', 'pid']


def test_invalid_answer_for_kind(monkeypatch):
    world = World(monkeypatch)
    with pytest.raises(service.TagPromptInvalid):
        service.apply_answer('u', _request(K.identify, O.unnamed, A.not_me), world.schedule, NOW)


@pytest.mark.parametrize(
    'origin,answer,person_id,suggested,enrolled,expected',
    [
        (O.auto_user, A.me, None, None, False, Q.owner_auto_confirmed),
        (O.auto_user, A.person, 'p1', None, True, Q.owner_auto_rejected),
        (O.auto_person, A.person, 'p1', 'p1', True, Q.person_auto_confirmed),
        (O.auto_person, A.person, 'p2', 'p1', True, Q.person_auto_corrected),
        (O.auto_person, A.me, None, 'p1', False, Q.person_auto_corrected),
        (O.unnamed, A.me, None, None, False, Q.owner_missed),
        (O.unnamed, A.not_me, None, None, False, Q.owner_unmatched_not_owner),
        (O.unnamed, A.person, 'p1', None, True, Q.person_missed_known),
        (O.unnamed, A.new_person, 'p9', None, False, Q.person_not_enrolled),
        (O.unnamed, A.someone_else, None, None, False, Q.unknown_voice),
        (O.auto_person, A.skip, None, 'p1', False, Q.skipped),
    ],
)
def test_quality_outcome_table(origin, answer, person_id, suggested, enrolled, expected):
    outcome = service.quality_outcome(
        origin, answer, person_id=person_id, suggested_person_id=suggested, person_enrolled=enrolled
    )
    assert outcome == expected


def test_prompts_respect_disabled_and_daily_cooldown(monkeypatch):
    world = World(monkeypatch, prompts_enabled=False)
    assert service.get_prompts('u', NOW).status == 'disabled'

    world = World(monkeypatch, state={'first_shown_at': NOW, 'last_shown_at': NOW - timedelta(hours=3)})
    response = service.get_prompts('u', NOW)
    assert response.status == 'cooldown' and response.first_time is False
    assert response.next_eligible_at == NOW - timedelta(hours=3) + service.SHOW_COOLDOWN


def test_repeated_dismissals_back_off_to_a_week(monkeypatch):
    world = World(monkeypatch, state={'last_shown_at': NOW - timedelta(days=2), 'consecutive_dismissals': 3})
    response = service.get_prompts('u', NOW)
    assert response.status == 'cooldown'
    assert response.next_eligible_at == NOW - timedelta(days=2) + service.DISMISSED_COOLDOWN


def test_empty_scan_is_remembered(monkeypatch):
    world = World(monkeypatch)
    first = service.get_prompts('u', NOW)
    assert first.status == 'no_candidates' and first.first_time is True
    calls = []
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: calls.append(1) or [])
    second = service.get_prompts('u', NOW + timedelta(minutes=30))
    assert second.status == 'no_candidates' and calls == []
    assert world.state['last_empty_check_at'] == NOW


def test_owner_clip_window_keeps_text_of_a_long_segment_cropped_to_the_clip():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 30, 'is_user': True, 'speaker_id': 0, 'text': 'one long owner turn'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a']) == (10.0, 20.0, 'one long owner turn')


def test_owner_clip_window_requires_clean_owner_stretch():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 4, 'is_user': True, 'text': 'one two'},
            {'id': 'b', 'start': 4, 'end': 8, 'is_user': True, 'text': 'three four'},
            {'id': 'c', 'start': 8, 'end': 9, 'is_user': False, 'text': 'x'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b']) == (0.0, 8.0, 'one two three four')
    assert service.owner_clip_window(conversation, ['a']) is None  # too short
    assert service.owner_clip_window(conversation, ['a', 'c']) is None  # not all the owner


def test_owner_clip_window_rejects_a_second_diarized_voice_even_labeled_user():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'speaker_id': 0, 'text': 'mine'},
            {'id': 'b', 'start': 3, 'end': 4, 'is_user': True, 'speaker_id': 1, 'text': 'theirs'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a']) is None


def test_owner_clip_window_uses_only_text_inside_the_clip():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 3, 'is_user': True, 'speaker_id': 0, 'text': 'outside before'},
            {'id': 'b', 'start': 5, 'end': 15, 'is_user': True, 'speaker_id': 0, 'text': 'inside clip'},
            {'id': 'c', 'start': 17, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': 'outside after'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b', 'c']) == (5.0, 15.0, 'inside clip')
    no_inside_text = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'speaker_id': 0, 'text': ''},
            {'id': 'b', 'start': 8, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': ''},
        ]
    }
    assert service.owner_clip_window(no_inside_text, ['a', 'b']) is None


def test_owner_sample_verifies_only_text_inside_the_clip(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 3, 'is_user': True, 'speaker_id': 0, 'text': 'outside before'},
            {'id': 'b', 'start': 5, 'end': 15, 'is_user': True, 'speaker_id': 0, 'text': 'inside clip'},
            {'id': 'c', 'start': 17, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': 'outside after'},
        ],
    }
    clipped = []
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(
        service,
        'conversation_clip_pcm',
        lambda uid, conv, start, end: clipped.append((start, end)) or b'\x01\x00' * 16000,
    )

    async def verify(wav, rate, text, language=None):
        assert text == 'inside clip'
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[1.0, 0.0]], dtype=np.float32))
    monkeypatch.setattr(
        service.voice_profiles_db, 'add_owner_voice_confirmation', lambda uid, embedding, pool, conversation_id: 1
    )
    assert asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a', 'b', 'c'])) == 'stored'
    assert clipped == [(5.0, 15.0)]


def test_owner_sample_gets_only_prompt_segments_still_assigned(monkeypatch):
    world = World(monkeypatch, paid=False)

    def assign(uid, conversation_id, **kwargs):
        return {'transcript_segments': [{'id': 's1', 'start': 0, 'end': 9}]}, ['s1', 's9'], [], []

    monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)
    response = service.apply_answer(
        'u', _request(K.owner_check, O.unnamed, A.me, segment_ids=['s1', 'stale']), world.schedule, NOW
    )
    fn, kwargs = world.scheduled[0]
    assert fn is service.store_owner_voice_sample and kwargs['segment_ids'] == ['s1']
    assert response.voice_sample_queued


def test_owner_sample_not_queued_when_prompt_segments_are_gone(monkeypatch):
    world = World(monkeypatch, paid=False)

    def assign(uid, conversation_id, **kwargs):
        return {'transcript_segments': [{'id': 's9', 'start': 0, 'end': 9}]}, ['s9'], [], []

    monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)
    response = service.apply_answer(
        'u', _request(K.owner_check, O.unnamed, A.me, segment_ids=['s1']), world.schedule, NOW
    )
    assert world.scheduled == [] and not response.voice_sample_queued


def test_owner_sample_is_verified_then_pooled(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [{'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'text': 'hello there friend'}],
    }
    pooled = []
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *a: b'\x01\x00' * 16000)

    async def verify(wav, rate, text, language=None):
        assert text == 'hello there friend' and language == 'en'
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[3.0, 4.0]], dtype=np.float32))
    monkeypatch.setattr(
        service.voice_profiles_db,
        'add_owner_voice_confirmation',
        lambda uid, embedding, pool, conversation_id: pooled.append((embedding, pool([embedding]))) or 1,
    )
    outcome = asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a']))
    assert outcome == 'stored'
    assert pooled[0][0] == [3.0, 4.0]
    assert pooled[0][1] == pytest.approx([0.6, 0.8])


def test_owner_sample_rejected_by_quality_gate_is_not_pooled(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [{'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'text': 'hi'}],
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *a: b'\x01\x00' * 16000)

    async def verify(wav, rate, text, language=None):
        return None, False, 'multi_speaker: ratio=0.40'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(
        service.voice_profiles_db, 'add_owner_voice_confirmation', lambda *a, **k: pytest.fail('must not pool')
    )
    assert asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a'])) == 'rejected_quality'
