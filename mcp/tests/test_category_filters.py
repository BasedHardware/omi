"""Regression tests: conversation/memory category filters must fail closed.

``_parse_categories`` used to log and drop any value it could not map onto the
tool's enum. Both dispatchers only forward the filter when the parsed list is
non-empty, so a filter whose values were *all* unknown vanished: ``get_memories``
with ``categories=["finance"]`` (a conversation category -- ``MemoryCategory``
has no such member) issued an unfiltered request and handed the model every
memory the user has, with nothing in the response marking the filter as dropped.

That is the silent-widening failure #13941 already removed from the date filters
in the same file: "a date filter that cannot be parsed must surface as an error
to the model instead of being silently dropped (which would return unfiltered
results)". Categories now raise ``ValueError("Invalid category '<value>'.
Expected one of: ...")`` before any request is made, through the same error
channel as the date and ``query is required`` validations.

Hermetic: runs on stdlib Python (``python3 mcp/tests/test_category_filters.py``)
by stubbing the ``mcp``/``pydantic``/``requests`` imports that are absent from
the manifest lane, and is also collected by the ``mcp/tests`` pytest suite where
the real dependencies exist. The harness below intentionally mirrors
``test_date_filters.py`` rather than importing it, so each manifest check stays a
standalone file. No network is ever touched.
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
    """Stand-in for the ``requests`` module bound inside server.py."""

    HTTPError = getattr(sys.modules.get("requests"), "HTTPError", Exception)

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
    logger = logging.getLogger("test_category_filters")
    return asyncio.run(server._execute_tool(name, arguments, logger))


class ParseCategoriesTests(unittest.TestCase):
    def test_unknown_category_raises_naming_the_value(self):
        logger = logging.getLogger("test")
        with self.assertRaises(ValueError) as caught:
            server._parse_categories(["finance"], server.MemoryCategory, logger)
        message = str(caught.exception)
        self.assertIn("Invalid category 'finance'", message)
        # The model can only retry correctly if the error carries the vocabulary.
        self.assertIn("hobbies", message)

    def test_unknown_category_is_rejected_even_beside_valid_ones(self):
        # A partially parsed filter is still the wrong filter: the model asked
        # for two categories and would silently receive one.
        logger = logging.getLogger("test")
        with self.assertRaises(ValueError) as caught:
            server._parse_categories(
                ["work", "not-a-real-category"], server.ConversationCategory, logger
            )
        self.assertIn("Invalid category 'not-a-real-category'", str(caught.exception))

    def test_valid_categories_still_parse_to_enum_members(self):
        logger = logging.getLogger("test")
        result = server._parse_categories(
            ["work", "travel"], server.ConversationCategory, logger
        )
        self.assertEqual(
            result, [server.ConversationCategory.work, server.ConversationCategory.travel]
        )

    def test_empty_list_is_not_an_error(self):
        logger = logging.getLogger("test")
        self.assertEqual(
            server._parse_categories([], server.ConversationCategory, logger), []
        )

    def test_non_list_still_raises(self):
        logger = logging.getLogger("test")
        with self.assertRaises(ValueError):
            server._parse_categories("work", server.ConversationCategory, logger)


class DispatcherCategoryFilterTests(unittest.TestCase):
    """The behaviour that actually reached the user: an unfiltered result set."""

    def test_get_memories_does_not_fall_back_to_the_unfiltered_list(self):
        fake_requests = _RecordingRequests(payload=[{"id": "m1"}, {"id": "m2"}])
        with (
            mock.patch.object(server, "requests", fake_requests),
            self.assertRaises(ValueError) as caught,
        ):
            _run_tool("get_memories", {"api_key": "key", "categories": ["finance"]})
        self.assertIn("Invalid category 'finance'", str(caught.exception))
        self.assertEqual(fake_requests.get_calls, [])

    def test_get_conversations_does_not_fall_back_to_the_unfiltered_list(self):
        fake_requests = _RecordingRequests(payload=[{"id": "c1"}])
        with (
            mock.patch.object(server, "requests", fake_requests),
            self.assertRaises(ValueError) as caught,
        ):
            _run_tool(
                "get_conversations", {"api_key": "key", "categories": ["groceries"]}
            )
        self.assertIn("Invalid category 'groceries'", str(caught.exception))
        self.assertEqual(fake_requests.get_calls, [])

    def test_valid_category_filter_is_still_forwarded(self):
        fake_requests = _RecordingRequests(payload=[{"id": "c1"}])
        with mock.patch.object(server, "requests", fake_requests):
            _run_tool("get_conversations", {"api_key": "key", "categories": ["work"]})
        self.assertEqual(len(fake_requests.get_calls), 1)
        self.assertEqual(fake_requests.get_calls[0]["params"]["categories"], "work")


if __name__ == "__main__":
    unittest.main(verbosity=2)
