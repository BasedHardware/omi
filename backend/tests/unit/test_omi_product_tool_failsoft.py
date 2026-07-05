"""Tests for fail-soft behavior of the Omi product info chat tool.

get_omi_product_info_tool fetches product docs from GitHub over the network. A fetch failure (the
helper makes synchronous httpx calls that raise on network errors) or an empty result must not break
the chat turn: the tool now fails soft with an "Error: ..." / "no docs" string like the other
retrieval tools, instead of letting the exception escape into the agent loop and aborting the answer.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub the heavy leaf utils.app_integrations (httpx + database); langchain_core is used for real (the
# @tool decorator needs it). The docs fetch is mocked per test.
_pkg("utils")
_pkg("utils.retrieval")
_pkg("utils.retrieval.tools")
_app_integrations = types.ModuleType("utils.app_integrations")
_app_integrations.get_github_docs_content = MagicMock(return_value={})
sys.modules["utils.app_integrations"] = _app_integrations

omi = _load("utils.retrieval.tools.omi_tools", "utils/retrieval/tools/omi_tools.py")


def _call(query="How does the device connect to my phone?"):
    return omi.get_omi_product_info_tool.invoke({"query": query})


class TestOmiProductInfoToolFailsSoft:
    def test_formats_docs_on_success(self):
        docs = {"docs/setup.md": "Pair over Bluetooth", "docs/battery.md": "Lasts about two days"}
        with patch.object(omi, "get_github_docs_content", return_value=docs):
            out = _call()
        assert "Omi/Friend Product Documentation" in out
        assert "Pair over Bluetooth" in out
        assert "Lasts about two days" in out

    def test_fails_soft_when_fetch_raises(self):
        with patch.object(omi, "get_github_docs_content", side_effect=RuntimeError("github down")):
            out = _call()
        # No exception escapes into the agent loop; the tool returns a soft error it can relay.
        assert out.startswith("Error:")
        assert "temporarily unavailable" in out

    def test_handles_empty_docs(self):
        with patch.object(omi, "get_github_docs_content", return_value={}):
            out = _call()
        # An empty fetch must not be dressed up as real documentation.
        assert "temporarily unavailable" in out
        assert "Omi/Friend Product Documentation" not in out

    def test_handles_none_docs(self):
        with patch.object(omi, "get_github_docs_content", return_value=None):
            out = _call()
        assert "temporarily unavailable" in out
