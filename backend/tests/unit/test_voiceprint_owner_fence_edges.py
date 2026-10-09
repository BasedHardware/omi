"""Owner publication and retraction across every contributor, real codecs and zero-duration text."""

import asyncio
from copy import deepcopy

import pytest

from database import conversations, voice_profiles
from models.speaker_tag_prompts import SpeakerTagPromptAnswerRequest
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator
from tests.unit.test_voiceprint_owner_overlap import world, assign, decoded, run_task, Tasks, USER, CONV
from utils.speaker_tag_prompts import service


def queued(world, card):
    store, reads = world
    assign(segment_ids=['other'])
    if not card:
        return assign(segment_ids=['s'])
    tasks = Tasks()
    request = SpeakerTagPromptAnswerRequest(
        prompt_id='pid',
        kind='owner_check',
        origin='unnamed',
        conversation_id='c',
        speaker_id=1,
        segment_ids=['s'],
        answer='me',
    )
    service.apply_answer('u', request, tasks.add_task)
    return tasks


@pytest.mark.parametrize('card', [False, True])
@pytest.mark.parametrize('target', ['s', 'other'])
@pytest.mark.parametrize('edit', ['optout', 'not_owner', 'missing'])
def test_every_contributor_rechecked_after_verification(world, monkeypatch, card, target, edit):
    store, reads = world
    tasks = queued(world, card)

    async def verify(*args, **kwargs):
        if edit == 'missing':
            raw = decoded(store)
            raw['transcript_segments'] = [s for s in raw['transcript_segments'] if s['id'] != target]
            store.rows[CONV] = raw
        else:
            conversations.assign_conversation_speaker(
                'u', 'c', segment_ids=[target], is_user=edit != 'not_owner', use_for_speech_training=False
            )
        return 'Synthetic owner speech', True, 'passed'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert run_task(tasks) == 'stale_assignment'
    assert reads == [(0.0, 8.0)]
    assert not store.rows[USER].get('owner_voice_confirmations')


@pytest.mark.parametrize('card', [False, True])
@pytest.mark.parametrize('target', ['s', 'other'])
@pytest.mark.parametrize('edit', ['optout', 'not_owner'])
def test_either_contributor_retracts_after_publication(world, card, target, edit):
    store, reads = world
    tasks = queued(world, card)
    assert run_task(tasks) == 'stored'
    assert store.rows[USER]['owner_voice_confirmations'][0]['segment_ids'] == ['s', 'other']
    conversations.assign_conversation_speaker(
        'u', 'c', segment_ids=[target], is_user=edit != 'not_owner', use_for_speech_training=False
    )
    assert store.rows[USER]['owner_voice_confirmations'] == []
    assert store.rows[USER]['speaker_embedding'] is None


def add_unrelated(store):
    raw = decoded(store)
    raw['transcript_segments'].append(
        dict(raw['transcript_segments'][0], id='unrelated', start=20, end=28, speaker_id=2, is_user=False)
    )
    store.rows[CONV] = raw


@pytest.mark.parametrize('card', [False, True])
def test_unrelated_edit_keeps_exact_card_and_training_grants(world, monkeypatch, card):
    store, reads = world
    add_unrelated(store)
    tasks = queued(world, card)

    async def verify(*args, **kwargs):
        assign(segment_ids=['unrelated'])
        return 'Synthetic owner speech', True, 'passed'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert run_task(tasks) == 'stored'
    confirmation = deepcopy(store.rows[USER]['owner_voice_confirmations'])
    assert confirmation[0]['segment_ids'] == ['s', 'other']
    assign(segment_ids=['unrelated'], use_for_speech_training=False)
    assert store.rows[USER]['owner_voice_confirmations'] == confirmation


@pytest.mark.parametrize('level', ['raw', 'standard', 'enhanced'])
def test_wider_publication_and_retraction_use_real_codecs(world, level):
    store, reads = world
    store.rows[CONV]['data_protection_level'] = level
    tasks = queued(world, False)
    assert run_task(tasks) == 'stored'
    assert store.rows[USER]['owner_voice_confirmations'][0]['segment_ids'] == ['s', 'other']
    assign(segment_ids=['other'], use_for_speech_training=False)
    assert not store.rows[USER]['owner_voice_confirmations']


def test_retraction_keeps_base_and_other_conversations(world):
    store, reads = world
    store.rows[USER]['speaker_embedding'] = [1.0, 0.0]
    other_conv = deepcopy(store.rows[CONV])
    other_conv.update(
        id='c2',
        transcript_segments=[dict(other_conv['transcript_segments'][0], id='third', is_user=True)],
        manual_speaker_assignments={'generation': 1, 'segments': {'third': {'generation': 1, 'is_user': True}}},
    )
    store.rows[(*USER, 'conversations', 'c2')] = other_conv
    assert (
        voice_profiles.add_owner_voice_confirmation(
            'u', [1.0, 1.0], service._pool, conversation_id='c2', expected_receipt_generation=1, segment_ids=['third']
        )
        == 1
    )
    assert run_task(queued(world, False)) == 'stored'
    assign(segment_ids=['other'], use_for_speech_training=False)
    assert store.rows[USER]['speaker_embedding_base'] == [1.0, 0.0]
    assert [c['conversation_id'] for c in store.rows[USER]['owner_voice_confirmations']] == ['c2']
    assert store.rows[USER]['speaker_embedding']


def test_mixed_card_and_earlier_explicit_training_permission(world):
    store, reads = world
    assign(segment_ids=['other'])
    assign(segment_ids=['s'], use_for_speech_training=False)
    generation = decoded(store)['manual_speaker_assignments']['generation']
    assert asyncio.run(service.store_owner_voice_sample('u', 'c', ['s'], card_generation=generation)) == 'stored'
    assert store.rows[USER]['owner_voice_confirmations'][0]['segment_ids'] == ['s', 'other']


def put_zero_duration_point(store):
    raw = decoded(store)
    for segment in raw['transcript_segments']:
        segment['speaker_id_scope'] = 'live:epoch-a'
    timeline = CaptureTimeline(sample_rate=16000)
    timeline.accept(b'\x00\x00' * 64000, arrival_wall=4.0, arrival_monotonic=4.0)
    translator = ProviderEpochTranslator(timeline, 16000, project_times=False)
    original = dict(raw['transcript_segments'][1], start=4.0, end=4.0)
    point = translator.translate([original])[0]
    assert point['start'] == point['end'] == 4.0 and point.get('audio_alignment') is None
    for key in list(point):
        if key.startswith('_'):
            point.pop(key)
    raw['transcript_segments'][1] = point
    store.rows[CONV] = raw


def test_zero_duration_point_must_not_be_recorded_as_audio_contributor(world):
    store, reads = world
    put_zero_duration_point(store)
    tasks = queued(world, False)
    assert run_task(tasks) == 'stored'
    actual = store.rows[USER]['owner_voice_confirmations'][0]['segment_ids']
    assert actual == ['s'], f'zero-duration point counted as audio contributor: {actual}'


def test_correcting_zero_duration_point_must_preserve_sample(world):
    store, reads = world
    put_zero_duration_point(store)
    assert run_task(queued(world, False)) == 'stored'
    conversations.assign_conversation_speaker(
        'u', 'c', segment_ids=['other'], is_user=False, use_for_speech_training=False
    )
    assert store.rows[USER]['owner_voice_confirmations'], 'zero-duration text retracted valid speech'


def test_correcting_zero_duration_point_during_verification_must_not_block_publication(world, monkeypatch):
    store, reads = world
    put_zero_duration_point(store)
    tasks = queued(world, False)

    async def verify(*args, **kwargs):
        conversations.assign_conversation_speaker(
            'u', 'c', segment_ids=['other'], is_user=False, use_for_speech_training=False
        )
        return 'Synthetic owner speech', True, 'passed'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    outcome = run_task(tasks)
    assert outcome == 'stored', f'zero-duration text blocked publication: {outcome}'
