from unittest.mock import AsyncMock, MagicMock, patch

from testing.import_isolation import install_auto_mock_modules
from tests.unit.memory_import_isolation import install_database_client_stub

stub = install_database_client_stub()
stub.run_transactional = MagicMock()

install_auto_mock_modules(
    [
        "anthropic",
        "openai",
        "pinecone",
        "typesense",
        "pycountry",
        "stripe",
        "langchain_anthropic",
        "langchain_openai",
        "langchain_google_genai",
        "langchain_community",
    ]
)

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from routers import apps as apps_routes
from routers.apps import (
    generate_app_endpoint,
    generate_app_icon_endpoint,
    add_mcp_server,
    mcp_oauth_callback,
    refresh_mcp_tools,
    GenerateAppRequest,
    GenerateAppIconRequest,
    McpServerRequest,
)

SENSITIVE_TRACE = "postgresql://user:super_secret_password@internal-db.prod.local:5432/omi"


async def _run_blocking_passthrough(_executor, fn, *args, **kwargs):
    """Run the offloaded call inline so the callback can be driven hermetically."""
    return fn(*args, **kwargs)


@pytest.mark.asyncio
async def test_generate_app_endpoint_does_not_leak_exception():
    request = GenerateAppRequest(prompt="Create a fitness motivation bot for my workouts")
    with patch("utils.llm.app_generator.generate_app_from_prompt", new_callable=AsyncMock) as mock_gen, patch(
        "routers.apps.track_usage"
    ):
        mock_gen.side_effect = RuntimeError(f"Connection timeout to {SENSITIVE_TRACE}")

        with pytest.raises(HTTPException) as exc_info:
            await generate_app_endpoint(
                data=request,
                uid="test-user-123",
                x_app_platform="ios",
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to generate app"
        assert SENSITIVE_TRACE not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_generate_app_icon_endpoint_does_not_leak_exception(monkeypatch):
    monkeypatch.setenv('APP_ICON_GENERATION_ENABLED', 'true')
    request = GenerateAppIconRequest(
        name="FitnessBot",
        description="Tracks workouts",
        category="health",
    )
    with patch("utils.llm.app_generator.generate_app_icon", new_callable=AsyncMock) as mock_gen, patch(
        "routers.apps.track_usage"
    ):
        mock_gen.side_effect = RuntimeError(f"API key invalid or socket failed: {SENSITIVE_TRACE}")

        with pytest.raises(HTTPException) as exc_info:
            await generate_app_icon_endpoint(
                data=request,
                uid="test-user-123",
                x_app_platform="ios",
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to generate icon"
        assert SENSITIVE_TRACE not in str(exc_info.value.detail)


@pytest.fixture
def icon_http_client(monkeypatch):
    app = FastAPI()
    app.include_router(apps_routes.router)
    app.dependency_overrides[apps_routes.auth.get_current_user_uid] = lambda: 'test-user'
    quota = MagicMock()
    monkeypatch.setattr(apps_routes, 'generated_compute_configured', lambda: False)
    monkeypatch.setattr(apps_routes, 'enforce_chat_quota', quota)
    with TestClient(app) as client:
        yield client, quota


@pytest.mark.parametrize(
    'gateway_status,error,retry_after,expected_status,expected_code',
    [
        (200, {}, None, 200, None),
        (400, {}, None, 500, None),
        (500, {}, None, 500, None),
        (429, {}, '17', 429, 'icon_generation_rate_limited'),
        (429, {}, None, 429, 'icon_generation_rate_limited'),
        (502, {}, None, 503, 'icon_generation_unavailable'),
        (503, {}, None, 503, 'icon_generation_unavailable'),
        (503, {'code': 'invalid_config'}, None, 424, 'icon_generation_invalid_config'),
        (503, {'message': 'provider request failed: invalid_config'}, None, 424, 'icon_generation_invalid_config'),
        (None, {}, None, 503, 'icon_generation_unavailable'),
    ],
)
def test_generate_app_icon_maps_gateway_response(
    monkeypatch, icon_http_client, gateway_status, error, retry_after, expected_status, expected_code
):
    monkeypatch.setenv('APP_ICON_GENERATION_ENABLED', 'true')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-service-token')

    def gateway_response(request):
        assert request.url.path == '/v1/images/generations'
        assert request.headers['Authorization'] == 'Bearer synthetic-service-token'
        assert request.headers['X-Omi-Service-Caller'] == 'backend'
        if gateway_status is None:
            raise httpx.ReadTimeout(SENSITIVE_TRACE, request=request)
        return httpx.Response(
            gateway_status,
            headers={'Retry-After': retry_after} if retry_after is not None else None,
            json=(
                {'data': [{'b64_json': 'aWNvbg=='}]}
                if gateway_status == 200
                else {'error': {'message': SENSITIVE_TRACE, **error}}
            ),
        )

    gateway_client = httpx.Client(transport=httpx.MockTransport(gateway_response))
    monkeypatch.setattr('utils.llm.gateway_client.httpx.Client', MagicMock(return_value=gateway_client))
    client, _ = icon_http_client
    response = client.post(
        '/v1/app/generate-icon',
        json={'name': 'Test App', 'description': 'Synthetic app description', 'category': 'other'},
        headers={'X-App-Platform': 'ios'},
    )

    assert response.status_code == expected_status
    assert response.headers.get('Retry-After') == retry_after
    if expected_status == 200:
        assert response.json() == {'status': 'ok', 'icon_base64': 'aWNvbg==', 'mime_type': 'image/png'}
    elif expected_code is None:
        assert response.json() == {'detail': 'Failed to generate icon'}
    else:
        assert response.json() == {'detail': {'code': expected_code, 'retryable': expected_status != 424}}


@pytest.mark.parametrize('switch', [None, 'false'])
def test_generate_app_icon_disabled_skips_provider(monkeypatch, icon_http_client, switch):
    if switch is None:
        monkeypatch.delenv('APP_ICON_GENERATION_ENABLED', raising=False)
    else:
        monkeypatch.setenv('APP_ICON_GENERATION_ENABLED', switch)

    generate_icon = AsyncMock()
    monkeypatch.setattr('utils.llm.app_generator.generate_app_icon', generate_icon)
    client, quota = icon_http_client
    response = client.post(
        '/v1/app/generate-icon',
        json={'name': 'Test App', 'description': 'Synthetic app description', 'category': 'other'},
        headers={'X-App-Platform': 'ios'},
    )

    quota.assert_called_once_with('test-user', platform='ios')
    generate_icon.assert_not_called()
    assert response.status_code == 424
    assert response.json() == {'detail': {'code': 'icon_generation_disabled', 'retryable': False}}


@pytest.mark.asyncio
async def test_add_mcp_server_oauth_registration_does_not_leak_exception():
    request = McpServerRequest(name="Test MCP", mcp_server_url="https://mcp.example.com")
    with patch("routers.apps.discover_oauth_metadata", new_callable=AsyncMock) as mock_oauth, patch(
        "routers.apps.register_oauth_client", new_callable=AsyncMock
    ) as mock_reg, patch.dict("os.environ", {"BASE_API_URL": "https://api.omi.me"}):
        mock_oauth.return_value = {
            "registration_endpoint": "https://mcp.example.com/register",
            "authorization_endpoint": "https://mcp.example.com/auth",
        }
        mock_reg.side_effect = ConnectionError(f"Failed to connect to internal auth host: {SENSITIVE_TRACE}")

        with pytest.raises(HTTPException) as exc_info:
            await add_mcp_server(data=request, uid="test-user-123")

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "OAuth client registration failed"
        assert SENSITIVE_TRACE not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_add_mcp_server_direct_discovery_does_not_leak_exception():
    request = McpServerRequest(name="Test MCP", mcp_server_url="https://mcp.example.com")
    with patch("routers.apps.discover_oauth_metadata", new_callable=AsyncMock) as mock_oauth, patch(
        "routers.apps.discover_mcp_tools", new_callable=AsyncMock
    ) as mock_disc:
        mock_oauth.return_value = None
        mock_disc.side_effect = RuntimeError(f"Internal SSL handshake error with {SENSITIVE_TRACE}")

        with pytest.raises(HTTPException) as exc_info:
            await add_mcp_server(data=request, uid="test-user-123")

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Failed to discover MCP tools"
        assert SENSITIVE_TRACE not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_mcp_oauth_callback_token_exchange_does_not_leak_exception():
    with patch("routers.apps.run_blocking", _run_blocking_passthrough), patch(
        "routers.apps.consume_mcp_oauth_state", return_value=("app-123", "uid-123")
    ), patch("routers.apps.get_app_by_id_db") as mock_get_app, patch(
        "routers.apps.exchange_oauth_code", new_callable=AsyncMock
    ) as mock_exchange:
        mock_get_app.return_value = {
            "id": "app-123",
            "uid": "uid-123",
            "external_integration": {
                "mcp_server_url": "https://mcp.example.com",
                "mcp_oauth_tokens": {
                    "token_endpoint": "https://mcp.example.com/token",
                    "client_id": "client-123",
                    "state": "valid-state",
                },
            },
        }
        mock_exchange.side_effect = RuntimeError(f"TLS failure or leaked secret: {SENSITIVE_TRACE}")

        response = await mcp_oauth_callback(code="test-code", state="valid-state")

        assert isinstance(response, HTMLResponse)
        assert response.status_code == 502
        content = response.body.decode("utf-8")
        assert "Token exchange failed" in content
        assert SENSITIVE_TRACE not in content


@pytest.mark.asyncio
async def test_mcp_oauth_callback_tool_discovery_does_not_leak_exception():
    with patch("routers.apps.run_blocking", _run_blocking_passthrough), patch(
        "routers.apps.consume_mcp_oauth_state", return_value=("app-123", "uid-123")
    ), patch("routers.apps.get_app_by_id_db") as mock_get_app, patch(
        "routers.apps.exchange_oauth_code", new_callable=AsyncMock
    ) as mock_exchange, patch(
        "routers.apps.discover_mcp_tools", new_callable=AsyncMock
    ) as mock_disc:
        mock_get_app.return_value = {
            "id": "app-123",
            "uid": "uid-123",
            "external_integration": {
                "mcp_server_url": "https://mcp.example.com",
                "mcp_oauth_tokens": {
                    "token_endpoint": "https://mcp.example.com/token",
                    "client_id": "client-123",
                    "state": "valid-state",
                },
            },
        }
        mock_exchange.return_value = {"access_token": "access-token-xyz"}
        mock_disc.side_effect = RuntimeError(f"Malformed manifest from {SENSITIVE_TRACE}")

        response = await mcp_oauth_callback(code="test-code", state="valid-state")

        assert isinstance(response, HTMLResponse)
        assert response.status_code == 502
        content = response.body.decode("utf-8")
        assert "Tool discovery failed" in content
        assert SENSITIVE_TRACE not in content


@pytest.mark.asyncio
async def test_refresh_mcp_tools_does_not_leak_exception():
    with patch("routers.apps.get_app_by_id_db") as mock_get_app, patch(
        "routers.apps.discover_mcp_tools", new_callable=AsyncMock
    ) as mock_disc:
        mock_get_app.return_value = {
            "id": "app-123",
            "uid": "test-user-123",
            "external_integration": {
                "mcp_server_url": "https://mcp.example.com",
            },
        }
        mock_disc.side_effect = ConnectionRefusedError(f"Cannot reach server: {SENSITIVE_TRACE}")

        with pytest.raises(HTTPException) as exc_info:
            await refresh_mcp_tools(app_id="app-123", uid="test-user-123")

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Failed to discover tools"
        assert SENSITIVE_TRACE not in str(exc_info.value.detail)
