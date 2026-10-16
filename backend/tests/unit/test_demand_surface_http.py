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
    app.add_api_route('/v1/users/client-state', users.report_surface_state, methods=['POST'])
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
    admission, deletion, cutover, byok = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(auth, 'enforce_jit_qa_uid', admission)
    monkeypatch.setattr(auth, 'enforce_account_deletion_http_access', deletion)
    monkeypatch.setattr(auth, '_enforce_cutover_http_if_request', cutover)
    monkeypatch.setattr(auth, 'validate_byok_request', byok)
    registration, device, recovery = Mock(), Mock(), Mock()
    monkeypatch.setattr(auth, 'record_user_platform', registration)
    monkeypatch.setattr(auth, 'record_client_device', device)
    monkeypatch.setattr(auth, '_recover_locked_content_if_request', recovery)
    request = SimpleNamespace(url=SimpleNamespace(path='/v1/users/client-state'))
    assert auth.get_current_user_uid(authorization='Bearer synthetic-token', request=request) == 'synthetic-owner'
    admission.assert_called_once_with('synthetic-owner')
    deletion.assert_called_once_with('synthetic-owner')
    cutover.assert_called_once_with('synthetic-owner', request)
    byok.assert_called_once_with('synthetic-owner')
    registration.assert_not_called()
    device.assert_not_called()
    recovery.assert_not_called()
