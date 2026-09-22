import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules


def _fake_tool(fn=None, *args, **kwargs):
    if fn is not None and callable(fn):
        return fn
    def decorator(func):
        return func
    return decorator


class TestWebToolsSanitization(unittest.TestCase):
    def setUp(self):
        tools_mock = AutoMockModule("langchain_core.tools")
        tools_mock.tool = _fake_tool

        self._stub_cm = stub_modules({
            "langchain_core": AutoMockModule("langchain_core"),
            "langchain_core.tools": tools_mock,
            "utils.http_client": AutoMockModule("utils.http_client"),
        })
        self._stub_cm.__enter__()
        tools_path = str(Path(backend_dir) / "utils" / "retrieval" / "tools" / "web_tools.py")
        self.web_tools = load_module_fresh("utils.retrieval.tools.web_tools", tools_path)

    def tearDown(self):
        self._stub_cm.__exit__(None, None, None)

    def test_fetch_url_tool_sanitizes_generic_exception(self):
        with patch.object(
            self.web_tools,
            "_fetch_page",
            AsyncMock(
                side_effect=RuntimeError(
                    "aiohttp.ClientConnectorError: Cannot connect to 10.0.1.5:8080 auth_token=super_secret"
                )
            ),
        ):
            res = asyncio.run(self.web_tools.fetch_url_tool("https://example.com/page"))
            self.assertEqual(res, "Error: Failed to fetch the URL.")
            self.assertNotIn("10.0.1.5", res)
            self.assertNotIn("8080", res)
            self.assertNotIn("super_secret", res)

    def test_fetch_url_tool_preserves_ssrf_value_error(self):
        with patch.object(
            self.web_tools,
            "_fetch_page",
            AsyncMock(side_effect=ValueError("URL resolves to a private or reserved address")),
        ):
            res = asyncio.run(self.web_tools.fetch_url_tool("https://127.0.0.1/admin"))
            self.assertEqual(res, "Error: URL resolves to a private or reserved address")

    def test_fetch_url_tool_validates_scheme(self):
        res = asyncio.run(self.web_tools.fetch_url_tool("ftp://example.com/file"))
        self.assertEqual(res, "Error: URL must start with http:// or https://")


if __name__ == "__main__":
    unittest.main()
