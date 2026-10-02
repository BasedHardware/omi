"""Regression tests for #13941: conversation date filters must fail closed.

``get_conversations`` used to swallow an unparseable ``start_date``/``end_date``
with a log line and then request the *unfiltered* conversation list, so a model
asking for "conversations since 01/01/2026" silently reasoned over the wrong
data. ``search_conversations`` forwarded raw strings, so the same input came
back as an opaque ``Omi API request failed (HTTP 400)`` with no hint about
which argument was wrong.

Both tools now raise ``ValueError("Invalid <field> '<value>'. Expected
YYYY-MM-DD.")`` before any request is made — the same error channel the
``query is required`` validation already uses to reach the MCP client.

Hermetic: runs on stdlib Python (``python3 mcp/tests/test_date_filters.py``)
by stubbing the ``mcp``/``pydantic``/``requests`` imports that are absent from
the manifest lane, and is also collected by the ``mcp/tests`` pytest suite
where the real dependencies exist. No network is ever touched: every test
installs a recording fake as ``server.requests``.
"""

import asyncio
import importlib.util
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

SERVER_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "mcp_server_omi" / "server.py"
)


def _fake_requests_module() -> types.ModuleType:
    module = types.ModuleType("requests")

    class HTTPError(Exception):
        def __init__(self, *args, response=None, **kwargs):
            super().__init__(*args)
            self.response = response

    class Response:
        status_code = 200

        def json(self):
            return {}

        def raise_for_status(self):
            return None

    def _blocked(*args, **kwargs):
        raise AssertionError("requests stub: network access is not allowed in tests")

    module.HTTPError = HTTPError
    module.Response = Response
    module.get = _blocked
    module.post = _blocked
    module.delete = _blocked
    module.patch = _blocked
    return module


def _fake_pydantic_module() -> types.ModuleType:
    module = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        @classmethod
        def model_json_schema(cls):
            return {}

    def Field(*args, **kwargs):
        return kwargs.get("default")

    module.BaseModel = BaseModel
    module.Field = Field
    return module


def _install_fake_mcp_modules() -> None:
    mcp_pkg = types.ModuleType("mcp")
    mcp_pkg.__path__ = []
    server_mod = types.ModuleType("mcp.server")
    stdio_mod = types.ModuleType("mcp.server.stdio")
    types_mod = types.ModuleType("mcp.types")

    class Server:
        def __init__(self, name, **kwargs):
            self.name = name
            self.kwargs = kwargs

        def list_tools(self):
            def decorator(fn):
                self.list_tools_handler = fn
                return fn

            return decorator

        def call_tool(self):
            def decorator(fn):
                self.call_tool_handler = fn
                return fn

            return decorator

    def stdio_server():
        raise AssertionError("mcp stub: stdio transport is not used in tests")

    class _Message:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    server_mod.Server = Server
    stdio_mod.stdio_server = stdio_server
    types_mod.TextContent = _Message
    types_mod.Tool = _Message
    server_mod.stdio = stdio_mod
    mcp_pkg.server = server_mod

    sys.modules["mcp"] = mcp_pkg
    sys.modules["mcp.server"] = server_mod
    sys.modules["mcp.server.stdio"] = stdio_mod
    sys.modules["mcp.types"] = types_mod


def _ensure_third_party_imports() -> None:
    """Stub only the third-party modules that are genuinely unavailable."""
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.modules["requests"] = _fake_requests_module()
    try:
        from pydantic import BaseModel, Field  # noqa: F401
    except ImportError:
        sys.modules["pydantic"] = _fake_pydantic_module()
    try:
        from mcp.server import Server  # noqa: F401
        from mcp.server.stdio import stdio_server  # noqa: F401
        from mcp.types import TextContent, Tool  # noqa: F401
    except ImportError:
        _install_fake_mcp_modules()


def _load_server_module():
    """Prefer the installed package (pytest/uv lane); fall back to the file."""
    try:
        from mcp_server_omi import server as server_module

        return server_module
    except ImportError:
        spec = importlib.util.spec_from_file_location(
            "mcp_server_omi_server_under_test", SERVER_PATH
        )
        server_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server_module)
        return server_module


_ensure_third_party_imports()
server = _load_server_module()


class _RecordingRequests:
    """Stand-in for the ``requests`` module bound inside server.py.

    Installed via ``mock.patch.object(server, "requests", ...)`` so no real
    network can be reached even when the genuine ``requests`` package is
    installed.
    """

    HTTPError = getattr(sys.modules.get("requests"), "HTTPError", Exception)
    Response = getattr(sys.modules.get("requests"), "Response", object)

    def __init__(self, payload=None):
        self.payload = [] if payload is None else payload
        self.get_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        response = mock.MagicMock()
        response.json.return_value = self.payload
        response.raise_for_status = mock.MagicMock()
        return response


def _run_tool(name, arguments):
    """Drive the production tool dispatcher the way ``call_tool`` does."""
    logger = logging.getLogger("test_date_filters")
    return asyncio.run(server._execute_tool(name, arguments, logger))


class GetConversationsDateFilterTests(unittest.TestCase):
    def test_unparseable_start_date_raises_named_error_before_request(self):
        fake_requests = _RecordingRequests()
        with (
            mock.patch.object(server, "requests", fake_requests),
            self.assertRaises(ValueError) as caught,
        ):
            server.get_conversations(
                logging.getLogger("test"), "key", start_date="01/01/2026"
            )
        self.assertEqual(
            str(caught.exception),
            "Invalid start_date '01/01/2026'. Expected YYYY-MM-DD.",
        )
        self.assertEqual(fake_requests.get_calls, [])

    def test_unparseable_end_date_raises_named_error_before_request(self):
        fake_requests = _RecordingRequests()
        with (
            mock.patch.object(server, "requests", fake_requests),
            self.assertRaises(ValueError) as caught,
        ):
            server.get_conversations(
                logging.getLogger("test"), "key", end_date="yesterday"
            )
        self.assertEqual(
            str(caught.exception), "Invalid end_date 'yesterday'. Expected YYYY-MM-DD."
        )
        self.assertEqual(fake_requests.get_calls, [])

    def test_valid_dates_keep_start_and_end_of_day_bounds(self):
        fake_requests = _RecordingRequests(payload=[{"id": "c1"}])
        with mock.patch.object(server, "requests", fake_requests):
            result = server.get_conversations(
                logging.getLogger("test"),
                "key",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )
        params = fake_requests.get_calls[0]["params"]
        self.assertEqual(params["start_date"], "2026-01-01T00:00:00")
        self.assertEqual(params["end_date"], "2026-01-31T23:59:59")
        self.assertEqual(result, [{"id": "c1"}])

    def test_no_dates_sends_no_date_params(self):
        fake_requests = _RecordingRequests()
        with mock.patch.object(server, "requests", fake_requests):
            server.get_conversations(logging.getLogger("test"), "key")
        params = fake_requests.get_calls[0]["params"]
        self.assertNotIn("start_date", params)
        self.assertNotIn("end_date", params)


class SearchConversationsDateFilterTests(unittest.TestCase):
    def test_unparseable_start_date_raises_named_error_before_request(self):
        fake_requests = _RecordingRequests()
        with (
            mock.patch.object(server, "requests", fake_requests),
            self.assertRaises(ValueError) as caught,
        ):
            server.search_conversations(
                logging.getLogger("test"),
                "key",
                query="standup",
                start_date="01/01/2026",
            )
        self.assertEqual(
            str(caught.exception),
            "Invalid start_date '01/01/2026'. Expected YYYY-MM-DD.",
        )
        self.assertEqual(fake_requests.get_calls, [])

    def test_unparseable_end_date_raises_named_error_before_request(self):
        fake_requests = _RecordingRequests()
        with (
            mock.patch.object(server, "requests", fake_requests),
            self.assertRaises(ValueError) as caught,
        ):
            server.search_conversations(
                logging.getLogger("test"),
                "key",
                query="standup",
                end_date="last Friday",
            )
        self.assertEqual(
            str(caught.exception),
            "Invalid end_date 'last Friday'. Expected YYYY-MM-DD.",
        )
        self.assertEqual(fake_requests.get_calls, [])

    def test_valid_dates_are_forwarded_as_yyyy_mm_dd(self):
        fake_requests = _RecordingRequests()
        with mock.patch.object(server, "requests", fake_requests):
            server.search_conversations(
                logging.getLogger("test"),
                "key",
                query="standup",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )
        params = fake_requests.get_calls[0]["params"]
        self.assertEqual(params["start_date"], "2026-01-01")
        self.assertEqual(params["end_date"], "2026-01-31")


class ToolDispatchDateFilterTests(unittest.TestCase):
    """The error must travel the same path ``call_tool`` uses to reach the MCP client."""

    def test_get_conversations_tool_surfaces_named_field_error(self):
        fake_requests = _RecordingRequests()
        with (
            mock.patch.object(server, "requests", fake_requests),
            self.assertRaises(ValueError) as caught,
        ):
            _run_tool(
                server.OmiTools.GET_CONVERSATIONS,
                {"api_key": "key", "start_date": "01/01/2026"},
            )
        self.assertIn("start_date", str(caught.exception))
        self.assertIn("01/01/2026", str(caught.exception))
        self.assertEqual(fake_requests.get_calls, [])

    def test_search_conversations_tool_surfaces_named_field_error(self):
        fake_requests = _RecordingRequests()
        with (
            mock.patch.object(server, "requests", fake_requests),
            self.assertRaises(ValueError) as caught,
        ):
            _run_tool(
                server.OmiTools.SEARCH_CONVERSATIONS,
                {"api_key": "key", "query": "standup", "end_date": "tomorrow"},
            )
        self.assertIn("end_date", str(caught.exception))
        self.assertIn("tomorrow", str(caught.exception))
        self.assertEqual(fake_requests.get_calls, [])


if __name__ == "__main__":
    unittest.main()
