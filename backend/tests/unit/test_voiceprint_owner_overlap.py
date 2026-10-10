"""Owner clip overlap consent and scope boundaries, through the real assignment and publication paths."""

import asyncio
from copy import deepcopy

import numpy as np
import pytest

from database import conversations, speaker_learning_jobs, voice_profiles
from models.speaker_tag_prompts import SpeakerTagPromptAnswerRequest
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.owner_voice_evidence import authorized_owner_segments
from utils.speaker_assignment_teaching import commit_manual_assignment
from utils.speaker_learning_policy import winning_receipt_decision
from utils.speaker_tag_prompts import service, selection

USER = ('users', 'u')
CONV = (*USER, 'conversations', 'c')


def decoded(store):
    raw = deepcopy(store.rows[CONV])
    raw['transcript_segments'] = conversations.decode_transcript_segments_verified(
        'u', raw['transcript_segments'], bool(raw.get('transcript_segments_compressed'))
    )
    raw['manual_speaker_assignments'] = conversations.decode_manual_speaker_assignments(
        'u', raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )
    raw['transcript_segments_compressed'] = False
    raw['manual_speaker_assignments_compressed'] = False
    return raw


@pytest.mark.parametrize('source', [None, 'manual', 'carried'])
@pytest.mark.parametrize('scope', ['sync:a', 'sync:b', None, 'conversation:c'])
def test_scope_boundary(source, scope):
    decision = dict(generation=1, speaker_id_scope='sync:a', is_user=True)
    if source is not None:
        decision['source'] = source
    receipt = {'speakers': {'1': decision}}
    segment = dict(id='s', speaker_id=1, speaker_id_scope=scope)
    expected = scope == 'sync:a' or (scope == 'conversation:c' and source != 'carried')
    assert (winning_receipt_decision(receipt, segment) == decision) is expected


def test_scope_denial_keeps_independent_segment_override():
    explicit = dict(generation=1, is_user=True)
    receipt = {
        'segments': {'s': explicit},
        'speakers': {'1': dict(generation=2, is_user=False, speaker_id_scope='sync:a')},
    }
    assert winning_receipt_decision(receipt, dict(id='s', speaker_id=1, speaker_id_scope='sync:b')) == explicit


def test_legacy_unscoped_speaker_receipt_still_applies():
    decision = dict(generation=1, is_user=True)
    assert (
        winning_receipt_decision({'speakers': {'1': decision}}, dict(id='s', speaker_id=1, speaker_id_scope='sync:b'))
        == decision
    )


class Tasks:
    def __init__(self):
        self.calls = []

    def add_task(self, fn, **kwargs):
        self.calls.append((fn, kwargs))


@pytest.fixture
def world(monkeypatch):
    raw = {
        'id': 'c',
        'language': 'en',
        'transcript_segments': [
            dict(
                id='s',
                speaker_id=1,
                speaker_id_scope='sync:a',
                start=0,
                end=8,
                text='Synthetic owner speech',
                is_user=False,
            ),
            dict(
                id='other',
                speaker_id=1,
                speaker_id_scope='sync:a',
                start=2,
                end=6,
                text='Synthetic owner speech',
                is_user=False,
            ),
        ],
    }
    store = StrictFirestore({USER: {}, CONV: raw})
    original_assign = conversations.assign_conversation_speaker
    original_pool = voice_profiles.add_owner_voice_confirmation
    monkeypatch.setattr(conversations, 'record_speaker_review', lambda *a: None)
    monkeypatch.setattr(
        conversations, 'assign_conversation_speaker', lambda *a, **kw: original_assign(*a, **kw, firestore_client=store)
    )
    monkeypatch.setattr(speaker_learning_jobs, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(conversations, 'get_conversation', lambda *a: decoded(store))
    monkeypatch.setattr(voice_profiles, 'record_tag_prompt_answered', lambda *a: None)
    monkeypatch.setattr(service, 'emit_product_event', lambda **kw: None)
    reads = []

    def clip(uid, conversation, start, end, **kwargs):
        reads.append((start, end))
        return b'\x01\x00' * int((end - start) * service.CLIP_SAMPLE_RATE)

    async def verify(*args, **kwargs):
        return 'Synthetic owner speech', True, 'passed'

    monkeypatch.setattr(service, 'conversation_clip_pcm', clip)
    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[0.0, 1.0]]))
    monkeypatch.setattr(
        voice_profiles, 'add_owner_voice_confirmation', lambda *a, **kw: original_pool(*a, **kw, firestore_client=store)
    )
    return store, reads


def assign(**kwargs):
    tasks = Tasks()
    commit_manual_assignment('u', 'c', person_id=None, is_user=True, background_tasks=tasks, **kwargs)
    return tasks


def run_task(tasks):
    fn, kwargs = tasks.calls[-1]
    return asyncio.run(fn(**kwargs))


def test_whole_speaker_label_still_teaches(world):
    store, reads = world
    tasks = assign(speaker_id=1)
    assert tasks.calls[-1][1]['segment_ids'] == ['s', 'other']
    assert run_task(tasks) == 'stored'
    assert reads == [(0.0, 8.0)]
    assert store.rows[USER]['owner_voice_confirmations'][0]['segment_ids'] == ['s', 'other']


def test_segment_tag_with_already_consented_overlap_should_teach(world):
    store, reads = world
    assign(segment_ids=['other'])
    tasks = assign(segment_ids=['s'])
    assert authorized_owner_segments(decoded(store), ['s', 'other']) == ['s', 'other']
    assert tasks.calls[-1][1]['segment_ids'] == ['s']
    outcome = run_task(tasks)
    assert outcome == 'stored', f'valid overlap consent refused: {outcome}; audio reads={reads}'
    assert store.rows[USER]['owner_voice_confirmations'][0]['segment_ids'] == ['s', 'other']


def test_naming_card_owner_grant_with_selected_run_should_teach(world):
    store, reads = world
    assign(segment_ids=['other'])
    raw = decoded(store)
    _, decided = selection._manually_decided(raw)
    runs = selection._runs(selection._normalized_segments(raw), decided)
    assert runs[0].segment_ids == ('s',)
    # Paid naming/tag cards retain their existing explicit owner-learning action;
    # the free owner_check path is label-only and covered by test_owner_confirmation_scope.
    request = SpeakerTagPromptAnswerRequest(
        prompt_id='pid',
        kind='identify',
        origin='unnamed',
        conversation_id='c',
        speaker_id=1,
        segment_ids=list(runs[0].segment_ids),
        answer='me',
    )
    tasks = Tasks()
    response = service.apply_answer('u', request, tasks.add_task)
    assert response.voice_sample_queued
    job = tasks.calls[-1][1]
    assert job['segment_ids'] == ['s']
    assert authorized_owner_segments(decoded(store), ['s', 'other'], card_generation=job['card_generation']) == [
        's',
        'other',
    ]
    outcome = run_task(tasks)
    assert outcome == 'stored', f'valid exact card consent refused: {outcome}; audio reads={reads}'
    assert store.rows[USER]['owner_voice_confirmations'][0]['segment_ids'] == ['s', 'other']


@pytest.mark.parametrize(
    'other_kind,expected',
    [
        ('optout', 'clip_not_clean'),
        ('unconfirmed', 'clip_not_clean'),
        ('adjacent', 'stored'),
        ('cross_scope', 'stored'),
        ('foreign_speaker', 'clip_not_clean'),
    ],
)
def test_overlap_controls(world, other_kind, expected):
    store, reads = world
    assign(segment_ids=['other'], use_for_speech_training=other_kind != 'optout')
    store.rows[CONV] = decoded(store)
    other = store.rows[CONV]['transcript_segments'][1]
    if other_kind == 'unconfirmed':
        store.rows[CONV]['manual_speaker_assignments']['segments'].pop('other')
    elif other_kind == 'adjacent':
        other.update(start=8, end=12)
    elif other_kind == 'cross_scope':
        other['speaker_id_scope'] = 'sync:b'
    elif other_kind == 'foreign_speaker':
        other['speaker_id'] = 2
    assert run_task(assign(segment_ids=['s'])) == expected
    assert bool(reads) is (expected == 'stored')
