"""Wire-contract coverage for the speaker-label flywheel slice (contract v1).

C1: ``TranscriptSegment.speaker_label_source`` — optional literal, default None.
C2: ``Person`` voice-learning fields — flat, defaulted for legacy records.
C4: ``RejectSpeakerRequest`` + POST reject route — body validation, durable ledger.
C5: ``VoiceMatch``/``VoiceMatchesResponse`` + GET voice-matches route — cached matches.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from google.cloud.firestore_v1.field_path import FieldPath
from pydantic import ValidationError

from database import conversations as conversations_db
from database import voice_profiles as voice_profiles_db
from models.other import Person
from models.speaker_labels import RejectSpeakerRequest, VoiceMatch, VoiceMatchesResponse
from models.transcript_segment import TranscriptSegment
from routers import speaker_labels as speaker_labels_router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.other import endpoints as auth
from utils import speaker_voice_matches
from utils.observability import speaker_identification as speaker_review

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

    reject_parameters = {
        parameter['name']: parameter['schema']
        for parameter in paths['/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject']['post']['parameters']
    }
    assert reject_parameters['conversation_id']['type'] == 'string'
    assert not {'pattern', 'minLength', 'maxLength'} & reject_parameters['conversation_id'].keys()
    assert reject_parameters['speaker_id']['type'] == 'integer'
    assert not {'minimum', 'maximum'} & reject_parameters['speaker_id'].keys()

    person_parameters = {
        parameter['name']: parameter['schema']
        for parameter in paths['/v1/users/people/{person_id}/voice-matches']['get']['parameters']
    }
    assert person_parameters['person_id']['type'] == 'string'
    assert not {'pattern', 'minLength', 'maxLength'} & person_parameters['person_id'].keys()

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


@pytest.mark.parametrize(
    'bad', ['a/b', '../x', '.', '..', '__reserved__', '__reserved\nvalue__', 'x' * 1501, 'é' * 751]
)
def test_reject_route_rejects_invalid_storage_id_before_database(client, monkeypatch, bad):
    def unexpected(*args, **kwargs):
        pytest.fail('invalid document ID reached the database')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', unexpected)
    response = client.post(f'/v1/conversations/{quote(bad, safe="")}/speakers/3/reject', json={'kind': 'not_me'})
    assert response.status_code in (404, 422)


@pytest.mark.parametrize('speaker_id', [-1, 2_000_000])
def test_reject_route_missing_speaker_preserves_lookup_404(client, monkeypatch, speaker_id):
    seen = []

    def missing(uid, conversation_id, **kwargs):
        seen.append((conversation_id, kwargs['speaker_id']))
        raise LookupError('Segment not found')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', missing)
    response = client.post(f'/v1/conversations/conv1/speakers/{speaker_id}/reject', json={'kind': 'not_me'})
    assert response.status_code == 404
    assert response.json()['detail'] == 'Conversation or speaker not found'
    assert seen == [('conv1', speaker_id)]
    assert not conversations_db.get_firestore_client().rows


@pytest.mark.parametrize(
    'bad', ['a/b', '../x', '.', '..', '__reserved__', '__reserved\nvalue__', 'x' * 1501, 'é' * 751]
)
def test_reject_route_rejects_invalid_body_person_before_database(client, monkeypatch, bad):
    def unexpected(*args, **kwargs):
        pytest.fail('invalid body person ID reached the database')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', unexpected)
    response = client.post('/v1/conversations/conv1/speakers/3/reject', json={'kind': 'not_person', 'person_id': bad})
    assert response.status_code == 400
    assert response.json()['detail'] == 'invalid person_id'


LEGACY_DOCUMENT_IDS = [
    'legacy.with.dots',
    'a\\b',
    'with space',
    ' padded ',
    'x' * 200,
    'x' * 1500,
    'é' * 750,
    '__id123__',
    '__',
    '___',
]


@pytest.mark.parametrize('document_id', LEGACY_DOCUMENT_IDS)
def test_reject_route_preserves_legacy_conversation_ids(client, monkeypatch, document_id):
    seen = []

    def missing(uid, conversation_id, **kwargs):
        seen.append(conversation_id)
        raise LookupError('Conversation not found')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', missing)
    response = client.post(
        f'/v1/conversations/{quote(document_id, safe="")}/speakers/3/reject', json={'kind': 'not_me'}
    )
    assert response.status_code == 404
    assert seen == [document_id]


@pytest.mark.parametrize('document_id', LEGACY_DOCUMENT_IDS)
def test_reject_body_preserves_legacy_person_ids(client, monkeypatch, document_id):
    seen = []

    def missing(uid, conversation_id, **kwargs):
        seen.append(kwargs['rejection']['person_id'])
        raise LookupError('Conversation not found')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', missing)
    response = client.post(
        '/v1/conversations/conv1/speakers/3/reject', json={'kind': 'not_person', 'person_id': document_id}
    )
    assert response.status_code == 404
    assert seen == [document_id]


def test_reject_route_conflict_returns_sanitized_409(client, monkeypatch):
    def raise_conflict(*args, **kwargs):
        raise ValueError('internal invariant detail that must not leak')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', raise_conflict)
    response = client.post('/v1/conversations/conv1/speakers/3/reject', json={'kind': 'not_me'})
    assert response.status_code == 409
    assert 'internal invariant detail' not in json.dumps(response.json())


def test_reject_route_unexpected_error_returns_sanitized_500(client, monkeypatch):
    def raise_boom(*args, **kwargs):
        raise RuntimeError('firestore internal: projects/x/databases/y')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', raise_boom)
    response = client.post('/v1/conversations/conv1/speakers/3/reject', json={'kind': 'not_me'})
    assert response.status_code == 500
    assert 'projects/x' not in json.dumps(response.json())


def test_reject_route_lookup_miss_returns_sanitized_404(client, monkeypatch):
    def raise_lookup(*args, **kwargs):
        raise LookupError('stored doc shape detail')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', raise_lookup)
    response = client.post('/v1/conversations/conv1/speakers/3/reject', json={'kind': 'not_me'})
    assert response.status_code == 404
    assert 'stored doc shape' not in json.dumps(response.json())


@pytest.mark.parametrize('document_id', ['私の記録\nprivate@local', 'x' * 1500, 'é' * 750, '\\' * 750, '`' * 750])
@pytest.mark.parametrize('kind', ['not_me', 'not_a_person'])
def test_successful_rejection_preserves_opaque_ids_with_safe_telemetry_and_markers(
    client, monkeypatch, caplog, document_id, kind
):
    store = conversations_db.get_firestore_client()
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    segment_id = 'segment.private@local'
    path = ('users', UID, 'conversations', document_id)
    store.rows[path] = {
        'id': document_id,
        'created_at': now,
        'started_at': now,
        'finished_at': now + timedelta(seconds=2),
        'structured': {'title': 'Synthetic', 'overview': '', 'emoji': '', 'action_items': [], 'events': []},
        'status': 'completed',
        'transcript_segments': [
            {
                'id': segment_id,
                'speaker_id': 3,
                'speaker': 'SPEAKER_03',
                'text': 'Synthetic speech',
                'start': 0.0,
                'end': 2.0,
                'is_user': True,
                'speaker_match_source': 'sync_embedding',
                'speaker_label_source': 'auto',
            }
        ],
    }
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *args: None)
    monkeypatch.setattr(voice_profiles_db, 'get_firestore_client', lambda: store)
    with caplog.at_level(logging.INFO):
        response = client.post(
            f'/v1/conversations/{quote(document_id, safe="")}/speakers/3/reject', json={'kind': kind}
        )

    assert response.status_code == 200, response.text
    assert response.json()['id'] == document_id
    assert response.json()['transcript_segments'][0].get('speaker_match_source') is None
    records = [record for record in caplog.records if record.name == speaker_review.logger.name]
    assert len(records) == 1
    message = records[0].getMessage()
    assert re.search(r'conversation_hash=[0-9a-f]{12} segment_hash=[0-9a-f]{12}', message)
    assert document_id not in message and segment_id not in message
    assert 'private@local' not in message
    for record in caplog.records:
        if record.name.startswith(('database.', 'routers.', 'utils.')):
            assert 'private@local' not in record.getMessage()
    assert path in store.rows
    if kind == 'not_a_person':
        state = store.rows[('users', UID, 'speaker_tag_prompts', 'state')]
        assert all(len(key.encode('utf-8')) <= 1500 for key in state['ignored_voices'])
        assert all(
            len(FieldPath('ignored_voices', key, 'assignment_generation').to_api_repr().encode('utf-8')) <= 1500
            for key in state['ignored_voices']
        )
        entry = next(iter(state['ignored_voices'].values()))
        assert entry['conversation_id'] == document_id and entry['speaker_id'] == 3


@pytest.mark.parametrize(
    'bad', ['a/b', '../x', '.', '..', '__reserved__', '__reserved\nvalue__', 'x' * 1501, 'é' * 751]
)
def test_voice_matches_rejects_invalid_storage_id_before_lookup(client, monkeypatch, bad):
    async def unexpected(*args, **kwargs):
        pytest.fail('invalid document ID reached voice matching')

    monkeypatch.setattr(speaker_labels_router, 'find_person_voice_matches', unexpected)
    assert client.get(f'/v1/users/people/{quote(bad, safe="")}/voice-matches').status_code in (404, 422)


@pytest.mark.parametrize('document_id', LEGACY_DOCUMENT_IDS)
def test_voice_matches_preserves_legacy_person_ids(client, monkeypatch, document_id):
    seen = []

    async def empty(uid, person_id):
        seen.append(person_id)
        return VoiceMatchesResponse()

    monkeypatch.setattr(speaker_labels_router, 'find_person_voice_matches', empty)
    response = client.get(f'/v1/users/people/{quote(document_id, safe="")}/voice-matches')
    assert response.status_code == 200
    assert response.json() == {'matches': []}
    assert seen == [document_id]


def test_voice_matches_unexpected_error_returns_sanitized_500(client, monkeypatch):
    async def raise_boom(uid, pid):
        raise RuntimeError('pinecone namespace users/u1 detail')

    monkeypatch.setattr(speaker_labels_router, 'find_person_voice_matches', raise_boom)
    response = client.get('/v1/users/people/p1/voice-matches')
    assert response.status_code == 500
    assert 'pinecone' not in json.dumps(response.json())


@pytest.mark.parametrize('failure,status', [(LookupError, 404), (ValueError, 409), (RuntimeError, 500)])
@pytest.mark.parametrize('document_id', ['私の記録\nperson.name@example.com', 'private@local'])
def test_reject_logs_mask_opaque_ids_and_echoed_exception_payload(
    client, monkeypatch, caplog, failure, status, document_id
):
    seen = []

    def fail(uid, conversation_id, **kwargs):
        seen.append(conversation_id)
        raise failure(f'Cannot resolve {conversation_id}')

    monkeypatch.setattr(conversations_db, 'assign_conversation_speaker', fail)
    response = client.post(
        f'/v1/conversations/{quote(document_id, safe="")}/speakers/3/reject', json={'kind': 'not_me'}
    )

    assert response.status_code == status
    assert seen == [document_id]
    records = [record for record in caplog.records if record.name == speaker_labels_router.logger.name]
    assert len(records) == 1
    message = records[0].getMessage()
    assert re.search(r'conv_hash=[0-9a-f]{12} speaker=3', message)
    assert 'person.name' not in message
    assert 'private@local' not in message
    assert document_id not in message
    assert records[0].exc_info is None
    assert failure.__name__ in message
    assert 'in fail' in message


@pytest.mark.parametrize('document_id', ['私の記録\nperson.name@example.com', 'private@local'])
def test_voice_matches_logs_mask_opaque_ids_and_echoed_exception_payload(client, monkeypatch, caplog, document_id):
    seen = []

    async def fail(uid, person_id):
        seen.append(person_id)
        raise RuntimeError(f'Cannot resolve {person_id}')

    monkeypatch.setattr(speaker_labels_router, 'find_person_voice_matches', fail)
    response = client.get(f'/v1/users/people/{quote(document_id, safe="")}/voice-matches')

    assert response.status_code == 500
    assert seen == [document_id]
    records = [record for record in caplog.records if record.name == speaker_labels_router.logger.name]
    assert len(records) == 1
    message = records[0].getMessage()
    assert re.search(r'person_hash=[0-9a-f]{12} uid=', message)
    assert 'person.name' not in message
    assert 'private@local' not in message
    assert document_id not in message
    assert 'RuntimeError' in message
    assert 'in fail' in message
    assert records[0].exc_info is None


@pytest.mark.parametrize(
    'bad', ['', '.', '..', 'a/b', '__reserved__', '__reserved\nvalue__', 'x' * 1501, 'é' * 751, '\ud800']
)
def test_document_id_guard_rejects_invalid_utf8_and_storage_shapes(bad):
    assert not speaker_labels_router._valid_document_id(bad)


def test_route_openapi_retains_released_unconstrained_path_types():
    app = FastAPI()
    # Exercise the actual endpoint signatures without rendering the unrelated,
    # expansive Conversation response schema for this path-parameter contract.
    for route in speaker_labels_router.router.routes:
        if isinstance(route, APIRoute):
            app.add_api_route(route.path, route.endpoint, methods=sorted(route.methods), response_model=None)
    paths = app.openapi()['paths']
    cases = [
        (
            '/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject',
            'post',
            {'conversation_id': 'string', 'speaker_id': 'integer'},
        ),
        ('/v1/users/people/{person_id}/voice-matches', 'get', {'person_id': 'string'}),
    ]
    for path, method, types in cases:
        schemas = {p['name']: p['schema'] for p in paths[path][method]['parameters'] if p['in'] == 'path'}
        for name, expected_type in types.items():
            assert schemas[name]['type'] == expected_type
            assert not {'pattern', 'minimum', 'maximum', 'minLength', 'maxLength'} & schemas[name].keys()


def test_generated_ids_fit_the_released_doc_id_contract():
    """Current generated document IDs remain accepted by the broad released contract."""
    import uuid

    for _ in range(1000):
        assert speaker_labels_router._valid_document_id(str(uuid.uuid4()))
