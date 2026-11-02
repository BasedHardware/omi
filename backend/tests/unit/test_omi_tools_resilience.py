"""Tests for context bounding, query validation, and non-dict resilience in omi_tools."""

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
    app_integrations_stub = ModuleType("utils.app_integrations")
    app_integrations_stub.get_github_docs_content = MagicMock(return_value={})

    fakes = {
        "utils": _empty_pkg("utils"),
        "utils.retrieval": _empty_pkg("utils.retrieval"),
        "utils.retrieval.tools": _empty_pkg("utils.retrieval.tools"),
        "utils.app_integrations": app_integrations_stub,
    }
    with stub_modules(fakes):
        # Keep pure rendering helpers real and registered for dataclass resolution.
        load_module_fresh("utils.model_text", str(BACKEND_DIR / "utils/model_text.py"))
        load_module_fresh(
            "utils.retrieval.tools.result_bounds", str(BACKEND_DIR / "utils/retrieval/tools/result_bounds.py")
        )
        module = load_module_fresh(
            "utils.retrieval.tools.omi_tools",
            os.path.join(str(BACKEND_DIR), "utils", "retrieval", "tools", "omi_tools.py"),
        )
        yield module


def _call(omi, query="How does the device connect to my phone?"):
    return omi.get_omi_product_info_tool.invoke({"query": query})


class TestOmiToolsResilience:
    def test_empty_or_whitespace_query_returns_error(self, omi):
        assert _call(omi, "").startswith("Error:")
        assert _call(omi, "   ").startswith("Error:")

    def test_none_query_returns_error(self, omi):
        assert _call(omi, None).startswith("Error:")

    def test_non_mapping_context_fails_soft(self, omi):
        with patch.object(omi, "get_github_docs_content", return_value=["unexpected", "list"]):
            out = _call(omi)
        assert "temporarily unavailable" in out
        assert "Omi/Friend Product Documentation" not in out

    def test_skips_none_section_content(self, omi):
        docs = {"docs/valid.md": "Battery lasts 2 days", "docs/empty.md": None}
        with patch.object(omi, "get_github_docs_content", return_value=docs):
            out = _call(omi)
        assert "Battery lasts 2 days" in out
        assert "## docs/empty.md" not in out

    def test_oversized_docs_are_bounded_to_max_result_chars(self, omi):
        huge_docs = {f"docs/page_{i}.md": "x" * 10000 for i in range(10)}
        with patch.object(omi, "get_github_docs_content", return_value=huge_docs):
            out = _call(omi)
        assert len(out) <= 60500
        assert "omitted data is not evidence of absence" in out

    def test_excessive_section_count_is_capped_with_truncation_note(self, omi):
        many_sections = {f"docs/sec_{i}.md": f"Section {i} body" for i in range(150)}
        with patch.object(omi, "get_github_docs_content", return_value=many_sections):
            out = _call(omi)
        assert "100 documentation sections" in out
        assert "## docs/sec_149.md" not in out
