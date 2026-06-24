"""
Unit test for get_omi_product_info_tool fail-soft behavior.

The retrieval agent tool `get_omi_product_info_tool` fetches product
documentation via `get_github_docs_content()` and formats it. Before the fix
this call was unguarded: if the docs fetch raised (e.g. an httpx transport
error) or returned a non-dict / empty value, the tool propagated the exception
(or crashed on `.items()`), taking down the agent turn instead of degrading
gracefully like its sibling retrieval tools.

This test loads the REAL `omi_tools.py` module from file (so the actual,
fixed function body executes) while stubbing its heavy dependency
`utils.app_integrations` and providing a lightweight, invokable `@tool`
decorator. It then:

  1. patches `get_github_docs_content` to raise -> asserts a string starting
     with "Error" is returned (fail-soft) instead of the exception propagating.
  2. patches `get_github_docs_content` to return {} (empty) -> asserts an
     "Error"/unavailable string is returned instead of an empty payload.

RED (before fix): the exception propagates out of invoke() -> test raises.
GREEN (after fix): a graceful "Error: ..." string is returned.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Lightweight, invokable @tool stand-in.
#
# The global Python 3.13 env ships an incompatible langchain_core/langsmith
# pair (langchain_core 1.x expects langsmith.RunTree, which the installed
# langsmith does not export), so the real `@tool` decorator cannot import.
# We substitute a tiny decorator that preserves the contract this test relies
# on: `.invoke({...})` runs the wrapped function body with the dict expanded
# as kwargs, and `.func` exposes the underlying callable. The REAL function
# body from omi_tools.py still executes, so the fail-soft behavior is exercised
# for real.
# ---------------------------------------------------------------------------
class _FakeTool:
    def __init__(self, func):
        self.func = func
        self.name = getattr(func, "__name__", "tool")
        self.description = (func.__doc__ or "").strip()

    def invoke(self, input):
        if isinstance(input, dict):
            return self.func(**input)
        return self.func(input)


def _tool_decorator(*dargs, **dkwargs):
    # Support both `@tool` and `@tool(...)` usage.
    if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
        return _FakeTool(dargs[0])

    def _wrap(func):
        return _FakeTool(func)

    return _wrap


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _load_omi_tools():
    """Load the real omi_tools.py with deps stubbed, returning the module."""
    # langchain_core.tools.tool -> lightweight invokable decorator.
    lc = _stub_package("langchain_core")
    lc_tools = _stub_package("langchain_core.tools")
    lc_tools.tool = _tool_decorator
    lc.tools = lc_tools

    # utils.app_integrations.get_github_docs_content -> patchable MagicMock.
    utils_pkg = _stub_package("utils")
    app_integrations = _stub_module("utils.app_integrations")
    app_integrations.get_github_docs_content = MagicMock(return_value={"Overview": "Omi is a wearable."})
    utils_pkg.app_integrations = app_integrations

    target = BACKEND_DIR / "utils" / "retrieval" / "tools" / "omi_tools.py"
    spec = importlib.util.spec_from_file_location("omi_tools_under_test", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["omi_tools_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


_MOD = _load_omi_tools()


def test_returns_error_string_when_docs_fetch_raises():
    """Fail-soft: a raising get_github_docs_content yields an 'Error' string, not an exception."""

    class _Boom(Exception):
        pass

    with patch.object(_MOD, "get_github_docs_content", side_effect=_Boom("connect failed")):
        result = _MOD.get_omi_product_info_tool.invoke({"query": "How does the device connect?"})

    assert isinstance(result, str)
    assert result.startswith("Error"), f"expected a fail-soft 'Error...' string, got: {result!r}"


def test_returns_error_string_when_docs_unavailable_empty():
    """A non-dict / empty docs payload degrades to an 'Error'/unavailable string instead of empty output."""
    with patch.object(_MOD, "get_github_docs_content", return_value={}):
        result = _MOD.get_omi_product_info_tool.invoke({"query": "What is the battery life?"})

    assert isinstance(result, str)
    assert result.startswith("Error"), f"expected a fail-soft 'Error...' string for empty docs, got: {result!r}"


def test_happy_path_still_returns_documentation():
    """When docs load normally the tool still returns the formatted documentation string."""
    with patch.object(
        _MOD,
        "get_github_docs_content",
        return_value={"Setup": "Pair via Bluetooth.", "Battery": "Up to 24h."},
    ):
        result = _MOD.get_omi_product_info_tool.invoke({"query": "How do I set up Omi?"})

    assert isinstance(result, str)
    assert not result.startswith("Error")
    assert "Pair via Bluetooth." in result
    assert "Up to 24h." in result
