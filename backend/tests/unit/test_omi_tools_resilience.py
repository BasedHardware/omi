"""Unit tests verifying input validation, fail-soft resilience, and context bounds in omi_tools.py."""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Stub packages before import to ensure hermetic execution without triggering __init__ cascades
for mod_name in ["utils", "utils.retrieval", "utils.retrieval.tools", "utils.app_integrations"]:
    if mod_name not in sys.modules:
        m = types.ModuleType(mod_name)
        if "." in mod_name:
            p, c = mod_name.rsplit(".", 1)
            if p in sys.modules:
                setattr(sys.modules[p], c, m)
        sys.modules[mod_name] = m

sys.modules["utils.app_integrations"].get_github_docs_content = MagicMock()

# Load result_bounds directly into sys.modules
rb_path = BACKEND_DIR / "utils" / "retrieval" / "tools" / "result_bounds.py"
rb_spec = importlib.util.spec_from_file_location("utils.retrieval.tools.result_bounds", str(rb_path))
rb_mod = importlib.util.module_from_spec(rb_spec)
sys.modules["utils.retrieval.tools.result_bounds"] = rb_mod
setattr(sys.modules["utils.retrieval.tools"], "result_bounds", rb_mod)
rb_spec.loader.exec_module(rb_mod)

# Load omi_tools directly
ot_path = BACKEND_DIR / "utils" / "retrieval" / "tools" / "omi_tools.py"
ot_spec = importlib.util.spec_from_file_location("utils.retrieval.tools.omi_tools", str(ot_path))
omi_tools = importlib.util.module_from_spec(ot_spec)
sys.modules["utils.retrieval.tools.omi_tools"] = omi_tools
setattr(sys.modules["utils.retrieval.tools"], "omi_tools", omi_tools)
ot_spec.loader.exec_module(omi_tools)

get_omi_product_info_tool = omi_tools.get_omi_product_info_tool


class TestOmiProductInfoToolResilience:
    def test_empty_or_whitespace_query_returns_error(self):
        assert "Error:" in get_omi_product_info_tool.invoke({"query": ""})
        assert "Error:" in get_omi_product_info_tool.invoke({"query": "   "})
        assert "Error:" in get_omi_product_info_tool.invoke({"query": None})

    def test_exception_in_docs_fetch_fails_soft(self, monkeypatch):
        def _mock_err():
            raise RuntimeError("GitHub API connection timeout")
        monkeypatch.setattr(omi_tools, "get_github_docs_content", _mock_err)
        result = get_omi_product_info_tool.invoke({"query": "How to set up device?"})
        assert "Error: the Omi product documentation could not be retrieved" in result

    def test_empty_docs_returns_unavailable_message(self, monkeypatch):
        monkeypatch.setattr(omi_tools, "get_github_docs_content", lambda: {})
        result = get_omi_product_info_tool.invoke({"query": "How to set up device?"})
        assert "No Omi product documentation is available right now" in result

    def test_non_dict_docs_returns_unavailable_message(self, monkeypatch):
        monkeypatch.setattr(omi_tools, "get_github_docs_content", lambda: "invalid non-dict content")
        result = get_omi_product_info_tool.invoke({"query": "How to set up device?"})
        assert "No Omi product documentation is available right now" in result

    def test_valid_docs_skips_none_content_and_formats(self, monkeypatch):
        mock_docs = {
            "device_setup.md": "Power on the device by pressing the side button.",
            "broken_section.md": None,
            "empty_section.md": "   ",
            "battery.md": "Battery life lasts approximately 24 hours.",
        }
        monkeypatch.setattr(omi_tools, "get_github_docs_content", lambda: mock_docs)
        result = get_omi_product_info_tool.invoke({"query": "What is the battery life?"})
        assert "## device_setup.md" in result
        assert "Power on the device by pressing the side button." in result
        assert "## battery.md" in result
        assert "Battery life lasts approximately 24 hours." in result
        assert "broken_section.md" not in result

    def test_oversized_docs_capped_and_bounded(self, monkeypatch):
        mock_docs = {
            "large_manual.md": "Omi hardware feature description. " * 3000,
        }
        monkeypatch.setattr(omi_tools, "get_github_docs_content", lambda: mock_docs)
        result = get_omi_product_info_tool.invoke({"query": "Explain all features"})
        assert "Omi/Friend Product Documentation:" in result
        # Bounded to MAX_RESULT_CHARS (60000) plus note
        assert len(result) <= 61000
        assert "more may exist" in result or "omitted" in result
