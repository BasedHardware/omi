import asyncio
import os
import sys
from types import ModuleType
from unittest.mock import patch, MagicMock
import unittest
from importlib.machinery import ModuleSpec

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from testing.import_isolation import AutoMockModule

class AutoStubLoader:
    def create_module(self, spec):
        m = AutoMockModule(spec.name)
        if spec.name == "langchain_core.tools":
            def tool_dec(fn=None):
                if fn is None:
                    return lambda f: f
                fn.ainvoke = lambda args: fn(**args)
                return fn
            m.tool = tool_dec
        return m

    def exec_module(self, module):
        pass

class AutoStubFinder:
    _STUB_PREFIXES = (
        "google",
        "database",
        "firebase",
        "pinecone",
        "typesense",
        "stripe",
        "anthropic",
        "openai",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "httpx",
        "pydantic",
        "fastapi",
        "pytz",
        "prometheus_client",
        "tiktoken",
    )

    def find_spec(self, fullname, path, target=None):
        if any(fullname == p or fullname.startswith(p + ".") for p in self._STUB_PREFIXES):
            spec = ModuleSpec(fullname, AutoStubLoader())
            spec.submodule_search_locations = []
            return spec
        return None

sys.meta_path.insert(0, AutoStubFinder())

# Pre-populate utils.retrieval.tools package without running __init__.py
tools_dir = os.path.join(backend_dir, "utils", "retrieval", "tools")
tools_pkg = ModuleType("utils.retrieval.tools")
tools_pkg.__path__ = [tools_dir]
tools_pkg.__file__ = os.path.join(tools_dir, "__init__.py")
sys.modules["utils.retrieval.tools"] = tools_pkg

from utils.retrieval.tools.web_tools import fetch_url_tool
from utils.retrieval.tools.perplexity_tools import perplexity_web_search_tool
from utils.retrieval.tools.calendar_tools import (
    create_calendar_event_tool,
    delete_calendar_event_tool,
    update_calendar_event_tool,
)


class TestRetrievalToolsInputGuards(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_url_tool_none_and_empty_guards(self):
        # Ensure None or non-string does not raise AttributeError
        res_none = await fetch_url_tool.ainvoke({"url": None})
        self.assertIn("Error: URL is required and cannot be empty.", res_none)

        res_empty = await fetch_url_tool.ainvoke({"url": "   "})
        self.assertIn("Error: URL is required and cannot be empty.", res_empty)

        res_num = await fetch_url_tool.ainvoke({"url": 12345})
        self.assertIn("Error: URL is required and cannot be empty.", res_num)

        res_invalid_scheme = await fetch_url_tool.ainvoke({"url": "ftp://example.com"})
        self.assertIn("Error: URL must start with http:// or https://", res_invalid_scheme)

    async def test_perplexity_web_search_tool_none_and_empty_guards(self):
        # Ensure None or non-string does not raise TypeError or proceed to API
        res_none = await perplexity_web_search_tool.ainvoke({"query": None})
        self.assertIn("Error: query is required and cannot be empty.", res_none)

        res_empty = await perplexity_web_search_tool.ainvoke({"query": "   "})
        self.assertIn("Error: query is required and cannot be empty.", res_empty)

        res_num = await perplexity_web_search_tool.ainvoke({"query": 9999})
        self.assertIn("Error: query is required and cannot be empty.", res_num)

    @patch("utils.retrieval.tools.calendar_tools.run_blocking")
    async def test_create_calendar_event_tool_input_guards(self, mock_run_blocking):
        mock_run_blocking.return_value = ("test-uid", {"id": "int-1"}, "test-token", None)

        # Empty/None title
        res_title_none = await create_calendar_event_tool.ainvoke({
            "title": None,
            "start_time": "2026-10-28T10:00:00Z",
            "end_time": "2026-10-28T11:00:00Z",
        })
        self.assertIn("Error: title is required and cannot be empty.", res_title_none)

        res_title_empty = await create_calendar_event_tool.ainvoke({
            "title": "   ",
            "start_time": "2026-10-28T10:00:00Z",
            "end_time": "2026-10-28T11:00:00Z",
        })
        self.assertIn("Error: title is required and cannot be empty.", res_title_empty)

        # Empty/None start_time
        res_start_none = await create_calendar_event_tool.ainvoke({
            "title": "Sync Meeting",
            "start_time": None,
            "end_time": "2026-10-28T11:00:00Z",
        })
        self.assertIn("Error: start_time is required in format", res_start_none)

        # Empty/None end_time
        res_end_none = await create_calendar_event_tool.ainvoke({
            "title": "Sync Meeting",
            "start_time": "2026-10-28T10:00:00Z",
            "end_time": None,
        })
        self.assertIn("Error: end_time is required in format", res_end_none)

    @patch("utils.retrieval.tools.calendar_tools.run_blocking")
    async def test_delete_calendar_event_tool_whitespace_sanitization(self, mock_run_blocking):
        mock_run_blocking.return_value = ("test-uid", {"id": "int-1"}, "test-token", None)

        # When event_id is only whitespace and no other fields provided
        res = await delete_calendar_event_tool.ainvoke({
            "event_id": "   ",
            "event_title": None,
            "start_date": None,
        })
        self.assertIn("Error: Please provide either event_id, event_title, or start_date", res)

    @patch("utils.retrieval.tools.calendar_tools.run_blocking")
    async def test_update_calendar_event_tool_whitespace_sanitization(self, mock_run_blocking):
        mock_run_blocking.return_value = ("test-uid", {"id": "int-1"}, "test-token", None)

        # When both event_id and event_title are whitespace
        res = await update_calendar_event_tool.ainvoke({
            "event_id": "   ",
            "event_title": "   ",
        })
        self.assertIn("Error: Please provide either event_id or event_title to identify which event to update.", res)


if __name__ == "__main__":
    unittest.main()
