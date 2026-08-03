"""`POST /v1/people/dossiers` contract.

What matters here is the *bounding*, because this endpoint runs across a whole address book:

  * one shared Firestore memory read per request, never one per person;
  * a person the caller already has a current fingerprint for costs no model call;
  * a person with too little evidence costs no model call;
  * a grounded-empty result is reported as skipped rather than as an all-null card.

Hermetic: the router's two data accessors and the synthesis call are monkeypatched, so nothing
touches Firestore or a provider.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.llm.people_dossier import GroundedDossier


@pytest.fixture(scope='module')
def app_client():
    from routers import people_dossier as module
    from utils.other import endpoints as auth

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'uid-1'
    return TestClient(app, raise_server_exceptions=False), module


def _memory(content, subject):
    return {'content': content, 'subject_entity_id': subject, 'object_entity_ids': [], 'created_at': '2026-07-01'}


def _wire(module, monkeypatch, *, people, memories, generated=None, reads=None):
    monkeypatch.setattr(module.users_db, 'get_people_by_ids', lambda uid, ids: people)
    monkeypatch.setattr(module, 'get_user_name', lambda uid: 'Alex')

    def get_memories(uid, limit=100, **kwargs):
        if reads is not None:
            reads.append(limit)
        return memories

    monkeypatch.setattr(module.memories_db, 'get_memories', get_memories)

    def generate(uid, user_name, person_name, evidence):
        if generated is not None:
            generated.append(person_name)
        return GroundedDossier(
            who=f'{person_name} is a climbing partner.',
            now=None,
            overall=None,
            facts=[],
            activities=[],
            open_threads=[],
            claims=[{'field': 'who', 'text': f'{person_name} is a climbing partner.', 'evidence': ['m0']}],
        )

    monkeypatch.setattr(module, 'generate_person_dossier', generate)


def test_returns_grounded_narrative_with_provenance(app_client, monkeypatch):
    client, module = app_client
    _wire(
        module,
        monkeypatch,
        people=[{'id': 'pid-1', 'name': 'Priya'}],
        memories=[_memory(f'fact {i}', 'person:pid-1') for i in range(5)],
    )

    response = client.post('/v1/people/dossiers', json={'people': [{'person_id': 'pid-1'}]})

    assert response.status_code == 200
    body = response.json()
    assert len(body['dossiers']) == 1
    dossier = body['dossiers'][0]
    assert dossier['person_id'] == 'pid-1'
    assert dossier['who'] == 'Priya is a climbing partner.'
    assert dossier['claims'] == [{'field': 'who', 'text': 'Priya is a climbing partner.', 'evidence': ['m0']}]
    assert dossier['evidence_count'] == 5
    assert dossier['evidence_fingerprint']
    assert body['skipped'] == []


def test_one_memory_read_serves_the_whole_batch(app_client, monkeypatch):
    client, module = app_client
    reads: list[int] = []
    generated: list[str] = []
    _wire(
        module,
        monkeypatch,
        people=[{'id': f'pid-{i}', 'name': f'P{i}'} for i in range(4)],
        memories=[_memory(f'fact {i}', f'person:pid-{i % 4}') for i in range(20)],
        generated=generated,
        reads=reads,
    )

    response = client.post('/v1/people/dossiers', json={'people': [{'person_id': f'pid-{i}'} for i in range(4)]})

    assert response.status_code == 200
    assert reads == [module.MEMORY_SCAN_LIMIT], 'the memory scan must be shared, not per person'
    assert sorted(generated) == ['P0', 'P1', 'P2', 'P3']


def test_matching_fingerprint_costs_no_model_call(app_client, monkeypatch):
    client, module = app_client
    generated: list[str] = []
    memories = [_memory(f'fact {i}', 'person:pid-1') for i in range(5)]
    _wire(module, monkeypatch, people=[{'id': 'pid-1', 'name': 'Priya'}], memories=memories, generated=generated)

    first = client.post('/v1/people/dossiers', json={'people': [{'person_id': 'pid-1'}]})
    fingerprint = first.json()['dossiers'][0]['evidence_fingerprint']
    generated.clear()

    second = client.post(
        '/v1/people/dossiers',
        json={'people': [{'person_id': 'pid-1', 'known_fingerprint': fingerprint}]},
    )

    assert second.json()['dossiers'] == []
    assert second.json()['skipped'] == [{'person_id': 'pid-1', 'reason': 'unchanged'}]
    assert generated == [], 'an unchanged person must not reach the model'


def test_thin_evidence_is_skipped_before_the_model(app_client, monkeypatch):
    client, module = app_client
    generated: list[str] = []
    _wire(
        module,
        monkeypatch,
        people=[{'id': 'pid-1', 'name': 'Priya'}],
        memories=[_memory('the only thing we know', 'person:pid-1')],
        generated=generated,
    )

    response = client.post('/v1/people/dossiers', json={'people': [{'person_id': 'pid-1'}]})

    assert response.json()['dossiers'] == []
    assert response.json()['skipped'] == [{'person_id': 'pid-1', 'reason': 'insufficient_evidence'}]
    assert generated == []


def test_unknown_person_is_reported_and_never_reads_memories(app_client, monkeypatch):
    client, module = app_client
    reads: list[int] = []
    _wire(module, monkeypatch, people=[], memories=[], reads=reads)

    response = client.post('/v1/people/dossiers', json={'people': [{'person_id': 'ghost'}]})

    assert response.json() == {'dossiers': [], 'skipped': [{'person_id': 'ghost', 'reason': 'unknown_person'}]}
    assert reads == []


def test_a_grounded_empty_result_is_skipped_not_an_empty_card(app_client, monkeypatch):
    client, module = app_client
    _wire(
        module,
        monkeypatch,
        people=[{'id': 'pid-1', 'name': 'Priya'}],
        memories=[_memory(f'fact {i}', 'person:pid-1') for i in range(5)],
    )
    monkeypatch.setattr(
        module,
        'generate_person_dossier',
        lambda *args: GroundedDossier(None, None, None, [], [], [], []),
    )

    response = client.post('/v1/people/dossiers', json={'people': [{'person_id': 'pid-1'}]})

    assert response.json()['dossiers'] == []
    assert response.json()['skipped'] == [{'person_id': 'pid-1', 'reason': 'insufficient_evidence'}]


def test_batch_is_capped_and_deduped(app_client, monkeypatch):
    client, module = app_client
    over_cap = module.MAX_PEOPLE_PER_REQUEST + 5
    _wire(module, monkeypatch, people=[], memories=[])

    response = client.post(
        '/v1/people/dossiers',
        json={'people': [{'person_id': f'pid-{i}'} for i in range(over_cap)]},
    )

    # Pydantic rejects an over-cap batch outright rather than silently truncating it, so a client
    # cannot fan out an address book's worth of model calls in one request.
    assert response.status_code == 422

    duplicated = client.post(
        '/v1/people/dossiers',
        json={'people': [{'person_id': 'pid-1'}, {'person_id': 'pid-1'}]},
    )
    assert duplicated.json()['skipped'] == [{'person_id': 'pid-1', 'reason': 'unknown_person'}]
