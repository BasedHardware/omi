"""Tests verifying exception sanitization in perplexity_tools.py.

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
from unittest.mock import AsyncMock, MagicMock, patch

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


# Ensure langchain_core is stubbed if not installed
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")
def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn
    def dec(func):
        func.func = func
        return func
    return dec
_lc_tools.tool = _tool_decorator

for _p in [
    "utils",
    "utils.llm",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

for _name, _attrs in {
    "utils.http_client": ["get_webhook_client"],
    "utils.llm.gateway_client": ["feature_auto_lane_id", "get_llm_gateway_base_url", "llm_gateway_headers"],
    "utils.log_sanitizer": ["sanitize"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

_llm_gateway = sys.modules["utils.llm.gateway_client"]
_llm_gateway.feature_auto_lane_id = lambda name: "test-lane"
_llm_gateway.get_llm_gateway_base_url = lambda: "http://test-gateway"
_llm_gateway.llm_gateway_headers = lambda: {}

_log_sanitizer = sys.modules["utils.log_sanitizer"]
_log_sanitizer.sanitize = lambda s: str(s)

pt = _load(
    "utils.retrieval.tools._perplexity_tools_sanitization_test",
    "utils/retrieval/tools/perplexity_tools.py",
)


class TestPerplexityToolsSanitization(unittest.TestCase):
    def test_perplexity_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(pt, "_post_gateway_chat_completion", side_effect=RuntimeError("internal gateway credentials secret")):
                result = await pt._perplexity_gateway_search("test query")
                self.assertEqual("Error: An unexpected error occurred while searching. Please try again later.", result)
                self.assertNotIn("internal gateway credentials secret", result)
                self.assertNotIn("RuntimeError", result)

        asyncio.run(_run())

    def test_perplexity_unexpected_response_format_sanitized(self):
        async def _run():
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"invalid_structure": 123}
            with patch.object(pt, "_post_gateway_chat_completion", return_value=mock_response):
                result = await pt._perplexity_gateway_search("test query")
                self.assertEqual("Error: Unexpected response format from Perplexity API", result)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
