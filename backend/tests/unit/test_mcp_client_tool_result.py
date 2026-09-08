"""Unit tests for utils.mcp_client._extract_tool_result.

Covers the MCP isError contract (#5124/#5130): tool execution failures are
reported in-band as result.isError=true, and must come back with an "Error"
prefix so app_tools.py failure detection (startswith 'Error'/'MCP error')
and the LLM both see the failure instead of treating it as success.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


for _mod in ['models.app', 'utils.log_sanitizer']:
    if _mod not in sys.modules:
        sys.modules[_mod] = _AutoMockModule(_mod)

from utils.mcp_client import _extract_tool_result


def test_success_text_content():
    resp = {"result": {"content": [{"type": "text", "text": "Page created"}]}}
    assert _extract_tool_result(resp) == "Page created"


def test_success_multiple_text_items():
    resp = {
        "result": {
            "content": [
                {"type": "text", "text": "line 1"},
                {"type": "text", "text": "line 2"},
            ]
        }
    }
    assert _extract_tool_result(resp) == "line 1\nline 2"


def test_is_error_with_text_gets_error_prefix():
    resp = {
        "result": {
            "isError": True,
            "content": [{"type": "text", "text": "insufficient permissions to create page"}],
        }
    }
    result = _extract_tool_result(resp)
    assert result.startswith("Error")
    assert "insufficient permissions to create page" in result


def test_is_error_without_content_gets_error_prefix():
    resp = {"result": {"isError": True, "content": []}}
    result = _extract_tool_result(resp)
    assert result.startswith("Error")


def test_is_error_false_is_treated_as_success():
    resp = {"result": {"isError": False, "content": [{"type": "text", "text": "ok"}]}}
    assert _extract_tool_result(resp) == "ok"


def test_jsonrpc_error_still_reported():
    resp = {"error": {"code": -32602, "message": "Invalid params"}}
    assert _extract_tool_result(resp) == "MCP error: Invalid params"


def test_empty_response():
    assert _extract_tool_result({}) == "No result returned from MCP tool."


def test_result_without_content_falls_back_to_str():
    resp = {"result": {"structuredContent": {"ok": True}}}
    assert _extract_tool_result(resp) == str({"structuredContent": {"ok": True}})


@pytest.mark.parametrize(
    "failure_resp",
    [
        {"result": {"isError": True, "content": [{"type": "text", "text": "API rate limited"}]}},
        {"result": {"isError": True, "content": []}},
        {"error": {"message": "boom"}},
    ],
)
def test_failures_match_app_tools_prefix_contract(failure_resp):
    # utils/retrieval/tools/app_tools.py records failures via
    # result.startswith('Error') or result.startswith('MCP error').
    result = _extract_tool_result(failure_resp)
    assert result.startswith("Error") or result.startswith("MCP error")
