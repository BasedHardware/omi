"""Offline ASGI checks for the authenticated first-value routes."""

from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import first_value_recovery as recovery
from routers import first_value_recovery as routes
from utils.other import endpoints as auth


def _client(monkeypatch, enabled):
    monkeypatch.setattr(routes, 'recovery_enabled', lambda: enabled)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'fixture-user'
    return TestClient(
        app,
        headers={
            'X-Omi-First-Value-Protocol': '1',
            'X-Omi-Notification-Permission': 'granted',
            'X-Omi-Time-Zone': 'UTC',
        },
    )


def test_off_prompt_does_no_eligibility_query(monkeypatch):
    selected = Mock(side_effect=AssertionError('off path selected paid starts'))
    monkeypatch.setattr(recovery, 'recent_starts', selected)
    response = _client(monkeypatch, False).get('/v1/first-value/recovery/prompt')
    assert response.status_code == 200
    assert response.json() == {'prompt': None}
    selected.assert_not_called()


def test_off_stops_outcome_and_pendant_io(monkeypatch):
    result = Mock(return_value=1)
    pendant = Mock(side_effect=AssertionError('off pendant write'))
    selected = Mock(side_effect=AssertionError('off pendant eligibility read'))
    monkeypatch.setattr(recovery, 'recent_starts', selected)
    monkeypatch.setattr(recovery, 'record_result_open', result)
    monkeypatch.setattr(recovery, 'record_pendant_connection', pendant)
    client = _client(monkeypatch, False)
    assert client.post('/v1/first-value/recovery/result-open', json={'conversation_id': 'result-1'}).json() == {
        'recorded': 0
    }
    assert client.post('/v1/first-value/recovery/pendant-connection').json() == {'recorded': False}
    result.assert_not_called()
    pendant.assert_not_called()
    selected.assert_not_called()


def test_unsupported_protocol_has_no_eligibility_query_or_capability_write(monkeypatch):
    selected = Mock(side_effect=AssertionError('unsupported client eligibility read'))
    capability = Mock(side_effect=AssertionError('unsupported client capability write'))
    monkeypatch.setattr(recovery, 'recent_starts', selected)
    monkeypatch.setattr(recovery, 'record_client_capability', capability)
    client = _client(monkeypatch, True)
    client.headers['X-Omi-First-Value-Protocol'] = '0'

    assert client.get('/v1/first-value/recovery/prompt').json() == {'prompt': None}
    selected.assert_not_called()
    capability.assert_not_called()


def test_in_app_prompt_returns_server_claimed_shipped_capture_route(monkeypatch):
    monkeypatch.setattr(recovery, 'recent_starts', lambda uid, now: [{'start_id': 'a' * 32}])
    monkeypatch.setattr(recovery, 'record_client_capability', lambda uid, start_id, start, **kwargs: dict(start))
    monkeypatch.setattr(recovery, 'probe_start', lambda uid, start_id, start, now: dict(start, variant='treatment'))
    monkeypatch.setattr(recovery, 'iter_candidate_kinds', lambda start, now: iter(['capture']))
    claimed = Mock(
        return_value={'kind': 'capture', 'channel': 'in_app', 'route': '/settings/device', 'claimed_at': None}
    )
    monkeypatch.setattr(recovery, 'claim_prompt', claimed)
    monkeypatch.setattr(routes, 'emit_product_event', lambda **_kwargs: None)

    response = _client(monkeypatch, True).get('/v1/first-value/recovery/prompt')

    assert response.status_code == 200
    assert response.json()['prompt']['route'] == '/settings/device'
    assert 'start_id' not in response.json()['prompt']
    assert claimed.call_args.args[3:5] == ('capture', 'in_app')


def test_push_navigation_returns_only_an_existing_result_claim(monkeypatch):
    monkeypatch.setattr(recovery, 'recent_starts', lambda uid, now: [{'start_id': 'a' * 32}])
    monkeypatch.setattr(
        recovery, 'record_client_capability', Mock(side_effect=AssertionError('navigation must not refresh capability'))
    )
    monkeypatch.setattr(recovery, 'probe_start', lambda uid, start_id, start, now: start)
    resolved = Mock(return_value={'kind': 'result', 'channel': 'push_navigation', 'route': '/conversation/result-1'})
    monkeypatch.setattr(recovery, 'resolve_push_navigation', resolved)
    claimed = Mock(side_effect=AssertionError('push navigation must not claim again'))
    monkeypatch.setattr(recovery, 'claim_prompt', claimed)

    response = _client(monkeypatch, True).get('/v1/first-value/recovery/prompt?navigation=true&kind=result')

    assert response.status_code == 200
    assert response.json()['prompt']['route'] == '/conversation/result-1'
    resolved.assert_called_once()
    claimed.assert_not_called()


def test_kill_after_claim_prevents_in_app_response(monkeypatch):
    client = _client(monkeypatch, True)
    monkeypatch.setattr(recovery, 'recent_starts', lambda uid, now: [{'start_id': 'synthetic'}])
    monkeypatch.setattr(recovery, 'record_client_capability', lambda uid, sid, start, **kw: start)
    monkeypatch.setattr(recovery, 'probe_start', lambda uid, sid, start, **kw: start)
    monkeypatch.setattr(recovery, 'iter_candidate_kinds', lambda start, now: iter(['capture']))

    def claim(*a, **kw):
        monkeypatch.setattr(routes, 'recovery_enabled', lambda: False)
        return {'kind': 'capture', 'route': '/settings/device'}

    monkeypatch.setattr(recovery, 'claim_prompt', claim)
    assert client.get('/v1/first-value/recovery/prompt').json() == {'prompt': None}
