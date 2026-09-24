"""Tests verifying exception sanitization in app_tools.py.

Ensures that internal exception details (unexpected exception str(e), database secrets, etc.)
are not leaked to chat tool callers or plugin logs.
"""

import asyncio
import importlib
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Ensure httpx is stubbed if not installed
try:
    import httpx
except ImportError:
    httpx = _mod("httpx")

    class HTTPError(Exception):
        pass

    class TimeoutException(HTTPError):
        pass

    class ConnectError(HTTPError):
        pass

    class RequestError(HTTPError):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, request=None, response=None):
            super().__init__(message)
            self.response = response or MagicMock(status_code=500)

    class Response:
        status_code = 200
        text = ""

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

        async def request(self, *args, **kwargs):
            pass

    httpx.HTTPError = HTTPError
    httpx.TimeoutException = TimeoutException
    httpx.ConnectError = ConnectError
    httpx.RequestError = RequestError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.Response = Response
    httpx.AsyncClient = FakeAsyncClient
    httpx.Client = MagicMock

# Ensure pydantic is stubbed if not installed
try:
    import pydantic
except ImportError:
    pydantic = _mod("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def Field(*args, **kwargs):
        return None

    def create_model(name, **kwargs):
        return type(name, (BaseModel,), kwargs)

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.create_model = create_model

# Ensure langchain_core is stubbed if not installed
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")


class BaseTool:
    pass


class StructuredTool:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_lc_tools.BaseTool = BaseTool
_lc_tools.StructuredTool = StructuredTool

_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

for _p in [
    "database",
    "models",
    "utils",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

for _name, _attrs in {
    "database.apps": ["get_app_by_id_db"],
    "database.redis_db": ["get_cached_user_geolocation", "delete_app_cache_by_id", "get_enabled_apps"],
    "database.webhook_health": [
        "ACTION_REDIRECT_NOT_FOLLOWED",
        "record_app_webhook_failure",
        "record_app_webhook_success",
        "is_app_webhook_disabled",
        "disable_app_in_firestore",
        "ENDPOINT_CHAT_TOOL",
        "ENDPOINT_MCP_TOOL",
    ],
    "models.app": ["App", "ChatTool"],
    "utils.executors": ["db_executor", "run_blocking"],
    "utils.http_client": ["get_webhook_circuit_breaker"],
    "utils.mcp_client": ["call_mcp_tool"],
    "utils.notifications": ["send_notification"],
    "utils.retrieval.agentic": ["agent_config_context"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

_executors = sys.modules["utils.executors"]


async def _async_run_blocking(executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


_executors.run_blocking = _async_run_blocking

at = _load(
    "utils.retrieval.tools._app_tools_sanitization_test",
    "utils/retrieval/tools/app_tools.py",
)


class TestAppToolsSanitization(unittest.TestCase):
    def test_call_tool_endpoint_unexpected_exception_sanitized(self):
        async def _run():
            config = {"configurable": {"user_id": "u1"}}
            app_tool = MagicMock()
            app_tool.name = "test_tool"
            app_tool.endpoint = "https://example.com/api"
            app_tool.method = "POST"
            app_tool.auth_required = False

            with patch.object(at, "is_app_webhook_disabled", return_value=False), patch.object(
                at, "get_webhook_circuit_breaker"
            ) as mock_cb, patch("httpx.AsyncClient.request", side_effect=RuntimeError("internal app tool secret leak")):
                cb_instance = MagicMock()
                cb_instance.allow_request.return_value = True
                mock_cb.return_value = cb_instance

                result = await at._call_tool_endpoint(
                    kwargs={"arg": "val"},
                    config=config,
                    app_tool=app_tool,
                    app_id="app_123",
                )
                self.assertEqual("Error calling test_tool: An unexpected error occurred.", result)
                self.assertNotIn("internal app tool secret leak", result)
                self.assertNotIn("RuntimeError", result)

        asyncio.run(_run())

    def test_mcp_tool_unexpected_exception_sanitized(self):
        async def _run():
            app_tool = MagicMock()
            app_tool.name = "mcp_test_tool"
            app_tool.action = "test_action"
            app_tool.description = "Test MCP Tool"
            app_tool.is_mcp = True
            app_tool.transport = "sse"
            app_tool.parameters = None
            app_tool.status_message = None

            with patch.object(at, "is_app_webhook_disabled", return_value=False), patch.object(
                at, "get_webhook_circuit_breaker"
            ) as mock_cb, patch.object(
                at, "call_mcp_tool", side_effect=RuntimeError("internal mcp client crash with secret")
            ):
                cb_instance = MagicMock()
                cb_instance.allow_request.return_value = True
                mock_cb.return_value = cb_instance

                tool = at.create_app_tool(
                    app_tool,
                    "app_mcp_123",
                    "mcp_app",
                    mcp_server_url="https://mcp.example.com",
                )
                result = await tool.coroutine(arg="val")
                self.assertEqual("Error calling mcp_test_tool: An unexpected error occurred.", result)
                self.assertNotIn("internal mcp client crash with secret", result)
                self.assertNotIn("RuntimeError", result)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
