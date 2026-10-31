"""The owner-only refresh endpoint shares durable rotation with ordinary tool calls."""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from routers import apps as router
from tests.unit.test_mcp_client_token_persistence import connection  # noqa: F401 -- shared fake authority fixture
from utils import mcp_client


@pytest.fixture
def endpoint(connection, monkeypatch):
    store, _, _ = connection
    store.rows[('plugins_data', 'app')]['uid'] = 'owner'
    user = {'uid': 'owner'}
    update = MagicMock()
    monkeypatch.setattr(router, 'update_app_in_db', update)
    monkeypatch.setattr(router, 'delete_app_cache_by_id', MagicMock())
    discover = AsyncMock(side_effect=[PermissionError('expired'), []])
    monkeypatch.setattr(router, 'discover_mcp_tools', discover)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: user['uid']
    with TestClient(app) as client:
        yield client, store, user, discover, update


def test_endpoint_saves_rotation_before_retry_without_rewriting_the_token_map(endpoint):
    client, store, _, discover, update = endpoint
    response = client.post('/v1/apps/app/mcp/refresh')
    assert response.status_code == 200, response.text
    assert response.json() == {'tools_count': 0, 'tool_names': []}
    assert discover.await_args_list[1].args[1] == 'access-1'
    assert (
        store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']['refresh_token'] == 'refresh-1'
    )
    update.assert_called_once_with({'id': 'app', 'chat_tools': []})


def test_endpoint_keeps_saved_rotation_when_discovery_retry_fails(endpoint):
    client, store, _, discover, update = endpoint
    discover.side_effect = [PermissionError('expired'), RuntimeError('provider-private-text')]
    response = client.post('/v1/apps/app/mcp/refresh')
    assert response.status_code == 502 and 'provider-private-text' not in response.text
    assert (
        store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']['refresh_token'] == 'refresh-1'
    )
    update.assert_not_called()


def test_endpoint_does_not_refresh_another_owners_connection(endpoint):
    client, _, user, discover, update = endpoint
    user['uid'] = 'other'
    response = client.post('/v1/apps/app/mcp/refresh')
    assert response.status_code == 403
    discover.assert_not_awaited()
    mcp_client.refresh_oauth_token.assert_not_awaited()
    update.assert_not_called()


def test_endpoint_returns_reauthorization_for_rejected_refresh(endpoint, monkeypatch):
    client, _, _, _, update = endpoint
    monkeypatch.setattr(mcp_client, 'refresh_oauth_token', AsyncMock(side_effect=RuntimeError('private-provider-body')))
    response = client.post('/v1/apps/app/mcp/refresh')
    assert response.status_code == 401 and 'private-provider-body' not in response.text
    update.assert_not_called()
