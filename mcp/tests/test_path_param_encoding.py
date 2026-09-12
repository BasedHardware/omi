"""Hermetic regression: resource ids must be URL-encoded in request paths.

delete_memory, edit_memory, and get_conversation_by_id interpolated the raw
tool argument into the URL path, so an id containing '/', '?', '#', or '%'
rewrote the request target - hitting a different endpoint or a 404.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


def load_server():
    """Import server.py with the mcp/pydantic/requests boundaries stubbed."""
    mcp = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_server.Server = Mock
    mcp_stdio = types.ModuleType("mcp.server.stdio")
    mcp_stdio.stdio_server = Mock()
    mcp_types = types.ModuleType("mcp.types")
    mcp_types.TextContent = Mock
    mcp_types.Tool = Mock
    mcp.server = mcp_server
    mcp_server.stdio = mcp_stdio

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        pass

    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda **kwargs: kwargs.get("default")

    requests = types.ModuleType("requests")
    requests.Response = object
    requests.HTTPError = Exception
    requests.get = requests.post = requests.delete = requests.patch = Mock()

    modules = {
        "mcp": mcp,
        "mcp.server": mcp_server,
        "mcp.server.stdio": mcp_stdio,
        "mcp.types": mcp_types,
        "pydantic": pydantic,
        "requests": requests,
    }
    originals = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        spec = importlib.util.spec_from_file_location(
            "server_under_test",
            Path(__file__).resolve().parents[1] / "src" / "mcp_server_omi" / "server.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
    return module


class PathParamEncodingTests(unittest.TestCase):
    def setUp(self):
        self.server = load_server()
        self.captured = {}

        def fake_response(url=None, **kwargs):
            self.captured["url"] = url
            response = Mock()
            response.status_code = 200
            response.json.return_value = {}
            return response

        self.fake_response = fake_response

    def url_of(self, method, operation):
        with patch.object(self.server.requests, method, side_effect=self.fake_response):
            operation()
        return self.captured["url"]

    def test_delete_memory_encodes_id(self):
        url = self.url_of(
            "delete", lambda: self.server.delete_memory("k", "a/b?c#d")
        )
        self.assertIn("memories/a%2Fb%3Fc%23d", url)
        self.assertNotIn("memories/a/b", url)

    def test_edit_memory_encodes_id(self):
        url = self.url_of(
            "patch", lambda: self.server.edit_memory("k", "a/b", "content")
        )
        self.assertIn("memories/a%2Fb", url)

    def test_get_conversation_encodes_id(self):
        url = self.url_of(
            "get", lambda: self.server.get_conversation_by_id("k", "x/y?z")
        )
        self.assertIn("conversations/x%2Fy%3Fz", url)

    def test_normal_ids_pass_through(self):
        url = self.url_of(
            "delete", lambda: self.server.delete_memory("k", "abc-123_DEF")
        )
        self.assertIn("memories/abc-123_DEF", url)


if __name__ == "__main__":
    unittest.main()
