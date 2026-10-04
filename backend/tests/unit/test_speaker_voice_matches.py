"""C5 cached evidence, receipt exclusions, and request work bounds."""

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.transcript_segment import legacy_conversation_segment_id
from routers import speaker_labels
from utils import speaker_voice_matches as matches
from utils.conversations import speaker_resolution as resolution
from utils.other import endpoints as auth

UID = 'test-account'
PERSON_ID = 'test-person'


def _segment(segment_id='s1', speaker_id=2, start=2.0, end=14.0, **overrides):
    return dict(id=segment_id, speaker_id=speaker_id, start=start, end=end, is_user=False, person_id=None, **overrides)


def _conversation(conversation_id='c1', age=1, **overrides):
    return {
        'id': conversation_id,
        'started_at': datetime.now(timezone.utc) - timedelta(days=age),
        'status': 'completed',
        'structured': {'title': 'Earlier conversation'},
        'transcript_segments': [_segment(), _segment('s2', start=20.0, end=23.0)],
        **overrides,
    }


def _cache(entries=None):
    return resolution.encode_cache(entries or {'s1': (12.0, np.array([1.0, 0.0]))})


@pytest.fixture
def env(monkeypatch):
    state = SimpleNamespace(
        person={
            'id': PERSON_ID,
            'speaker_embedding': [1.0, 0.0],
            'speech_samples': ['sample'],
            'speech_samples_version': 3,
        },
        allowed=True,
        conversations=[_conversation()],
        cache={'c1': _cache()},
        ignored={},
        reads=[],
        queries=[],
        threads=[],
    )

    def get_person(uid, person_id):
        assert (uid, person_id) == (UID, PERSON_ID)
        state.threads.append(threading.get_ident())
        return state.person

    def get_conversations(uid, **kwargs):
        assert uid == UID
        state.threads.append(threading.get_ident())
        state.queries.append(kwargs)
        return state.conversations

    def download(uid, conversation_id):
        assert uid == UID
        state.threads.append(threading.get_ident())
        state.reads.append(conversation_id)
        return state.cache.get(conversation_id)

    def forbidden(*args, **kwargs):
        pytest.fail('Historical matching must not compute embeddings, download audio, or write caches')

    monkeypatch.setattr(matches.users_db, 'get_person', get_person)
    monkeypatch.setattr(matches.users_db, 'get_people', lambda uid: [state.person] if state.person else [])
    monkeypatch.setattr(matches.users_db, 'get_user_speaker_embedding', lambda uid: None)
    monkeypatch.setattr(matches.conversations_db, 'get_conversations', get_conversations)
    monkeypatch.setattr(matches, 'named_speaker_prompts_allowed', lambda uid: state.allowed)
    monkeypatch.setattr(
        matches.voice_profiles_db, 'get_tag_prompt_state', lambda uid: {'ignored_voices': state.ignored}
    )
    monkeypatch.setattr(matches, 'download_speaker_embedding_cache', download)
    monkeypatch.setattr(resolution, 'extract_embedding_from_bytes', forbidden)
    monkeypatch.setattr(resolution, 'iter_audio_chunk_pcm', forbidden)
    monkeypatch.setattr(resolution, 'upload_speaker_embedding_cache', forbidden)
    return state


def _find():
    return asyncio.run(matches.find_person_voice_matches(UID, PERSON_ID)).matches


def test_matching_unnamed_voice_has_contract_fields_and_uses_workers(env):
    found = _find()
    assert len(found) == 1
    assert found[0].model_dump() == {
        'conversation_id': 'c1',
        'title': 'Earlier conversation',
        'started_at': env.conversations[0]['started_at'],
        'speaker_id': 2,
        'talk_seconds': 15.0,
        'segment_ids': ['s1', 's2'],
        'clip_start': 2.0,
        'clip_end': 12.0,
        'match_level': 'strong',
    }
    assert env.reads == ['c1']
    assert all(thread != threading.get_ident() for thread in env.threads)
    query = env.queries[0]
    assert query['limit'] == 25
    assert query['end_date'] - query['start_date'] == timedelta(days=30)


@pytest.mark.parametrize('distance,level', [(0.1, 'strong'), (0.45, 'likely'), (0.55, None), (1.0, None)])
def test_pooled_threshold_and_match_levels(env, distance, level):
    cosine = 1.0 - distance
    env.cache['c1'] = _cache({'s1': (12.0, np.array([cosine, np.sqrt(1.0 - cosine**2)]))})
    found = _find()
    assert [match.match_level for match in found] == ([level] if level else [])


def test_duration_weighted_normalized_pool(env):
    # Long matching evidence must dominate the short orthogonal segment,
    # regardless of raw vector magnitude.
    env.cache['c1'] = _cache({'s1': (12.0, np.array([1.0, 0.0])), 's2': (3.0, np.array([0.0, 100.0]))})
    assert _find()[0].match_level == 'strong'


@pytest.mark.parametrize('duration', [0.5, 4.0])
def test_insufficient_cached_speech_is_not_a_match(env, duration):
    env.cache['c1'] = _cache({'s1': (duration, np.array([1.0, 0.0]))})
    assert _find() == []


@pytest.mark.parametrize('vector', [[0.0, 0.0], [float('nan'), 0.0], [1.0, 0.0, 0.0]])
def test_invalid_cached_vectors_are_skipped(env, vector):
    env.cache['c1'] = _cache({'s1': (12.0, np.array(vector))})
    assert _find() == []


@pytest.mark.parametrize('cache', [None, b'bad-cache'])
def test_missing_or_malformed_cache_is_skipped(env, cache):
    env.cache['c1'] = cache
    assert _find() == []


@pytest.mark.parametrize(
    'receipt',
    [
        {'speakers': {'2': {'person_id': PERSON_ID, 'generation': 1}}},
        {'segments': {'s1': {'is_user': True, 'generation': 1}}},
        {'speakers': {'2': {'rejection': {'kind': 'not_person', 'person_id': PERSON_ID}, 'generation': 1}}},
        {
            'segments': {
                'old-id': {
                    'speaker_id': 2,
                    'rejection': {'kind': 'not_person', 'person_id': PERSON_ID},
                    'generation': 1,
                }
            }
        },
        {'speakers': {'2': {'rejection': {'kind': 'not_a_person'}, 'generation': 1}}},
    ],
)
def test_manual_decisions_exclude_whole_voice(env, receipt):
    env.conversations[0]['manual_speaker_assignments'] = receipt
    assert _find() == []
    assert env.reads == []


def test_ignored_store_excludes_voice_even_without_receipt(env):
    env.ignored = {'c1:2': {'conversation_id': 'c1', 'speaker_id': 2}}
    assert _find() == []
    assert env.reads == []


@pytest.mark.parametrize('identity', [{'is_user': True}, {'person_id': PERSON_ID}])
def test_one_named_segment_excludes_whole_voice(env, identity):
    env.conversations[0]['transcript_segments'][1].update(identity)
    assert _find() == []


@pytest.mark.parametrize(
    'change',
    [
        {'speaker_embedding': None},
        {'speech_samples_version': 2},
        {'speech_samples': []},
        {'speaker_embedding': [0.0, 0.0]},
    ],
)
def test_no_usable_voiceprint_returns_empty_without_scan(env, change):
    env.person.update(change)
    assert _find() == []
    assert env.queries == env.reads == []


def test_entitlement_denied_returns_empty_without_scan(env):
    env.allowed = False
    assert _find() == []
    assert env.queries == env.reads == []


@pytest.mark.parametrize(
    'override',
    [
        {'discarded': True},
        {'is_locked': True},
        {'deleted': True},
        {'status': 'in_progress'},
        {'status': None},
        {'started_at': None},
        {'started_at': datetime.now(timezone.utc) - timedelta(days=31)},
        {'started_at': datetime.now(timezone.utc) + timedelta(days=1)},
    ],
)
def test_ineligible_conversation_skips_cache(env, override):
    env.conversations[0].update(override)
    assert _find() == []
    assert env.reads == []


def test_match_bound_and_newest_first(env):
    env.conversations = [_conversation(f'c{i}', age=i) for i in range(1, 12)][::-1]
    env.cache = {conversation['id']: _cache() for conversation in env.conversations}
    assert [match.conversation_id for match in _find()] == ['c1', 'c2', 'c3', 'c4', 'c5']
    assert env.reads == ['c1', 'c2', 'c3', 'c4', 'c5']


def test_match_bound_also_applies_within_one_conversation(env):
    segments = [_segment(f's{i}', speaker_id=i, start=i * 15.0, end=i * 15.0 + 12.0) for i in range(8)]
    env.conversations[0]['transcript_segments'] = segments
    env.cache['c1'] = _cache({segment['id']: (12.0, np.array([1.0, 0.0])) for segment in segments})
    assert len(_find()) == 5
    assert env.reads == ['c1']


def test_conversation_bound_even_if_database_fake_returns_too_many(env):
    env.conversations = [_conversation(f'c{i}') for i in range(30)]
    env.cache = {'c29': _cache()}
    assert _find() == []
    assert len(env.reads) == 25
    assert 'c29' not in env.reads


def test_legacy_segment_ids_and_speaker_name(env):
    segment = env.conversations[0]['transcript_segments'][0]
    segment.pop('id')
    segment.pop('speaker_id')
    segment['speaker'] = 'SPEAKER_2'
    segment_id = legacy_conversation_segment_id('c1', 0)
    env.cache['c1'] = _cache({segment_id: (12.0, np.array([1.0, 0.0]))})
    assert _find()[0].segment_ids == [segment_id, 's2']


def test_sentinel_voice_is_not_offered(env):
    for segment in env.conversations[0]['transcript_segments']:
        segment['speaker_id'] = 99
    assert _find() == []
    assert env.reads == []


def test_deadline_returns_partial_matches_without_waiting_for_slow_cache(env, monkeypatch):
    env.conversations = [_conversation('c1', age=1), _conversation('c2', age=2), _conversation('c3', age=3)]
    release = threading.Event()
    entered = threading.Event()
    completed = threading.Event()

    def slow_download(uid, conversation_id):
        env.reads.append(conversation_id)
        if conversation_id == 'c2':
            entered.set()
            try:
                assert release.wait(timeout=2.0)
            finally:
                completed.set()
        return _cache()

    monkeypatch.setattr(matches, 'download_speaker_embedding_cache', slow_download)
    monkeypatch.setattr(matches, 'SCAN_SECONDS', 0.25)
    try:
        found = _find()
        assert entered.is_set()
        assert not release.is_set()
        assert [match.conversation_id for match in found] == ['c1']
        assert env.reads == ['c1', 'c2']
    finally:
        release.set()
        assert completed.wait(timeout=2.0)


def test_deadline_before_database_scan_returns_empty(env, monkeypatch):
    monkeypatch.setattr(matches, 'SCAN_SECONDS', 0.0)
    assert _find() == []
    assert env.queries == env.reads == []


@pytest.mark.parametrize('exists,status', [(True, 200), (False, 404)])
def test_route_ownership_and_response(env, monkeypatch, exists, status):
    if not exists:
        env.person = None
    monkeypatch.setattr(auth, '_enforce_rate_limit', lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(speaker_labels.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        response = client.get(f'/v1/users/people/{PERSON_ID}/voice-matches')
    assert response.status_code == status
    if exists:
        assert response.json()['matches'][0]['conversation_id'] == 'c1'
        assert response.json()['matches'][0]['match_level'] == 'strong'
    else:
        assert response.json() == {'detail': 'Person not found'}
        assert env.queries == env.reads == []


@pytest.mark.parametrize('competitor', ['owner', 'duplicate'])
def test_historical_matches_abstain_when_competing_identity_is_as_close(env, monkeypatch, competitor):
    if competitor == 'owner':
        monkeypatch.setattr(matches.users_db, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])
    else:
        monkeypatch.setattr(matches.users_db, 'get_people', lambda uid: [env.person, {**env.person, 'id': 'duplicate'}])
    assert asyncio.run(matches.find_person_voice_matches(UID, PERSON_ID)).matches == []
