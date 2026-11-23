"""Exercise the released surface reporting contract over ASGI with synthetic identity."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def endpoint(monkeypatch):
    from routers import users

    app = FastAPI()
    app.include_router(users.router)
    monkeypatch.setattr(users.auth, '_enforce_rate_limit', Mock())
    return app, users


def test_released_surface_payload_is_acknowledged_and_rejects_uid_override(endpoint):
    app, users = endpoint
    app.dependency_overrides[users.auth.get_current_user_uid] = lambda: 'synthetic-owner'
    client = TestClient(app)
    payload = {'session_id': 'synthetic-phone', 'foreground': True, 'surface_open': True, 'transcript_visible': False}
    response = client.post('/v1/users/client-state', json=payload)
    assert response.status_code == 200 and response.json() == {'status': 'ok'}
    assert client.post('/v1/users/client-state', json={**payload, 'uid': 'other'}).status_code == 422


def test_surface_report_requires_authentication(endpoint):
    app, _ = endpoint
    response = TestClient(app).post(
        '/v1/users/client-state',
        json={
            'session_id': 'synthetic-phone',
            'foreground': True,
            'surface_open': True,
            'transcript_visible': False,
        },
    )
    assert response.status_code in {401, 403}


def test_enrichment_checkpoint_is_a_blind_update_and_never_recreates(endpoint):
    from database import conversations
    from google.api_core.exceptions import NotFound

    client, ref = Mock(), Mock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value = ref
    assert conversations.record_demand_enrichment_checkpoint(
        'synthetic-owner', 'conversation', 'digest', firestore_client=client
    )
    ref.get.assert_not_called()
    ref.set.assert_not_called()
    ref.update.assert_called_once_with({'demand_enrichment_applied_hash': 'digest'})
    ref.update.side_effect = NotFound('removed')
    assert not conversations.record_demand_enrichment_checkpoint(
        'synthetic-owner', 'conversation', 'digest', firestore_client=client
    )


def test_surface_auth_retains_security_fences_without_registration_or_recovery(endpoint, monkeypatch):
    from types import SimpleNamespace

    _, users = endpoint
    auth = users.auth
    monkeypatch.setattr(auth, 'verify_token', lambda _: 'synthetic-owner')
    deletion, cutover, byok = Mock(), Mock(), Mock()
    monkeypatch.setattr(auth, 'enforce_account_deletion_http_access', deletion)
    monkeypatch.setattr(auth, '_enforce_cutover_http_if_request', cutover)
    monkeypatch.setattr(auth, 'validate_byok_request', byok)
    registration, device, recovery = Mock(), Mock(), Mock()
    monkeypatch.setattr(auth, 'record_user_platform', registration)
    monkeypatch.setattr(auth, 'record_client_device', device)
    monkeypatch.setattr(auth, '_recover_locked_content_if_request', recovery)
    request = SimpleNamespace(url=SimpleNamespace(path='/v1/users/client-state'))
    assert auth.get_current_user_uid(authorization='Bearer synthetic-token', request=request) == 'synthetic-owner'
    deletion.assert_called_once_with('synthetic-owner')
    cutover.assert_called_once_with('synthetic-owner', request)
    byok.assert_called_once_with('synthetic-owner')
    registration.assert_not_called()
    device.assert_not_called()
    recovery.assert_not_called()


@pytest.fixture
def listen_receiver_module():
    from routers.listen import receiver

    return receiver


@pytest.mark.parametrize('surface_open', [{}, {'surface_open': True}, {'surface_open': False}])
@pytest.mark.asyncio
async def test_released_listen_state_still_updates_visibility(listen_receiver_module, monkeypatch, surface_open):
    import json
    from types import SimpleNamespace

    module = listen_receiver_module
    monkeypatch.setattr(module, 'resolve_ondemand_config', lambda: SimpleNamespace(gate_enabled=False))
    visibility = Mock()
    receiver = module.ListenReceiver.__new__(module.ListenReceiver)
    receiver.host = SimpleNamespace(state=SimpleNamespace(realtime_demand=visibility))
    payload = {'type': 'client_state', 'foreground': True, 'transcript_visible': True, **surface_open}
    await receiver._handle_text(json.dumps(payload))
    visibility.observe.assert_called_once_with(payload)
