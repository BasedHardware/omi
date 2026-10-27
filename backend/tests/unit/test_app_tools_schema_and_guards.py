"""Unit tests for app_tools schema parsing, null-guards, and configuration fallbacks."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import utils.retrieval.tools.app_tools as app_tools
from models.app import App, ChatTool


def _allowing_breaker():
    breaker = MagicMock()
    breaker.allow_request.return_value = True
    return breaker


class TestAppToolsSchemaAndGuards:
    mod = app_tools

    def test_clean_identifier(self):
        assert self.mod._clean_identifier("valid_name") == "valid_name"
        assert self.mod._clean_identifier("123_invalid_start") == "n_123_invalid_start"
        assert self.mod._clean_identifier("tool:with-special.chars/") == "tool_with_special_chars"
        assert self.mod._clean_identifier("", fallback="fallback_item") == "fallback_item"
        assert self.mod._clean_identifier(None, fallback="fallback_item") == "fallback_item"

    def test_create_pydantic_model_from_schema_none_properties(self):
        # Must not raise AttributeError when properties or required is None
        model = self.mod._create_pydantic_model_from_schema(
            "test_tool", {"properties": None, "required": None}
        )
        assert model is not None
        instance = model()
        assert instance is not None

    def test_create_pydantic_model_from_schema_none_param_schema(self):
        # Must not raise AttributeError when a parameter schema is None
        model = self.mod._create_pydantic_model_from_schema(
            "test_tool", {"properties": {"query": None}, "required": ["query"]}
        )
        assert model is not None
        instance = model(query="hello")
        assert instance.query == "hello"

    def test_create_pydantic_model_from_schema_unusual_tool_name(self):
        # Must produce valid identifier and model without ValueError
        model = self.mod._create_pydantic_model_from_schema(
            "999-my.custom:tool", {"properties": {"param": {"type": "string"}}}
        )
        assert model.__name__.startswith("n_999_my_custom_tool")

    def test_create_app_tool_none_description_and_transport(self):
        tool = MagicMock(spec=ChatTool)
        tool.name = "echo"
        tool.description = None
        tool.endpoint = "https://example.com/echo"
        tool.parameters = None
        tool.status_message = None
        tool.is_mcp = False
        tool.transport = None
        tool.auth_required = False

        structured = self.mod.create_app_tool(tool, "app_1", "EchoApp")
        assert "echo (from EchoApp app)" in structured.description

    @pytest.mark.asyncio
    async def test_call_tool_endpoint_top_level_user_id(self):
        tool = ChatTool(
            name="ping",
            description="ping",
            endpoint="https://example.com/ping",
            method="POST",
        )
        structured = self.mod.create_app_tool(tool, "app_1", "PingApp")
        response = MagicMock(status_code=200)
        response.json.return_value = {"result": "pong"}
        client = AsyncMock()
        client.request = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        # Config with top-level user_id and NO configurable dict
        top_level_config = {"user_id": "top_level_uid_42"}

        with (
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
            patch.object(self.mod, "get_cached_user_geolocation", return_value=None),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=_allowing_breaker()),
            patch.object(self.mod, "record_app_webhook_success"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            self.mod.agent_config_context.set(top_level_config)
            result = await structured.ainvoke({})

        assert "pong" in result
        sent_body = client.request.call_args.kwargs["json"]
        assert sent_body["uid"] == "top_level_uid_42"

    @pytest.mark.asyncio
    async def test_call_tool_endpoint_missing_endpoint(self):
        tool = MagicMock(spec=ChatTool)
        tool.name = "broken_tool"
        tool.description = "broken"
        tool.endpoint = ""
        tool.parameters = None
        tool.status_message = None
        tool.is_mcp = False
        tool.auth_required = False

        structured = self.mod.create_app_tool(tool, "app_1", "BrokenApp")
        with patch.object(self.mod, "agent_config_context") as ctx_mock:
            ctx_mock.get.return_value = {"configurable": {"user_id": "u1"}}
            result = await structured.ainvoke({})
        assert "Endpoint not configured" in result

    @pytest.mark.asyncio
    async def test_call_tool_endpoint_none_method_defaults_to_post(self):
        tool = MagicMock(spec=ChatTool)
        tool.name = "no_method_tool"
        tool.description = "desc"
        tool.endpoint = "https://example.com/post_endpoint"
        tool.method = None
        tool.parameters = None
        tool.status_message = None
        tool.is_mcp = False
        tool.auth_required = False

        structured = self.mod.create_app_tool(tool, "app_1", "NoMethodApp")
        response = MagicMock(status_code=200)
        response.json.return_value = {"result": "success"}
        client = AsyncMock()
        client.request = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
            patch.object(self.mod, "get_cached_user_geolocation", return_value=None),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=_allowing_breaker()),
            patch.object(self.mod, "record_app_webhook_success"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            token = self.mod.agent_config_context.set({"configurable": {"user_id": "u_test"}})
            try:
                result = await structured.ainvoke({})
            finally:
                self.mod.agent_config_context.reset(token)

        assert "success" in result
        assert client.request.call_args.kwargs["method"] == "POST"

    def test_load_app_tools_none_enabled_apps(self):
        with patch.object(self.mod, "get_enabled_apps", return_value=None):
            tools = self.mod.load_app_tools("uid_test")
            assert tools == []

    def test_load_app_tools_handles_none_tools_in_list(self):
        mock_app = MagicMock(spec=App)
        mock_app.id = "app_test"
        mock_app.name = "Test App"
        valid_tool = ChatTool(
            name="valid_tool",
            description="valid",
            endpoint="https://example.com/valid",
        )
        mock_app.chat_tools = [None, valid_tool]
        mock_app.external_integration = None

        with (
            patch.object(self.mod, "get_enabled_apps", return_value=["app_test"]),
            patch.object(self.mod, "get_app_by_id_db", return_value={"id": "app_test"}),
            patch.object(self.mod, "App", return_value=mock_app),
        ):
            tools = self.mod.load_app_tools("uid_test")
            assert len(tools) == 1
            assert tools[0].name == "app_test_valid_tool"
