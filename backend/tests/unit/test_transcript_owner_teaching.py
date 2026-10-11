"""C3: manual ``is_user`` assignment teaches the owner voiceprint.

The assign endpoints queue ``run_authorized_owner_learning`` on the canonical
resolved conversation when the label is the owner and training is on; person
and unassign paths are unchanged. The window picker is exercised directly for
run/gap/purity semantics, and one test drives the real
``store_owner_voice_sample`` into StrictFirestore.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import voice_profiles
from models.conversation import Conversation
from models.structured import Structured
from routers import conversations as conversations_router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import speaker_assignment_teaching as teaching_tasks
from utils.other import endpoints as auth
from utils.speaker_tag_prompts import service

UID = 'uid-owner-teaching'
CONV = 'conv-1'
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _segment(seg_id, start, end, *, speaker_id=0, is_user=False, person_id=None, scope=None, text='words'):
    segment = {
        'id': seg_id,
        'start': start,
        'end': end,
        'speaker_id': speaker_id,
        'is_user': is_user,
        'person_id': person_id,
        'text': text,
    }
    if scope:
        segment['speaker_id_scope'] = scope
    return segment


def _conversation_model(segments):
    return Conversation(
        id=CONV,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        structured=Structured(title='t', overview='o'),
        transcript_segments=[
            {
                'id': s['id'],
                'text': s.get('text', ''),
                'is_user': s.get('is_user', False),
                'person_id': s.get('person_id'),
                'speaker_id': s.get('speaker_id'),
                'start': s['start'],
                'end': s['end'],
            }
            for s in segments
        ],
    )


@pytest.fixture
def world(monkeypatch):
    scheduled = {'owner': [], 'person': [], 'deleted': []}
    monkeypatch.setattr(
        teaching_tasks,
        'run_authorized_owner_learning',
        lambda **kwargs: scheduled['owner'].append(kwargs),
    )
    monkeypatch.setattr(
        teaching_tasks,
        'run_authorized_person_learning',
        lambda **kwargs: scheduled['person'].append(kwargs),
    )
    monkeypatch.setattr(teaching_tasks, 'delete_speech_profile_blob', lambda path: scheduled['deleted'].append(path))
    monkeypatch.setattr(conversations_router, 'emit_product_event', lambda **kwargs: None)
    monkeypatch.setattr(
        conversations_router, 'deserialize_conversation', lambda raw: _conversation_model(raw['transcript_segments'])
    )
    world = SimpleNamespace(
        scheduled=scheduled,
        assignments=[],
        assign_fn=lambda uid, conversation_id, **kwargs: (
            {'id': conversation_id, 'transcript_segments': []},
            [],
            [],
            [],
        ),
    )

    def assign(uid, conversation_id, **kwargs):
        world.assignments.append(kwargs)
        return world.assign_fn(uid, conversation_id, **kwargs)

    monkeypatch.setattr(conversations_router.conversations_db, 'assign_conversation_speaker', assign)
    # Free plan for every route test: labeling your own transcript is never a paid action.
    monkeypatch.setattr('utils.speaker_permissions.users_db.get_user_valid_subscription', lambda uid, **kwargs: None)
    app = FastAPI()
    app.include_router(conversations_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    world.client = TestClient(app)
    return world


def _set_assign_result(world, segments, resolved, removed=(), before=(), raw_id=CONV):
    world.assign_fn = lambda uid, conversation_id, **kwargs: (
        {'id': raw_id, 'transcript_segments': segments},
        list(resolved),
        list(removed),
        list(before),
    )


def test_speaker_endpoint_is_user_queues_owner_sample(world):
    segments = [
        _segment('s1', 0.0, 6.0, is_user=True),
        _segment('s2', 7.0, 12.0, is_user=True),
    ]
    _set_assign_result(world, segments, resolved=['s1', 's2'])
    response = world.client.patch(
        f'/v1/conversations/{CONV}/assign-speaker/0', params={'assign_type': 'is_user', 'value': 'true'}
    )
    assert response.status_code == 200
    assert world.assignments[0]['is_user'] is True and world.assignments[0]['speaker_id'] == 0
    assert world.scheduled['owner'] == [{'uid': UID, 'conversation_id': CONV, 'segment_ids': ['s1', 's2']}]


def test_segment_endpoint_is_user_queues_owner_sample(world):
    _set_assign_result(world, [_segment('s1', 0.0, 8.0, is_user=True)], resolved=['s1'])
    response = world.client.patch(
        f'/v1/conversations/{CONV}/segments/0/assign', params={'assign_type': 'is_user', 'value': '1'}
    )
    assert response.status_code == 200
    assert world.scheduled['owner'] == [{'uid': UID, 'conversation_id': CONV, 'segment_ids': ['s1']}]


def test_bulk_endpoint_is_user_queues_owner_sample(world):
    segments = [_segment('s1', 0.0, 8.0, is_user=True), _segment('s2', 9.0, 14.0, is_user=True)]
    _set_assign_result(world, segments, resolved=['s1', 's2'])
    response = world.client.patch(
        f'/v1/conversations/{CONV}/segments/assign-bulk',
        json={'assign_type': 'is_user', 'value': 'true', 'segment_ids': ['s1', 's2']},
    )
    assert response.status_code == 200
    assert world.scheduled['owner'] == [{'uid': UID, 'conversation_id': CONV, 'segment_ids': ['s1', 's2']}]


def test_merged_conversation_uses_canonical_id(world):
    _set_assign_result(world, [_segment('s1', 0.0, 8.0, is_user=True)], resolved=['s1'], raw_id='survivor-9')
    response = world.client.patch(
        f'/v1/conversations/{CONV}/assign-speaker/0', params={'assign_type': 'is_user', 'value': 'true'}
    )
    assert response.status_code == 200
    assert world.scheduled['owner'] == [{'uid': UID, 'conversation_id': 'survivor-9', 'segment_ids': ['s1']}]


def test_is_user_false_and_training_false_queue_nothing(world):
    _set_assign_result(world, [_segment('s1', 0.0, 8.0)], resolved=['s1'])
    for params in (
        {'assign_type': 'is_user', 'value': 'false'},
        {'assign_type': 'is_user', 'value': 'true', 'use_for_speech_training': 'false'},
    ):
        response = world.client.patch(f'/v1/conversations/{CONV}/assign-speaker/0', params=params)
        assert response.status_code == 200
    assert world.scheduled['owner'] == [] and world.scheduled['person'] == []


def test_person_assignment_keeps_person_teaching(world):
    segments = [_segment('s1', 0.0, 8.0, person_id='p1')]
    _set_assign_result(world, segments, resolved=['s1'], removed=['old.wav'], before=segments)
    response = world.client.patch(
        f'/v1/conversations/{CONV}/assign-speaker/0', params={'assign_type': 'person_id', 'value': 'p1'}
    )
    assert response.status_code == 200
    assert world.scheduled['person'] == [
        {'uid': UID, 'person_id': 'p1', 'conversation_id': CONV, 'segment_ids': ['s1']}
    ]
    assert world.scheduled['deleted'] == ['old.wav']


def test_owner_teaching_never_checks_named_entitlement(world, monkeypatch):
    def banned(uid):
        raise AssertionError('owner teaching must not consult the named-people entitlement')

    monkeypatch.setattr(service, 'named_speaker_prompts_allowed', banned)
    _set_assign_result(world, [_segment('s1', 0.0, 8.0, is_user=True)], resolved=['s1'])
    response = world.client.patch(
        f'/v1/conversations/{CONV}/assign-speaker/0', params={'assign_type': 'is_user', 'value': 'true'}
    )
    assert response.status_code == 200
    assert world.scheduled['owner']


def test_owner_window_allows_split_same_voice_run():
    conversation = {
        'transcript_segments': [
            _segment('a', 0.0, 3.0, is_user=True, text='alpha part'),
            _segment('b', 3.5, 6.5, is_user=True, text='beta part'),
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b']) == (0.0, 6.5, 'alpha part beta part')


def test_owner_window_ignores_cross_scope_duplicate():
    conversation = {
        'transcript_segments': [
            _segment('a', 0.0, 6.0, is_user=True, scope='rt', text='owner speech'),
            _segment('dup', 0.0, 6.0, speaker_id=3, is_user=True, scope='v2', text='owner speech'),
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'dup']) == (0.0, 6.0, 'owner speech')


def test_owner_window_rejects_same_scope_foreign_voice():
    conversation = {
        'transcript_segments': [
            _segment('a', 0.0, 8.0, is_user=True),
            _segment('intruder', 2.0, 4.0, speaker_id=1, person_id='p9'),
        ]
    }
    assert service.owner_clip_window(conversation, ['a']) is None


def test_owner_window_rejects_gap_separated_short_runs():
    conversation = {
        'transcript_segments': [
            _segment('a', 0.0, 1.0, is_user=True),
            _segment('b', 30.0, 31.0, is_user=True),
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b']) is None


def test_owner_window_rejects_unplaced_candidate():
    conversation = {
        'transcript_segments': [
            _segment('a', 0.0, 8.0, is_user=True),
            {**_segment('b', 9.0, 10.0, is_user=True), 'audio_alignment': 'unplaced'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b']) is None


def test_owner_window_rejects_nonowner_target():
    conversation = {'transcript_segments': [_segment('a', 0.0, 8.0, person_id='p9')]}
    assert service.owner_clip_window(conversation, ['a']) is None


def test_owner_window_rechecks_speech_after_crop():
    conversation = {
        'transcript_segments': [
            _segment('a', 0.0, 2.0, is_user=True),
            _segment('b', 3.4, 4.4, is_user=True),
            _segment('c', 5.8, 6.8, is_user=True),
            _segment('d', 8.2, 9.2, is_user=True),
            _segment('e', 10.6, 11.6, is_user=True),
        ]
    }
    assert (
        service.owner_clip_window(conversation, ['a', 'b', 'c', 'd', 'e']) is None
    ), 'the cropped 10s window holds only ~4.4s of owner speech even though the run holds 6s'


def test_decoded_pcm_below_floor_fails_before_embedding(monkeypatch):
    conversation = {
        'id': CONV,
        'language': 'en',
        'transcript_segments': [_segment('a', 0.0, 8.0, is_user=True, text='hello there friend')],
    }
    conversation['manual_speaker_assignments'] = {
        'generation': 1,
        'segments': {s['id']: {'generation': 1, 'is_user': True} for s in conversation['transcript_segments']},
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(
        service, 'conversation_clip_pcm', lambda *a, **kwargs: b'\x01\x00' * int(service.CLIP_SAMPLE_RATE * 4.8)
    )
    monkeypatch.setattr(
        service, 'extract_embedding_from_bytes', lambda *a: pytest.fail('embedding must not run on short audio')
    )

    async def verify(wav, rate, text, language=None):
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert asyncio.run(service.store_owner_voice_sample(UID, CONV, ['a'])) == 'clip_not_clean'


def test_oversized_pcm_is_capped_to_the_window(monkeypatch):
    conversation = {
        'id': CONV,
        'language': 'en',
        'transcript_segments': [_segment('a', 0.0, 8.0, is_user=True, text='hello there friend')],
    }
    conversation['manual_speaker_assignments'] = {
        'generation': 1,
        'segments': {s['id']: {'generation': 1, 'is_user': True} for s in conversation['transcript_segments']},
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(
        service, 'conversation_clip_pcm', lambda *a, **kwargs: b'\x01\x00' * int(service.CLIP_SAMPLE_RATE * 20)
    )
    captured = {}

    async def verify(wav, rate, text, language=None):
        captured['wav_seconds'] = (len(wav) - 44) / (rate * 2)
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[1.0, 0.0]], dtype=np.float32))
    monkeypatch.setattr(
        service.voice_profiles_db,
        'add_owner_voice_confirmation',
        lambda uid, embedding, pool, **kwargs: 1,
    )
    assert asyncio.run(service.store_owner_voice_sample(UID, CONV, ['a'])) == 'stored'
    assert captured['wav_seconds'] == pytest.approx(8.0, abs=0.01)


def test_success_path_pools_owner_confirmation_into_voiceprint(monkeypatch):
    segments = [
        _segment('a', 0.0, 4.0, is_user=True, text='hello there'),
        _segment('b', 4.5, 8.5, is_user=True, text='friend now'),
    ]
    store = StrictFirestore({('users', UID): {'speaker_embedding': [1.0, 0.0]}})
    conversation = {'id': CONV, 'language': 'en', 'transcript_segments': segments}
    store.rows[('users', UID, 'conversations', CONV)] = conversation
    conversation['manual_speaker_assignments'] = {
        'generation': 1,
        'segments': {s['id']: {'generation': 1, 'is_user': True} for s in conversation['transcript_segments']},
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(
        service, 'conversation_clip_pcm', lambda *a, **kwargs: b'\x01\x00' * service.CLIP_SAMPLE_RATE * 8
    )
    monkeypatch.setattr(service.voice_profiles_db, 'get_firestore_client', lambda *a, **k: store)

    async def verify(wav, rate, text, language=None):
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[0.0, 1.0]], dtype=np.float32))

    outcome = asyncio.run(service.store_owner_voice_sample(UID, CONV, ['a', 'b']))
    assert outcome == 'stored'
    row = store.rows[('users', UID)]
    assert row['owner_voice_confirmations'][-1]['conversation_id'] == CONV
    assert row['speaker_embedding_base'] == [1.0, 0.0]

    for index in range(voice_profiles.OWNER_VOICE_CONFIRMATIONS_MAX + 2):
        voice_profiles.add_owner_voice_confirmation(
            UID, [0.0, float(index)], service._pool, conversation_id=f'c{index}', firestore_client=store
        )
    assert len(row['owner_voice_confirmations']) == voice_profiles.OWNER_VOICE_CONFIRMATIONS_MAX


@pytest.mark.parametrize('change', ['reject', 'delete', 'missing'])
def test_owner_teaching_drops_receipt_changed_during_verification(monkeypatch, change):
    receipt = {'generation': 1, 'speakers': {'0': {'generation': 1, 'is_user': True}}}
    conversation = {
        'id': CONV,
        'language': 'en',
        'manual_speaker_assignments': receipt,
        'transcript_segments': [_segment('a', 0, 8, is_user=True)],
    }
    conv_path = ('users', UID, 'conversations', CONV)
    store = StrictFirestore({('users', UID): {'speaker_embedding': [1.0, 0.0]}, conv_path: conversation})
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda *a: deepcopy(conversation))
    monkeypatch.setattr(service.voice_profiles_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(
        service, 'conversation_clip_pcm', lambda *a, **kwargs: b'\x01\x00' * service.CLIP_SAMPLE_RATE * 8
    )

    async def verify(wav, rate, text, language=None):
        if change == 'reject':
            store.rows[conv_path]['manual_speaker_assignments'] = {
                'generation': 2,
                'speakers': {'0': {'generation': 2, 'is_user': False, 'rejection': {'kind': 'not_me'}}},
            }
        elif change == 'delete':
            store.rows[conv_path]['deleted'] = True
        else:
            store.rows.pop(conv_path)
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[0.0, 1.0]]))
    assert asyncio.run(service.store_owner_voice_sample(UID, CONV, ['a'])) == 'stale_assignment'
    assert store.rows[('users', UID)]['speaker_embedding'] == [1.0, 0.0]
    assert 'owner_voice_confirmations' not in store.rows[('users', UID)]


def test_speaker_endpoint_forwards_optional_range(world):
    _set_assign_result(world, [_segment('s1', 1, 2)], resolved=['s1'])
    response = world.client.patch(
        f'/v1/conversations/{CONV}/assign-speaker/0',
        params={'assign_type': 'person_id', 'value': 'p1', 'start': 1, 'end': 2},
    )
    assert response.status_code == 200
    assert world.assignments[0]['time_range'] == (1, 2)
    assert world.assignments[0]['speaker_id'] == 0
    assert world.scheduled['person'][0]['segment_ids'] == ['s1']


@pytest.mark.parametrize('params', [{'start': 0}, {'end': 2}])
def test_speaker_endpoint_requires_both_range_boundaries(world, params):
    response = world.client.patch(
        f'/v1/conversations/{CONV}/assign-speaker/0', params={'assign_type': 'person_id', 'value': 'p1', **params}
    )
    assert response.status_code == 422
    assert not world.assignments
