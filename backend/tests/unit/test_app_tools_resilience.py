"""Tests for hardening app_tools against malformed schemas, non-dict configs, and HTTP method normalization."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import utils.retrieval.tools.app_tools as app_tools
from models.app import ChatTool


class TestSchemaAndArgumentHardening:
    mod = app_tools

    def test_create_pydantic_model_from_non_dict_parameters(self):
        """Non-dict parameters must return a valid model without raising AttributeError."""
        model = self.mod._create_pydantic_model_from_schema("test_tool", None)
        assert model is not None
        instance = model()
        assert instance.model_dump() == {}

        model2 = self.mod._create_pydantic_model_from_schema("test-tool.name", "invalid")
        assert model2 is not None

    def test_create_pydantic_model_from_malformed_properties_and_required(self):
        """Schema with None or malformed properties / required must not raise TypeError or AttributeError."""
        malformed_schema = {
            "properties": None,
            "required": None,
        }
        model = self.mod._create_pydantic_model_from_schema("malformed_tool", malformed_schema)
        assert model is not None
        assert model().model_dump() == {}

        # Malformed param_schema inside properties
        weird_props = {
            "properties": {
                "bad_param": "not_a_dict",
                "": {"type": "string"},  # empty param name
                123: {"type": "integer"},  # non-string param name
                "good_param": {"type": "string", "description": "valid"},
            },
            "required": ["good_param"],
        }
        model_props = self.mod._create_pydantic_model_from_schema("weird_props", weird_props)
        assert "good_param" in model_props.model_fields
        assert "bad_param" in model_props.model_fields

    def test_supplied_arguments_with_non_dict_kwargs(self):
        """Non-dict kwargs must return empty dict instead of raising AttributeError."""
        assert self.mod._supplied_arguments(None) == {}
        assert self.mod._supplied_arguments("string") == {}
        assert self.mod._supplied_arguments([1, 2, 3]) == {}

    def test_supplied_arguments_drops_none(self):
        """Only non-None arguments must be preserved."""
        assert self.mod._supplied_arguments({"a": 1, "b": None, "c": "foo"}) == {"a": 1, "c": "foo"}


class TestCreateAppToolResilience:
    mod = app_tools

    def test_create_app_tool_with_none_or_non_dict_parameters(self):
        """Tool manifest with parameters=None or non-dict must initialize cleanly."""
        tool_none = ChatTool(name="test_tool_none", description="d", endpoint="https://app.test/run", parameters=None)
        structured_none = self.mod.create_app_tool(tool_none, "app-1", "App1")
        assert structured_none.name == "app-1_test_tool_none"

        tool_str = ChatTool(name="test_tool_str", description="d", endpoint="https://app.test/run", parameters="none")
        structured_str = self.mod.create_app_tool(tool_str, "app-2", "App2")
        assert structured_str.name == "app-2_test_tool_str"

    def test_create_mcp_tool_transport_fallback_and_tokens_safety(self):
        """MCP tool with transport=None or non-dict mcp_oauth_tokens must default transport and avoid AttributeError."""
        tool_mcp = ChatTool(
            name="mcp_test",
            description="d",
            endpoint="https://mcp.test/run",
            parameters={},
        )
        tool_mcp.is_mcp = True
        tool_mcp.transport = None

        # non-dict tokens
        structured = self.mod.create_app_tool(
            tool_mcp,
            "app-mcp",
            "AppMCP",
            mcp_server_url="https://mcp.example.com",
            mcp_oauth_tokens="invalid_tokens",
        )
        assert structured.name == "app-mcp_mcp_test"


class TestCallToolEndpointResilience:
    mod = app_tools

    @pytest.mark.asyncio
    async def test_non_dict_config_returns_error(self):
        """Non-dict config must return configuration error rather than raising AttributeError."""
        tool = ChatTool(name="sample_tool", description="d", endpoint="https://app.test/run", parameters={})
        res = await self.mod._call_tool_endpoint(
            kwargs={},
            config="invalid_config",
            app_tool=tool,
            app_id="app-1",
        )
        assert "Error: Configuration not available for sample_tool" in res

    @pytest.mark.asyncio
    async def test_top_level_user_id_and_uid_alias_fallbacks(self):
        """Tool endpoint extracts user ID when supplied at top-level config or via 'uid' alias."""
        tool = ChatTool(name="sample_tool", description="d", endpoint="https://app.test/run", parameters={})

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"ok": True}
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        breaker = MagicMock()
        breaker.allow_request.return_value = True

        # 1. user_id at top-level config
        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=breaker),
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
        ):
            res1 = await self.mod._call_tool_endpoint(
                kwargs={},
                config={"user_id": "top-uid-123"},
                app_tool=tool,
                app_id="app-1",
            )
            assert "ok" in res1
            call_kwargs = mock_client.request.call_args.kwargs
            assert call_kwargs["json"]["uid"] == "top-uid-123"

        # 2. 'uid' inside configurable
        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=breaker),
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
        ):
            res2 = await self.mod._call_tool_endpoint(
                kwargs={},
                config={"configurable": {"uid": "alias-uid-456"}},
                app_tool=tool,
                app_id="app-1",
            )
            assert "ok" in res2
            call_kwargs = mock_client.request.call_args.kwargs
            assert call_kwargs["json"]["uid"] == "alias-uid-456"

    @pytest.mark.asyncio
    async def test_delete_and_custom_http_methods_preserve_payload_and_normalize(self):
        """DELETE requests route payload via params instead of dropping, and method is normalized."""
        tool = ChatTool(
            name="delete_item",
            description="d",
            endpoint="https://app.test/items",
            parameters={},
        )
        tool.method = "delete "  # lowercase with whitespace

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"deleted": True}
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        breaker = MagicMock()
        breaker.allow_request.return_value = True

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=breaker),
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
        ):
            await self.mod._call_tool_endpoint(
                kwargs={"item_id": "item-999"},
                config={"configurable": {"user_id": "u1"}},
                app_tool=tool,
                app_id="app-1",
            )
            call_kwargs = mock_client.request.call_args.kwargs
            assert mock_client.request.call_args.kwargs.get("method") == "DELETE"
            # DELETE payload routed to params
            assert call_kwargs["params"]["item_id"] == "item-999"
            assert call_kwargs["params"]["uid"] == "u1"
            assert "json" not in call_kwargs
