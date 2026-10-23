"""The episodes API: the capability flag, reads, wrap-up and dismiss."""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import episodes as config
from routers import episodes as router_module
from utils.other import endpoints as auth

T0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
EPISODE = {
    'id': 'e1',
    'status': 'live',
    'started_at': T0,
    'last_activity_at': T0,
    'title': 'Coding at the café',
    'bullets': ['Lunch at 12:30'],
    'people': ['Huong'],
    'provisional_items': [
        {'id': 'p1', 'text': 'Book lunch table', 'kind': 'task', 'status': 'provisional', 'created_at': T0}
    ],
    'moments': [{'id': 'm1', 'conversation_id': 'c1', 'started_at': T0, 'ended_at': T0, 'heading': 'Lunch plans'}],
    'conversation_ids': ['c1'],
    'sources': ['omi'],
    'applied': {'c1': 20.0},
    'usage': {'calls': 1},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)
    # The capability marker is Redis; test_episodes_client_gate covers it.
    monkeypatch.setattr(router_module.client_gate, 'note_client_seen', lambda uid: False)
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'uid-1'
    # Write routes wrap auth in a rate limiter; resolve every route dependency to the test uid.
    for route in app.routes:
        for dependency in getattr(getattr(route, 'dependant', None), 'dependencies', []):
            app.dependency_overrides[dependency.call] = lambda: 'uid-1'
    # A TestFlight build (beta channel); test_episodes_client_gate covers the channel gate.
    return app, TestClient(app, headers={'X-Omi-App-Channel': 'beta'})


def test_live_reports_capability_and_projects_the_wire_shape(client, monkeypatch):
    _, http = client
    monkeypatch.setattr(router_module.service, 'live_episode', lambda uid: dict(EPISODE))
    body = http.get('/v1/episodes/live').json()
    assert body['enabled'] is True
    assert body['episode']['title'] == 'Coding at the café'
    assert body['episode']['provisional_items'][0]['status'] == 'provisional'
    assert 'applied' not in body['episode'] and 'usage' not in body['episode']

    monkeypatch.setattr(router_module.service, 'live_episode', lambda uid: None)
    assert http.get('/v1/episodes/live').json() == {'enabled': True, 'episode': None}


def test_kill_switch_reports_disabled_and_refuses_writes(client, monkeypatch):
    _, http = client
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    monkeypatch.setattr(router_module.service, 'live_episode', lambda uid: pytest.fail('must not read'))
    assert http.get('/v1/episodes/live').json() == {'enabled': False, 'episode': None}
    assert http.get('/v1/episodes/by-conversation/c1').json() == {'enabled': False, 'episode': None}
    assert http.post('/v1/episodes/e1/wrap-up', json={}).status_code == 404


def test_lookup_wrap_up_and_dismiss(client, monkeypatch):
    app, http = client
    calls = []
    monkeypatch.setattr(router_module.service, 'episode_for_conversation', lambda uid, cid: dict(EPISODE))
    monkeypatch.setattr(
        router_module.service,
        'wrap_up',
        lambda uid, eid, conversation_id: calls.append(('wrap', eid, conversation_id)) or {**EPISODE, 'status': 'live'},
    )
    monkeypatch.setattr(
        router_module.service,
        'dismiss_item',
        lambda uid, eid, item_id: calls.append(('dismiss', eid, item_id)) or dict(EPISODE),
    )
    assert http.get('/v1/episodes/by-conversation/c1').json()['episode']['id'] == 'e1'
    assert http.post('/v1/episodes/e1/wrap-up', json={'conversation_id': 'c1'}).status_code == 200
    assert http.post('/v1/episodes/e1/wrap-up').status_code == 200
    assert http.post('/v1/episodes/e1/items/p1/dismiss').status_code == 200
    assert calls == [('wrap', 'e1', 'c1'), ('wrap', 'e1', None), ('dismiss', 'e1', 'p1')]
    monkeypatch.setattr(router_module.service, 'wrap_up', lambda uid, eid, conversation_id: None)
    assert http.post('/v1/episodes/missing/wrap-up').status_code == 404
