"""Tests for fail-soft behavior of the Omi product info chat tool.

get_omi_product_info_tool fetches product docs from GitHub over the network. A fetch failure (the
helper makes synchronous httpx calls that raise on network errors) or an empty result must not break
the chat turn: the tool now fails soft with an "Error: ..." / "no docs" string like the other
retrieval tools, instead of letting the exception escape into the agent loop and aborting the answer.

``utils.retrieval.tools.omi_tools`` binds ``get_github_docs_content`` at import
(``from utils.app_integrations import get_github_docs_content``), and the real
``utils.app_integrations`` plus ``utils.retrieval.tools/__init__.py`` pull in heavy httpx + database
chains. The fake parent packages and ``utils.app_integrations`` must therefore be active before the
module is exec'd. This is the sanctioned Tier-2 "fake must precede import" case: see
backend/docs/test_isolation.md and testing/import_isolation.load_module_fresh.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _empty_pkg(name):
    pkg = ModuleType(name)
    pkg.__path__ = []  # type: ignore[attr-defined]
    return pkg


@pytest.fixture(scope="module")
def omi():
    """Load a fresh utils.retrieval.tools.omi_tools against stubbed parent packages + app_integrations.

    The real ``utils.retrieval.tools/__init__.py`` imports every sibling tool module (gmail,
    calendar, apple_health, ...) which each pull heavy database/httpx chains. Empty package stubs
    for the parents short-circuit that cascade; the ``utils.app_integrations`` fake stands in for
    the docs fetcher that the module binds at import. ``langchain_core`` is used for real so the
    ``@tool`` decorator runs.
    """
    app_integrations_stub = ModuleType("utils.app_integrations")
    app_integrations_stub.get_github_docs_content = MagicMock(return_value={})

    fakes = {
        "utils": _empty_pkg("utils"),
        "utils.retrieval": _empty_pkg("utils.retrieval"),
        "utils.retrieval.tools": _empty_pkg("utils.retrieval.tools"),
        "utils.app_integrations": app_integrations_stub,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.retrieval.tools.omi_tools",
            os.path.join(str(BACKEND_DIR), "utils", "retrieval", "tools", "omi_tools.py"),
        )
        yield module


def _call(omi, query="How does the device connect to my phone?"):
    return omi.get_omi_product_info_tool.invoke({"query": query})


class TestOmiProductInfoToolFailsSoft:
    def test_formats_docs_on_success(self, omi):
        docs = {"docs/setup.md": "Pair over Bluetooth", "docs/battery.md": "Lasts about two days"}
        with patch.object(omi, "get_github_docs_content", return_value=docs):
            out = _call(omi)
        assert "Omi/Friend Product Documentation" in out
        assert "Pair over Bluetooth" in out
        assert "Lasts about two days" in out

    def test_fails_soft_when_fetch_raises(self, omi):
        with patch.object(omi, "get_github_docs_content", side_effect=RuntimeError("github down")):
            out = _call(omi)
        # No exception escapes into the agent loop; the tool returns a soft error it can relay.
        assert out.startswith("Error:")
        assert "temporarily unavailable" in out

    def test_handles_empty_docs(self, omi):
        with patch.object(omi, "get_github_docs_content", return_value={}):
            out = _call(omi)
        # An empty fetch must not be dressed up as real documentation.
        assert "temporarily unavailable" in out
        assert "Omi/Friend Product Documentation" not in out

    def test_handles_none_docs(self, omi):
        with patch.object(omi, "get_github_docs_content", return_value=None):
            out = _call(omi)
        assert "temporarily unavailable" in out
