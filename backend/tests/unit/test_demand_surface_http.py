"""Exercise the real surface-intent endpoint over ASGI with synthetic identity."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def endpoint(monkeypatch):
    from routers import users
    from utils.conversations import demand_processing

    app = FastAPI()
    app.include_router(users.router)
    monkeypatch.setattr(users.auth, '_enforce_rate_limit', Mock())
    report = Mock()
    monkeypatch.setattr(demand_processing, 'observe_surface', report)
    return app, users, report


def test_surface_lease_uses_authenticated_owner_and_rejects_uid_payload(endpoint):
    app, users, report = endpoint
    app.dependency_overrides[users.auth.get_current_user_uid] = lambda: 'synthetic-owner'
    client = TestClient(app)
    payload = {'session_id': 'synthetic-phone', 'foreground': True, 'surface_open': True, 'transcript_visible': False}
    response = client.post('/v1/users/client-state', json=payload)
    assert response.status_code == 200 and response.json() == {'status': 'ok'}
    assert report.call_args.args[:2] == ('synthetic-owner', 'synthetic-phone')
    assert report.call_args.args[2]['surface_open'] is True
    assert client.post('/v1/users/client-state', json={**payload, 'uid': 'other'}).status_code == 422
    assert report.call_count == 1


def test_surface_lease_requires_authentication(endpoint):
    app, _, report = endpoint
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
    report.assert_not_called()


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

    _, users, _ = endpoint
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


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.asyncio
async def test_websocket_surface_signal_uses_the_executor_only_when_enabled(
    endpoint, listen_receiver_module, monkeypatch, enabled
):
    import json
    from types import SimpleNamespace

    module = listen_receiver_module
    _, _, report = endpoint
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true' if enabled else 'false')
    monkeypatch.setenv('DEMAND_PROCESSING_PERCENT', '100')
    monkeypatch.setenv('DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED', 'true')
    monkeypatch.setattr(module, 'resolve_ondemand_config', lambda: SimpleNamespace(gate_enabled=False))
    receiver = module.ListenReceiver.__new__(module.ListenReceiver)
    receiver.host = SimpleNamespace(
        state=SimpleNamespace(realtime_demand=Mock(observe=Mock(return_value=True))), session_id='synthetic-socket'
    )
    if enabled:
        receiver.host.request = SimpleNamespace(uid='synthetic-owner')
    payload = {'type': 'client_state', 'surface_open': True, 'foreground': True, 'transcript_visible': False}
    await receiver._handle_text(json.dumps(payload))
    if enabled:
        report.assert_called_once_with('synthetic-owner', 'synthetic-socket', payload)
    else:
        report.assert_not_called()
    receiver.host.state.realtime_demand.observe.assert_called_once_with(payload)


@pytest.mark.parametrize('platform', ['ios', 'android', 'mobile', 'macos'])
@pytest.mark.asyncio
async def test_released_listen_state_remains_telemetry_with_all_server_flags_on(
    endpoint, listen_receiver_module, monkeypatch, platform
):
    import json
    from types import SimpleNamespace

    module = listen_receiver_module
    _, _, report = endpoint
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true')
    monkeypatch.setenv('DEMAND_PROCESSING_PERCENT', '100')
    monkeypatch.setenv('DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED', 'true')
    monkeypatch.setattr(module, 'resolve_ondemand_config', lambda: SimpleNamespace(gate_enabled=False))
    receiver = module.ListenReceiver.__new__(module.ListenReceiver)
    receiver.host = SimpleNamespace(
        request=SimpleNamespace(uid='synthetic-owner'),
        state=SimpleNamespace(realtime_demand=Mock(observe=Mock(return_value=True))),
        session_id='released-socket',
    )
    monkeypatch.setattr(receiver, '_telemetry_platform', lambda: platform)
    payload = {'type': 'client_state', 'foreground': True, 'transcript_visible': True}
    await receiver._handle_text(json.dumps(payload))
    report.assert_not_called()
    receiver.host.state.realtime_demand.observe.assert_called_once_with(payload)
