"""Synthetic teach/restart/sync contracts; no speech provider or customer data.

The embedding service and audio storage are fake. Sample selection, transcript
quality verification, Firestore transactions and matching are production code.
"""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from database import users
from routers.listen import speakers
from utils.audio import AudioRingBuffer
from models.transcript_segment import TranscriptSegment
from utils.sync import pipeline
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models.conversation import Conversation
from routers import conversations
from datetime import datetime, timezone
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import speaker_identification as teaching
from utils import speaker_sample


@pytest.fixture
def world(monkeypatch):
    store = StrictFirestore()
    person_path = ('users', 'account-a', 'people', 'person-1')
    conversation_path = ('users', 'account-a', 'conversations', 'teach-1')
    person = {'id': 'person-1', 'name': 'Synthetic Alex', 'speech_samples_version': 3}
    text_a = 'Hoje vamos conversar sobre nossa viagem'
    text_b = 'amanha vamos visitar nossos bons amigos'
    conversation = {
        'started_at': 1700000000.0,
        'language': 'pt',
        'transcript_segments': [
            {'id': 's1', 'start': 0.0, 'end': 5.0, 'speaker_id': 0, 'person_id': 'person-1', 'text': text_a},
            {'id': 's2', 'start': 5.0, 'end': 10.0, 'speaker_id': 0, 'person_id': 'person-1', 'text': text_b},
        ],
        'audio_files': [{'chunk_timestamps': [1700000000.0]}],
    }
    store.rows[person_path] = person
    store.rows[conversation_path] = conversation
    monkeypatch.setattr(users, 'db', store)
    monkeypatch.setattr(users, 'get_person', lambda uid, pid: deepcopy(store.rows.get(('users', uid, 'people', pid))))
    monkeypatch.setattr(
        users,
        'get_people',
        lambda uid: [deepcopy(v) for k, v in store.rows.items() if k[:3] == ('users', uid, 'people')],
    )
    monkeypatch.setattr(users, 'get_user_speaker_embedding', lambda uid: None)
    voice_settings = {'speaker_tag_prompts_enabled': True, 'save_other_voice_profiles': True}
    monkeypatch.setattr(teaching.voice_profiles_db, 'get_voice_profile_settings', lambda uid: dict(voice_settings))
    monkeypatch.setattr(
        teaching.conversations_db,
        'get_conversation',
        lambda uid, cid: deepcopy(store.rows.get(('users', uid, 'conversations', cid))),
    )
    pcm = np.full(16000 * 10, 1000, dtype=np.int16).tobytes()
    monkeypatch.setattr(teaching, 'download_audio_chunks_and_merge', lambda *a, **k: pcm)
    vector = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    monkeypatch.setattr(teaching, 'extract_embedding_from_bytes', lambda *a: vector)
    uploads = []

    def upload(*args):
        path = f'{args[1]}/people_profiles/{args[2]}/{len(uploads)}.wav'
        uploads.append(path)
        return path

    monkeypatch.setattr(teaching, 'upload_person_speech_sample_from_bytes', upload)
    deleted = []
    monkeypatch.setattr(teaching, 'delete_sample_from_storage', lambda path: deleted.append(path) or True)
    monkeypatch.setattr(
        speaker_sample,
        'deepgram_prerecorded_from_bytes',
        lambda *a, **k: [{'text': text_a + ' ' + text_b, 'speaker': 'SPEAKER_00'}],
    )
    return SimpleNamespace(
        store=store,
        person_path=person_path,
        conversation_path=conversation_path,
        uploads=uploads,
        deleted=deleted,
        vector=vector,
        voice_settings=voice_settings,
    )


def teach():
    asyncio.run(teaching.extract_speaker_samples('account-a', 'person-1', 'teach-1', ['s1', 's2']))


def test_user_opt_out_skips_saving_other_voices(world):
    world.voice_settings['save_other_voice_profiles'] = False
    teach()
    saved = world.store.rows[world.person_path]
    assert not saved.get('speech_samples'), 'opting out must stop new voice samples for other people'
    assert not saved.get('speaker_embedding')
    assert world.uploads == []


def test_opt_out_during_inflight_teaching_discards_the_upload(world, monkeypatch):
    def embed(*args):
        world.store.rows[('users', 'account-a')] = {'save_other_voice_profiles': False}
        return world.vector

    monkeypatch.setattr(teaching, 'extract_embedding_from_bytes', embed)
    teach()
    saved = world.store.rows[world.person_path]
    assert not saved.get('speaker_embedding')
    assert not saved.get('speech_samples'), 'the publish transaction must re-check the opt-out atomically'
    assert world.uploads[-1] in world.deleted
    assert not world.store.transactions[-1].has_written, 'preference and person reads precede the first write'


def test_expanded_audio_is_verified_against_all_contributing_text(world):
    teach()
    saved = world.store.rows[world.person_path]
    assert saved.get('speech_samples'), 'valid adjacent Portuguese speech must create a durable sample'
    assert saved['speaker_embedding'] == [1.0, 0.0, 0.0]


def test_deletion_invalidates_embedding_in_same_transaction(world):
    world.store.rows[world.person_path].update(
        speech_samples=['a.wav', 'b.wav'], speech_sample_transcripts=['a', 'b'], speaker_embedding=[1.0, 0.0, 0.0]
    )
    assert users.remove_person_speech_sample('account-a', 'person-1', 'a.wav')
    saved = world.store.rows[world.person_path]
    assert not saved.get('speaker_embedding'), 'a removed voice must not remain eligible while another sample exists'
    assert saved['speech_samples'] == ['b.wav']


async def fresh_live_match(monkeypatch, uid, vector):

    ring = AudioRingBuffer(10, 1000)
    ring.write(np.full(1000 * 10, 1000, dtype=np.int16).tobytes(), 10)
    suggestions = []

    async def call(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid=uid, sample_rate=1000),
        persistence=SimpleNamespace(call=call),
        has_speech_profile=False,
        state=SimpleNamespace(
            speaker_id_enabled=True, speaker_id_done=asyncio.Event(), active=False, audio_ring_buffer=ring
        ),
        limits=SimpleNamespace(speaker_id_min_audio=2),
        emit_speaker_suggestion=lambda *args: suggestions.append(args),
    )
    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', lambda *args: vector)
    matcher = speakers.SpeakerMatcher(host)
    # End the worker deterministically once loading finishes; no timer/sleep.
    matcher.queue = SimpleNamespace(get=AsyncMock(side_effect=asyncio.TimeoutError))
    await matcher.load_and_run()
    await matcher.match(7, {'id': 'later-segment', 'duration': 10, 'abs_start': 0, 'abs_end': 10})
    return matcher, suggestions


def test_teach_once_new_sessions_and_offline_sync_recognize_same_person(world, monkeypatch):

    teach()
    for _ in range(2):  # No session state carried across the simulated app restart.
        matcher, suggestions = asyncio.run(fresh_live_match(monkeypatch, 'account-a', world.vector))
        assert matcher.speaker_to_person[7] == ('person-1', 'Synthetic Alex')
        assert suggestions == [(7, 'person-1', 'Synthetic Alex', 'later-segment')]
    other, suggestions = asyncio.run(fresh_live_match(monkeypatch, 'account-b', world.vector))
    assert not other.person_embeddings and not suggestions
    cache = pipeline.build_person_embeddings_cache('account-a')
    assert not pipeline.build_person_embeddings_cache('account-b')
    monkeypatch.setattr(pipeline, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(pipeline, 'extract_embedding_from_bytes', lambda *a: world.vector)
    segment = TranscriptSegment(
        id='offline-1', text='Synthetic speech about a trip', speaker='SPEAKER_07', is_user=False, start=0, end=10
    )
    wav = teaching._pcm_to_wav_bytes(np.full(16000 * 10, 1000, dtype=np.int16).tobytes(), 16000)
    pipeline.identify_speakers_for_segments([segment], wav, cache, 'account-a')
    assert segment.person_id == 'person-1' and not segment.is_user
    unknown, suggestions = asyncio.run(fresh_live_match(monkeypatch, 'account-a', np.array([[0.0, 1.0, 0.0]])))
    assert not unknown.speaker_to_person and not suggestions


def test_reteaching_replaces_legacy_profile_and_failed_embedding_preserves_it(world, monkeypatch):
    world.store.rows[world.person_path].update(
        speech_samples=['legacy.wav'], speech_samples_version=1, speaker_embedding=[0.0, 1.0, 0.0]
    )
    teach()
    saved = deepcopy(world.store.rows[world.person_path])
    assert saved['speech_samples_version'] == 3
    assert saved['speaker_embedding'] == [1.0, 0.0, 0.0]
    assert world.deleted == ['legacy.wav']

    def fail(*args):
        raise RuntimeError('synthetic embedding outage')

    monkeypatch.setattr(teaching, 'extract_embedding_from_bytes', fail)
    teach()
    assert world.store.rows[world.person_path] == saved


def test_same_person_id_in_two_accounts_never_shares_a_profile(world, monkeypatch):
    teach()
    other_path = ('users', 'account-b', 'people', 'person-1')
    world.store.rows[other_path] = {
        'id': 'person-1',
        'name': 'Synthetic Blair',
        'speech_samples_version': 3,
        'speech_samples': ['account-b/people_profiles/person-1/sample.wav'],
        'speaker_embedding': [0.0, 1.0, 0.0],
    }
    other_before = deepcopy(world.store.rows[other_path])
    matcher, suggestions = asyncio.run(fresh_live_match(monkeypatch, 'account-b', world.vector))
    assert not suggestions
    matcher, suggestions = asyncio.run(fresh_live_match(monkeypatch, 'account-b', np.array([[0.0, 1.0, 0.0]])))
    assert matcher.speaker_to_person[7] == ('person-1', 'Synthetic Blair')
    users.remove_person_speech_sample('account-a', 'person-1', world.uploads[0])
    assert world.store.rows[other_path] == other_before
    assert not pipeline.build_person_embeddings_cache('account-a')
    assert pipeline.build_person_embeddings_cache('account-b')['person-1']['name'] == 'Synthetic Blair'


def test_correction_invalidates_only_contributing_teaching(world):
    teach()
    assert users.invalidate_person_speech_profile('account-a', 'person-1', 'different-conversation', ['s1']) == []
    assert world.store.rows[world.person_path]['speaker_embedding']
    assert users.invalidate_person_speech_profile('account-b', 'person-1', 'teach-1', ['s1']) == []
    assert users.invalidate_person_speech_profile('account-a', 'person-1', 'teach-1', ['s1']) == world.uploads
    assert not world.store.rows[world.person_path]['speaker_embedding']


@pytest.mark.parametrize('mutation', ['correction', 'delete-sample', 'delete-person'])
def test_inflight_teaching_cannot_restore_corrected_or_deleted_profile(world, monkeypatch, mutation):
    teach()

    def embedding(*args):
        if mutation == 'correction':
            users.invalidate_person_speech_profile('account-a', 'person-1', 'teach-1', ['s1'])
        elif mutation == 'delete-sample':
            users.remove_person_speech_sample('account-a', 'person-1', world.uploads[0])
        else:
            del world.store.rows[world.person_path]
        return world.vector

    monkeypatch.setattr(teaching, 'extract_embedding_from_bytes', embedding)
    teach()
    assert not world.store.rows.get(world.person_path, {}).get('speaker_embedding')
    assert world.uploads[-1] in world.deleted


def test_expansion_never_crosses_a_corrected_person_boundary(world):
    world.store.rows[world.conversation_path]['transcript_segments'][0]['person_id'] = 'other-person'
    teach()
    assert not world.uploads


def test_recovery_cannot_restore_a_sample_deleted_during_embedding(world, monkeypatch):
    teach()
    world.store.rows[world.person_path]['speaker_embedding'] = None
    snapshot = deepcopy(world.store.rows[world.person_path])
    monkeypatch.setattr(speakers, 'download_sample_audio', lambda path: b'synthetic-wav')

    def embed(*args):
        users.remove_person_speech_sample('account-a', 'person-1', world.uploads[0])
        return world.vector

    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', embed)

    async def call(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(request=SimpleNamespace(uid='account-a'), persistence=SimpleNamespace(call=call))
    result = asyncio.run(speakers.SpeakerMatcher(host)._recover_person_embedding(snapshot))
    assert result is None
    assert not world.store.rows[world.person_path]['speaker_embedding']


def test_offline_cache_rejects_legacy_and_deleted_profiles(world):

    world.store.rows[world.person_path].update(
        speech_samples=['legacy.wav'], speech_samples_version=2, speaker_embedding=[1.0, 0.0, 0.0]
    )
    assert not pipeline.build_person_embeddings_cache('account-a')

    teach()
    users.remove_person_speech_sample('account-a', 'person-1', world.uploads[-1])
    assert not pipeline.build_person_embeddings_cache('account-a')


def test_mobile_bulk_endpoint_teaches_corrects_and_rejects_foreign_person(world, monkeypatch):

    now = datetime(2026, 9, 19, tzinfo=timezone.utc)

    def deserialize(raw):
        raw = deepcopy(raw)
        raw.pop('audio_files', None)
        for segment in raw['transcript_segments']:
            segment.setdefault('is_user', False)
        return Conversation(created_at=now, finished_at=now, structured={}, **raw)

    monkeypatch.setattr(conversations.conversations_db, 'get_firestore_client', lambda: world.store)
    # The fixture intentionally keeps its synthetic manifest minimal; exercise
    # the real command/transaction while leaving storage encryption out of scope.
    monkeypatch.setattr(conversations.conversations_db, '_prepare_conversation_for_write', lambda data, *args: data)
    monkeypatch.setattr(conversations, 'deserialize_conversation', deserialize)
    monkeypatch.setattr(conversations, '_emit_speaker_identity_confirmed', lambda **kwargs: None)
    monkeypatch.setattr(conversations, 'delete_speech_profile_blob', lambda path: world.deleted.append(path))
    app = FastAPI()
    app.include_router(conversations.router)
    app.dependency_overrides[conversations.auth.get_current_user_uid] = lambda: 'account-a'
    with TestClient(app) as client:
        url = '/v1/conversations/teach-1/segments/assign-bulk'
        payload = {'segment_ids': ['s1', 's2'], 'assign_type': 'person_id', 'value': 'person-1'}
        assert client.patch(url, json=payload).status_code == 200
        assert world.store.rows[world.person_path]['speaker_embedding'] == [1.0, 0.0, 0.0]
        world.store.rows[('users', 'account-b', 'people', 'foreign-person')] = {'id': 'foreign-person'}
        assert client.patch(url, json={**payload, 'value': 'foreign-person'}).status_code == 404
        assert world.store.rows[world.person_path]['speaker_embedding']
        world.store.rows[('users', 'account-a', 'people', 'person-2')] = {'id': 'person-2', 'name': 'Synthetic Sam'}
        assert client.patch(url, json={**payload, 'value': 'person-2'}).status_code == 200
        assert not world.store.rows[world.person_path]['speaker_embedding']
        corrected = world.store.rows[('users', 'account-a', 'people', 'person-2')]
        assert corrected['speaker_embedding'] == [1.0, 0.0, 0.0]
        assert world.store.rows[world.conversation_path]['transcript_segments'][0]['person_id'] == 'person-2'
        matcher, suggestions = asyncio.run(fresh_live_match(monkeypatch, 'account-a', world.vector))
        assert matcher.speaker_to_person[7] == ('person-2', 'Synthetic Sam')
        assert set(pipeline.build_person_embeddings_cache('account-a')) == {'person-2'}


def test_next_conversation_refreshes_profiles_but_same_conversation_keeps_locked_matches(world, monkeypatch):
    async def exercise():
        matcher, _ = await fresh_live_match(monkeypatch, 'account-a', world.vector)
        await matcher.refresh_for_conversation('first')
        assert not matcher.person_embeddings
        await teaching.extract_speaker_samples('account-a', 'person-1', 'teach-1', ['s1', 's2'])
        matcher.speaker_to_person[7] = ('locked', 'Locked')
        await matcher.refresh_for_conversation('first')
        assert matcher.speaker_to_person[7][0] == 'locked'
        assert not matcher.person_embeddings
        await matcher.refresh_for_conversation('second')
        assert 'person-1' in matcher.person_embeddings
        assert not matcher.speaker_to_person
        await matcher.match(7, {'id': 'old', 'conversation_id': 'first', 'duration': 10, 'abs_start': 0, 'abs_end': 10})
        assert not matcher.speaker_to_person
        await matcher.match(
            7, {'id': 'new', 'conversation_id': 'second', 'duration': 10, 'abs_start': 0, 'abs_end': 10}
        )
        assert matcher.speaker_to_person[7][0] == 'person-1'

    asyncio.run(exercise())
