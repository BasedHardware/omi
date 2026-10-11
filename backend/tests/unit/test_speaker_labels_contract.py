"""Wire-contract coverage for the speaker-label flywheel slice (contract v1).

C1: ``TranscriptSegment.speaker_label_source`` — optional literal, default None.
C2: ``Person`` voice-learning fields — flat, defaulted for legacy records.
C4: ``RejectSpeakerRequest`` + POST reject route — body validation, durable ledger.
C5: ``VoiceMatch``/``VoiceMatchesResponse`` + GET voice-matches route — cached matches.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from database import conversations as conversations_db
from models.other import Person
from models.speaker_labels import RejectSpeakerRequest, VoiceMatch, VoiceMatchesResponse
from models.transcript_segment import TranscriptSegment
from routers import speaker_labels as speaker_labels_router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.other import endpoints as auth
from utils import speaker_voice_matches

ROOT_DIR = Path(__file__).resolve().parents[3]

UID = "uid-speaker-label-contract"


def _segment(**overrides) -> TranscriptSegment:
    data = {'text': 'hello', 'is_user': False, 'start': 0.0, 'end': 1.0}
    data.update(overrides)
    return TranscriptSegment(**data)


def test_segment_speaker_label_source_defaults_none():
    segment = _segment()
    assert segment.speaker_label_source is None


@pytest.mark.parametrize('source', ['manual', 'auto', 'carried'])
def test_segment_speaker_label_source_accepts_literals(source):
    assert _segment(speaker_label_source=source, person_id='p1').speaker_label_source == source


def test_segment_speaker_label_source_rejects_invalid():
    with pytest.raises(ValidationError):
        _segment(speaker_label_source='magic')


def test_segment_dump_includes_speaker_label_source():
    dumped = _segment(speaker_label_source='manual', person_id='p1').model_dump()
    assert dumped['speaker_label_source'] == 'manual'
    assert 'speaker_label_source' in _segment().model_dump()


def test_person_voice_learning_defaults_for_legacy_record():
    person = Person(id='p1', name='Ada')
    assert person.voice_learning_state == 'unknown'
    assert person.voice_speech_seconds is None
    assert person.voice_needed_seconds is None


def test_person_voice_learning_rejects_invalid_state():
    with pytest.raises(ValidationError):
        Person(id='p1', name='Ada', voice_learning_state='half_learned')


@pytest.mark.parametrize('state', ['learned', 'pending', 'needs_more_speech', 'disabled', 'unknown'])
def test_person_voice_learning_accepts_literals(state):
    fields = {'id': 'p1', 'name': 'Ada', 'voice_learning_state': state}
    if state == 'learned':
        fields.update(speech_samples=['a.wav'], speech_samples_version=3, speaker_embedding=[1.0, 0.0])
    assert Person(**fields).voice_learning_state == state


def test_person_voice_learning_derives_learned_only_with_ready_print():
    assert Person(id='p1', name='Ada', voice_learning_state='learned').voice_learning_state == 'unknown'


@pytest.mark.parametrize('kind', ['not_me', 'not_person', 'not_a_person'])
def test_reject_speaker_request_accepts_all_kinds(kind):
    body = RejectSpeakerRequest(kind=kind, person_id='p1', segment_ids=['s1', 's2'])
    assert body.kind == kind
    assert body.segment_ids == ['s1', 's2']


def test_reject_speaker_request_allows_omitted_segment_ids():
    body = RejectSpeakerRequest(kind='not_me')
    assert body.segment_ids is None


def test_reject_speaker_request_rejects_empty_segment_ids():
    with pytest.raises(ValidationError):
        RejectSpeakerRequest(kind='not_me', segment_ids=[])


def test_reject_speaker_request_normalizes_person_id_for_non_person_kinds():
    assert RejectSpeakerRequest(kind='not_me', person_id='p1').person_id is None
    assert RejectSpeakerRequest(kind='not_a_person', person_id='p1').person_id is None
    assert RejectSpeakerRequest(kind='not_person', person_id='p1').person_id == 'p1'


def test_reject_speaker_request_not_person_requires_person_id():
    with pytest.raises(ValidationError):
        RejectSpeakerRequest(kind='not_person')


def test_reject_speaker_request_not_person_rejects_blank_person_id():
    with pytest.raises(ValidationError):
        RejectSpeakerRequest(kind='not_person', person_id='  ')


def test_reject_speaker_request_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        RejectSpeakerRequest(kind='maybe')


def test_voice_matches_response_defaults_empty():
    assert VoiceMatchesResponse().matches == []


def test_voice_match_shape():
    match = VoiceMatch(
        conversation_id='c1',
        title='Lunch',
        started_at='2024-01-01T12:00:00Z',
        speaker_id=2,
        talk_seconds=12.5,
        segment_ids=['s1'],
        clip_start=1.0,
        clip_end=13.5,
        match_level='strong',
    )
    dumped = match.model_dump(mode='json')
    assert dumped['started_at'] == '2024-01-01T12:00:00Z'
    assert dumped['speaker_id'] == 2
    assert dumped['talk_seconds'] == 12.5
    assert dumped['segment_ids'] == ['s1']
    assert dumped['match_level'] == 'strong'
    with pytest.raises(ValidationError):
        VoiceMatch(**{**dumped, 'match_level': 'maybe'})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, '_enforce_rate_limit', lambda *args, **kwargs: None)
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    app = FastAPI()
    app.include_router(speaker_labels_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def test_reject_route_missing_conversation_mutates_nothing(client, monkeypatch):
    response = client.post(
        '/v1/conversations/conv1/speakers/3/reject',
        json={'kind': 'not_me'},
    )
    assert response.status_code == 404
    store = conversations_db.get_firestore_client()
    assert ('users', UID, 'conversations', 'conv1') not in store.rows


def test_reject_route_rejects_malformed_body(client):
    response = client.post(
        '/v1/conversations/conv1/speakers/3/reject',
        json={'kind': 'not_person'},
    )
    assert response.status_code == 422


def test_voice_matches_route_returns_empty_list_without_voiceprint(client, monkeypatch):
    monkeypatch.setattr(speaker_voice_matches, 'named_speaker_prompts_allowed', lambda uid: True)
    monkeypatch.setattr(speaker_voice_matches.users_db, 'get_person', lambda uid, pid: {'id': pid})
    response = client.get('/v1/users/people/p1/voice-matches')
    assert response.status_code == 200
    assert response.json() == {'matches': []}


def test_routes_depend_on_authenticated_uid():
    for route in speaker_labels_router.router.routes:
        dependant = getattr(route, 'dependant', None)
        assert dependant is not None
        dependency_calls = [dep.call for dep in dependant.dependencies]
        assert auth.get_current_user_uid in dependency_calls


def test_app_client_openapi_covers_contract():
    spec = json.loads((ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json').read_text(encoding='utf-8'))
    paths = spec['paths']
    assert '/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject' in paths
    assert 'post' in paths['/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject']
    assert '/v1/users/people/{person_id}/voice-matches' in paths
    assert 'get' in paths['/v1/users/people/{person_id}/voice-matches']

    components = spec['components']['schemas']
    segment_props = components['TranscriptSegment']['properties']
    assert 'speaker_label_source' in segment_props
    source_schema = segment_props['speaker_label_source']
    assert set(source_schema.get('anyOf', [{}])[0].get('enum', source_schema.get('enum', []))) <= {
        'manual',
        'auto',
        'carried',
    }

    person_props = components['Person']['properties']
    for field in ('voice_learning_state', 'voice_speech_seconds', 'voice_needed_seconds'):
        assert field in person_props

    for name in ('RejectSpeakerRequest', 'VoiceMatch', 'VoiceMatchesResponse'):
        assert name in components


def test_public_openapi_excludes_first_party_reject_route():
    spec = json.loads((ROOT_DIR / 'docs' / 'api-reference' / 'openapi.json').read_text(encoding='utf-8'))
    assert '/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject' not in spec['paths']
    assert '/v1/users/people/{person_id}/voice-matches' not in spec['paths']


def test_generated_dart_wire_models_cover_contract():
    gen_dir = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen'
    conversation_dart = (gen_dir / 'conversation_wire.g.dart').read_text(encoding='utf-8')
    assert 'speakerLabelSource' in conversation_dart
    assert 'class GeneratedRejectSpeakerRequest' in conversation_dart

    people_dart = (gen_dir / 'people_wire.g.dart').read_text(encoding='utf-8')
    assert 'voiceLearningState' in people_dart
    assert 'class GeneratedVoiceMatch' in people_dart
    assert 'class GeneratedVoiceMatchesResponse' in people_dart
