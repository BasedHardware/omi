"""Regression: optional tool parameters the model did not supply must not reach the app as null.

utils.retrieval.tools.app_tools builds each app tool's argument model from the manifest schema
with every non-required parameter typed Optional and defaulted to None. langchain forwards those
defaulted fields to the coroutine as explicit None, and both wrappers sent the kwargs through
verbatim, so "what is the bitcoin price?" reached a plugin as {"coin_ids": "bitcoin",
"vs_currency": null}. Plugins that type the parameter as string or integer reject the null and
every ordinary call fails validation. The wire body must carry only the arguments that were
actually supplied.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import utils.retrieval.tools.app_tools as app_tools
from models.app import ChatTool

PARAMETERS = {
    "properties": {
        "coin_ids": {"type": "string", "description": "coin ids"},
        "vs_currency": {"type": "string", "description": "currency", "default": "usd"},
        "limit": {"type": "integer", "description": "rows", "default": 5},
        "verbose": {"type": "boolean", "description": "verbose"},
    },
    "required": ["coin_ids"],
}
CONFIG = {"configurable": {"user_id": "uid-1"}}


def _allowing_breaker():
    breaker = MagicMock()
    breaker.allow_request.return_value = True
    return breaker


class TestHttpToolArguments:
    mod = app_tools

    async def _invoke(self, tool_input):
        tool = ChatTool(
            name="get_crypto_price", description="d", endpoint="https://app.example/tools/price", parameters=PARAMETERS
        )
        structured = self.mod.create_app_tool(tool, "app-1", "Crypto")
        response = MagicMock(status_code=200)
        response.json.return_value = {"result": "ok"}
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
            token = self.mod.agent_config_context.set(CONFIG)
            try:
                result = await structured.ainvoke(tool_input)
            finally:
                self.mod.agent_config_context.reset(token)
        assert result == "ok"
        return client.request.call_args.kwargs["json"]

    @pytest.mark.asyncio
    async def test_omitted_optionals_are_absent_from_the_body(self):
        body = await self._invoke({"coin_ids": "bitcoin"})
        assert body == {"coin_ids": "bitcoin", "uid": "uid-1", "app_id": "app-1", "tool_name": "get_crypto_price"}

    @pytest.mark.asyncio
    async def test_supplied_optionals_are_kept_including_falsy_values(self):
        body = await self._invoke({"coin_ids": "bitcoin", "vs_currency": "eur", "limit": 0, "verbose": False})
        assert body["vs_currency"] == "eur"
        assert body["limit"] == 0
        assert body["verbose"] is False


class TestMcpToolArguments:
    mod = app_tools

    @pytest.mark.asyncio
    async def test_omitted_optionals_are_absent_from_mcp_arguments(self):
        tool = ChatTool(name="search", description="d", endpoint="", is_mcp=True, parameters=PARAMETERS)
        structured = self.mod.create_app_tool(tool, "app-mcp", "Mcp", mcp_server_url="https://mcp.example")
        with (
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=_allowing_breaker()),
            patch.object(self.mod, "call_mcp_tool", new_callable=AsyncMock, return_value="found") as call,
            patch.object(self.mod, "record_app_webhook_success"),
        ):
            result = await structured.ainvoke({"coin_ids": "bitcoin", "limit": 3})
        assert result == "found"
        assert call.call_args.args[2] == {"coin_ids": "bitcoin", "limit": 3}
