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
