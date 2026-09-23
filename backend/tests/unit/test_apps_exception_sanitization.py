"""Unit tests for apps router exception detail sanitization.

Verifies that internal exceptions, provider network errors, and raw secrets
in generate-app, generate-icon, MCP tool discovery, and MCP OAuth callback handlers
are masked and not leaked in HTTP response bodies or HTML failure pages.
"""

from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
import pytest

from routers import apps as apps_routes


@pytest.mark.asyncio
async def test_generate_app_endpoint_masks_internal_error_detail(monkeypatch):
    monkeypatch.setattr(apps_routes, 'run_blocking', AsyncMock(return_value=None))
    monkeypatch.setattr(apps_routes, 'track_usage', MagicMock())
    mock_gen = AsyncMock(side_effect=RuntimeError('internal_cluster_failure: token=sec_12345'))
    monkeypatch.setattr('utils.llm.app_generator.generate_app_from_prompt', mock_gen)

    req = apps_routes.GenerateAppRequest(prompt='create a fitness assistant app for runners')
    with pytest.raises(HTTPException) as caught:
        await apps_routes.generate_app_endpoint(req, uid='user-1')

    assert caught.value.status_code == 500
    assert caught.value.detail == 'Failed to generate app. Please try again later.'
    assert 'internal_cluster_failure' not in str(caught.value.detail)
    assert 'sec_12345' not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_generate_app_icon_endpoint_masks_internal_error_detail(monkeypatch):
    monkeypatch.setattr(apps_routes, 'run_blocking', AsyncMock(return_value=None))
    monkeypatch.setattr(apps_routes, 'track_usage', MagicMock())
    mock_icon = AsyncMock(side_effect=RuntimeError('dalle_api_failed: secret_key=sec_99999'))
    monkeypatch.setattr('utils.llm.app_generator.generate_app_icon', mock_icon)

    req = apps_routes.GenerateAppIconRequest(name='FitnessApp', description='App for runners', category='health')
    with pytest.raises(HTTPException) as caught:
        await apps_routes.generate_app_icon_endpoint(req, uid='user-1')

    assert caught.value.status_code == 500
    assert caught.value.detail == 'Failed to generate icon. Please try again later.'
    assert 'dalle_api_failed' not in str(caught.value.detail)
    assert 'sec_99999' not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_mcp_oauth_callback_masks_token_exchange_error_detail(monkeypatch):
    monkeypatch.setattr(apps_routes, 'parse_state_token', lambda state: ('app-1', 'user-1'))
    monkeypatch.setattr(
        apps_routes,
        'run_blocking',
        AsyncMock(
            return_value={
                'id': 'app-1',
                'external_integration': {
                    'mcp_oauth_tokens': {'token_endpoint': 'https://oauth.example.com/token', 'client_id': 'cid'},
                    'mcp_server_url': 'https://mcp.example.com',
                },
            }
        ),
    )
    mock_exchange = AsyncMock(side_effect=RuntimeError('upstream_oauth_tls_error: client_secret=shhh_secret'))
    monkeypatch.setattr(apps_routes, 'exchange_oauth_code', mock_exchange)

    resp = await apps_routes.mcp_oauth_callback(code='auth_code_123', state='valid_state')
    assert resp.status_code == 502
    body = resp.body.decode('utf-8')
    assert 'Token exchange failed' in body
    assert 'shhh_secret' not in body
    assert 'upstream_oauth_tls_error' not in body
    assert 'Failed to exchange authorization code. Please try again.' in body


@pytest.mark.asyncio
async def test_mcp_oauth_callback_masks_tool_discovery_error_detail(monkeypatch):
    monkeypatch.setattr(apps_routes, 'parse_state_token', lambda state: ('app-1', 'user-1'))
    monkeypatch.setattr(
        apps_routes,
        'run_blocking',
        AsyncMock(
            return_value={
                'id': 'app-1',
                'external_integration': {
                    'mcp_oauth_tokens': {'token_endpoint': 'https://oauth.example.com/token', 'client_id': 'cid'},
                    'mcp_server_url': 'https://mcp.example.com',
                },
            }
        ),
    )
    monkeypatch.setattr(apps_routes, 'exchange_oauth_code', AsyncMock(return_value={'access_token': 'tok_123'}))
    mock_discover = AsyncMock(side_effect=RuntimeError('internal_mcp_socket_leak: port=9999'))
    monkeypatch.setattr(apps_routes, 'discover_mcp_tools', mock_discover)

    resp = await apps_routes.mcp_oauth_callback(code='auth_code_123', state='valid_state')
    assert resp.status_code == 502
    body = resp.body.decode('utf-8')
    assert 'Tool discovery failed' in body
    assert 'internal_mcp_socket_leak' not in body
    assert 'port=9999' not in body
    assert 'Failed to discover tools from the specified server. Please try again.' in body


@pytest.mark.asyncio
async def test_refresh_mcp_tools_masks_discovery_error_detail(monkeypatch):
    monkeypatch.setattr(
        apps_routes,
        'run_blocking',
        AsyncMock(
            return_value={
                'id': 'app-1',
                'uid': 'user-1',
                'external_integration': {'mcp_server_url': 'https://mcp.example.com'},
            }
        ),
    )
    mock_discover = AsyncMock(side_effect=RuntimeError('mcp_server_connection_reset: ip=10.0.0.42'))
    monkeypatch.setattr(apps_routes, 'discover_mcp_tools', mock_discover)

    with pytest.raises(HTTPException) as caught:
        await apps_routes.refresh_mcp_tools(app_id='app-1', uid='user-1')

    assert caught.value.status_code == 502
    assert caught.value.detail == 'Failed to discover tools from the specified server.'
    assert '10.0.0.42' not in str(caught.value.detail)
    assert 'mcp_server_connection_reset' not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_add_mcp_server_masks_oauth_client_registration_error(monkeypatch):
    monkeypatch.setenv('BASE_API_URL', 'https://api.example.com')
    monkeypatch.setattr(apps_routes, 'run_blocking', AsyncMock(return_value={'id': 'app-1', 'uid': 'user-1'}))
    monkeypatch.setattr(
        apps_routes,
        'discover_oauth_metadata',
        AsyncMock(return_value={'registration_endpoint': 'https://oauth.example.com/reg'}),
    )
    mock_reg = AsyncMock(side_effect=RuntimeError('dynamic_client_reg_failed: key=master_token_99'))
    monkeypatch.setattr(apps_routes, 'register_oauth_client', mock_reg)

    req = apps_routes.McpServerRequest(
        name='TestApp',
        mcp_server_url='https://mcp.example.com',
    )
    with pytest.raises(HTTPException) as caught:
        await apps_routes.add_mcp_server(req, uid='user-1')

    assert caught.value.status_code == 502
    assert caught.value.detail == 'OAuth client registration failed on the remote server.'
    assert 'master_token_99' not in str(caught.value.detail)
    assert 'dynamic_client_reg_failed' not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_add_mcp_server_masks_mcp_tool_discovery_error(monkeypatch):
    monkeypatch.setattr(apps_routes, 'run_blocking', AsyncMock(return_value={'id': 'app-1', 'uid': 'user-1'}))
    monkeypatch.setattr(apps_routes, 'discover_oauth_metadata', AsyncMock(return_value=None))
    mock_discover = AsyncMock(side_effect=RuntimeError('upstream_rpc_error: cluster_id=k8s-us-east-1'))
    monkeypatch.setattr(apps_routes, 'discover_mcp_tools', mock_discover)

    req = apps_routes.McpServerRequest(
        name='TestApp',
        mcp_server_url='https://mcp.example.com',
    )
    with pytest.raises(HTTPException) as caught:
        await apps_routes.add_mcp_server(req, uid='user-1')

    assert caught.value.status_code == 502
    assert caught.value.detail == 'Failed to discover MCP tools from the specified server.'
    assert 'k8s-us-east-1' not in str(caught.value.detail)
    assert 'upstream_rpc_error' not in str(caught.value.detail)
