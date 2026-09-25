import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

from tests.unit.memory_import_isolation import (
    AutoMockModule,
    install_database_client_stub,
)

stub = install_database_client_stub()
stub.run_transactional = MagicMock()

for name in [
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
]:
    if name not in sys.modules or not isinstance(sys.modules[name], AutoMockModule):
        sys.modules[name] = AutoMockModule(name)

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

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


@pytest.mark.asyncio
async def test_generate_app_endpoint_does_not_leak_exception():
    request = GenerateAppRequest(prompt="Create a fitness motivation bot for my workouts")
    with patch("utils.llm.app_generator.generate_app_from_prompt", new_callable=AsyncMock) as mock_gen, \
         patch("routers.apps.track_usage"):
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
async def test_generate_app_icon_endpoint_does_not_leak_exception():
    request = GenerateAppIconRequest(
        name="FitnessBot",
        description="Tracks workouts",
        category="health",
    )
    with patch("utils.llm.app_generator.generate_app_icon", new_callable=AsyncMock) as mock_gen, \
         patch("routers.apps.track_usage"):
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


@pytest.mark.asyncio
async def test_add_mcp_server_oauth_registration_does_not_leak_exception():
    request = McpServerRequest(name="Test MCP", mcp_server_url="https://mcp.example.com")
    with patch("routers.apps.discover_oauth_metadata", new_callable=AsyncMock) as mock_oauth, \
         patch("routers.apps.register_oauth_client", new_callable=AsyncMock) as mock_reg, \
         patch.dict("os.environ", {"BASE_API_URL": "https://api.omi.me"}):
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
    with patch("routers.apps.discover_oauth_metadata", new_callable=AsyncMock) as mock_oauth, \
         patch("routers.apps.discover_mcp_tools", new_callable=AsyncMock) as mock_disc:
        mock_oauth.return_value = None
        mock_disc.side_effect = RuntimeError(f"Internal SSL handshake error with {SENSITIVE_TRACE}")

        with pytest.raises(HTTPException) as exc_info:
            await add_mcp_server(data=request, uid="test-user-123")

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Failed to discover MCP tools"
        assert SENSITIVE_TRACE not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_mcp_oauth_callback_token_exchange_does_not_leak_exception():
    with patch("routers.apps.parse_state_token", return_value=("app-123", "uid-123")), \
         patch("routers.apps.get_app_by_id_db") as mock_get_app, \
         patch("routers.apps.exchange_oauth_code", new_callable=AsyncMock) as mock_exchange:
        mock_get_app.return_value = {
            "id": "app-123",
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
    with patch("routers.apps.parse_state_token", return_value=("app-123", "uid-123")), \
         patch("routers.apps.get_app_by_id_db") as mock_get_app, \
         patch("routers.apps.exchange_oauth_code", new_callable=AsyncMock) as mock_exchange, \
         patch("routers.apps.discover_mcp_tools", new_callable=AsyncMock) as mock_disc:
        mock_get_app.return_value = {
            "id": "app-123",
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
    with patch("routers.apps.get_app_by_id_db") as mock_get_app, \
         patch("routers.apps.discover_mcp_tools", new_callable=AsyncMock) as mock_disc:
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
