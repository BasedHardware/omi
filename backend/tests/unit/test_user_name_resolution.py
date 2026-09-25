"""Owner names resolve from explicit identity sources, never biography mining."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import auth
from models.transcript_segment import TranscriptSegment
from routers import developer
from utils.conversations import render, transcript_for_llm
from utils.llm import chat


@pytest.fixture
def sources(monkeypatch):
    firebase = Mock(
        return_value=SimpleNamespace(
            display_name=None,
            uid='u',
            email=None,
            email_verified=False,
            phone_number=None,
            photo_url=None,
            disabled=False,
        )
    )
    client = Mock()
    document = client.collection.return_value.document.return_value.get.return_value
    document.exists = True
    document.to_dict.return_value = {}
    cache = Mock()
    monkeypatch.setattr(auth, '_firebase_get_user', firebase)
    monkeypatch.setattr(auth, 'get_firestore_client', Mock(return_value=client))
    monkeypatch.setattr(auth, 'cache_user_name', cache)
    return SimpleNamespace(firebase=firebase, client=client, document=document, cache=cache)


def test_firebase_wins_without_firestore_read(sources):
    sources.firebase.return_value.display_name = 'Alice Example'
    sources.document.to_dict.return_value = {
        'name': 'Bob',
        'ai_user_profile': {'profile_text': '- David Zhang is here.'},
    }
    assert auth.get_user_name('u') == 'Alice'
    sources.client.collection.assert_not_called()
    sources.cache.assert_called_once_with('u', 'Alice', ttl=3600)


@pytest.mark.parametrize('firebase_state', ['missing', 'no_display_name', 'anonymous'])
def test_firestore_name_precedes_ai_profile(sources, firebase_state):
    if firebase_state == 'missing':
        sources.firebase.side_effect = ValueError('missing user')
    elif firebase_state == 'anonymous':
        sources.firebase.return_value.display_name = 'AnonymousUser'
    sources.document.to_dict.return_value = {'name': 'Bob Smith', 'ai_user_profile': {'profile_text': '- David Zhang'}}
    assert auth.get_user_name('u', use_default=False) == 'Bob'
    sources.cache.assert_called_once_with('u', 'Bob', ttl=3600)


@pytest.mark.parametrize('display_name', [None, '', 'AnonymousUser'])
@pytest.mark.parametrize(
    'profile_text,expected',
    [
        ('- David Zhang (张大正) is a US citizen …\n- Alice is a colleague.', 'David'),
        ('- Mary-Jane O\'Brien is an engineer.', 'Mary-Jane'),
        ('- David Zhang', 'David'),
        ('- 张大正', '张大正'),
        ('- 김민수 is an engineer.', '김민수'),
    ],
)
def test_ai_identity_first_line(sources, display_name, profile_text, expected):
    sources.firebase.return_value.display_name = display_name
    sources.document.to_dict.return_value = {'ai_user_profile': {'profile_text': profile_text}}
    assert auth.get_user_name('u', use_default=False) == expected
    sources.cache.assert_called_once_with('u', expected, ttl=3600)


@pytest.mark.parametrize(
    'profile_text',
    [
        None,
        123,
        '',
        'David Zhang is an engineer.',
        '- enjoys hiking',
        '- Enjoys hiking',
        'Biography\n- David Zhang is an engineer.',
        '\n- David Zhang is an engineer.',
        '- Met David Zhang yesterday.',
        '- David Zhang Extra Fourth is an engineer.',
        '- **David Zhang** is an engineer.',
        '- david Zhang is an engineer.',
    ],
)
@pytest.mark.parametrize('use_default,expected', [(True, 'The User'), (False, None)])
def test_non_identity_profiles_preserve_default(sources, profile_text, use_default, expected):
    sources.document.to_dict.return_value = {'ai_user_profile': {'profile_text': profile_text}}
    assert auth.get_user_name('u', use_default=use_default) == expected
    sources.cache.assert_not_called()


@pytest.mark.parametrize('use_default,expected', [(True, 'The User'), (False, None)])
@pytest.mark.parametrize('state', ['absent', 'anonymous', 'malformed', 'unavailable'])
def test_missing_identity_sources(sources, use_default, expected, state):
    sources.firebase.return_value.display_name = 'AnonymousUser' if state == 'anonymous' else None
    if state == 'absent':
        sources.document.exists = False
    elif state == 'malformed':
        sources.document.to_dict.return_value = {'ai_user_profile': 'bad data'}
    elif state == 'unavailable':
        sources.client.collection.side_effect = RuntimeError('unavailable')
    assert auth.get_user_name('u', use_default=use_default) == expected


def test_resolved_identity_reaches_api_and_both_transcripts(sources):
    sources.document.to_dict.return_value = {
        'ai_user_profile': {'profile_text': '- David Zhang (张大正) is an engineer.'}
    }
    segments = [TranscriptSegment(id='s1', text='Hello.', speaker_id=0, is_user=True, start=0, end=2)]
    payload = {'transcript_segments': [segment.model_dump() for segment in segments]}
    render.populate_speaker_names('u', [payload])
    assert payload['transcript_segments'][0]['speaker_name'] == 'David'
    conversation = SimpleNamespace(
        transcript_segments=segments,
        get_transcript=lambda timestamps, people, user_name: TranscriptSegment.segments_as_string(
            segments, include_timestamps=timestamps, people=people, user_name=user_name
        ),
    )
    assert 'David' in transcript_for_llm.conversation_transcript_for_llm('u', conversation)
    _, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map('u', conversation)
    assert speaker_map == {0: 'David'}


def test_absent_firebase_user_still_uses_ai_identity(sources):
    sources.firebase.side_effect = ValueError('missing user')
    sources.document.to_dict.return_value = {'ai_user_profile': {'profile_text': '- David Zhang is an engineer.'}}
    assert auth.get_user_name('u', use_default=False) == 'David'


def test_chat_system_prompt_uses_ai_identity(sources, monkeypatch):
    sources.document.to_dict.return_value = {'ai_user_profile': {'profile_text': '- David Zhang is an engineer.'}}
    monkeypatch.setattr(chat.goals_db, 'get_user_goals', lambda *a, **k: [])
    prompt = chat._get_agentic_qa_prompt('u', tz='UTC')
    assert 'David' in prompt
    assert 'The User' not in prompt


def test_developer_conversation_http_response_resolves_owner(sources, monkeypatch):
    sources.document.to_dict.return_value = {'ai_user_profile': {'profile_text': '- David Zhang is an engineer.'}}
    conversation = {
        'id': 'c1',
        'created_at': '2026-09-22T00:00:00Z',
        'started_at': None,
        'finished_at': None,
        'structured': {'title': 'Hello', 'overview': 'Synthetic', 'emoji': '', 'category': 'other', 'action_items': []},
        'transcript_segments': [
            {'id': 's1', 'text': 'Hello.', 'speaker_id': 0, 'is_user': True, 'start': 0, 'end': 2},
            {'id': 's2', 'text': 'Hi.', 'speaker_id': 1, 'is_user': False, 'start': 2, 'end': 3},
        ],
    }
    monkeypatch.setattr(developer.conversations_db, 'get_conversation', lambda *a: conversation)
    monkeypatch.setattr(developer, 'check_conversation_transcript_read_limit', lambda *a, **k: None)
    app = FastAPI()
    app.include_router(developer.router)
    app.dependency_overrides[developer.get_auth_with_conversation_detail_read] = lambda: developer.ApiKeyAuth('u', None)
    with TestClient(app) as client:
        response = client.get('/v1/dev/user/conversations/c1?include_transcript=true')
    assert response.status_code == 200, response.text
    segments = response.json()['transcript_segments']
    assert [segment['speaker_name'] for segment in segments] == ['David', 'Speaker 1']
