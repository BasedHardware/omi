"""
Hermetic Unit Tests for Perplexity Search and Web Retrieval Tools Resilience.
Tests parameter validation, defensive parsing of edge cases (empty choices, None messages, IndexError prevention).
"""

import os
import sys
import unittest
import asyncio
import importlib.util
from unittest.mock import AsyncMock, patch, MagicMock

# Stub external runtime dependencies
for mod_name in [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "httpx",
    "utils.generated_compute",
    "utils.executors",
    "utils.http_client",
    "utils.llm",
    "utils.llm.gateway_client",
    "utils.log_sanitizer",
    "utils.model_text",
]:
    if mod_name not in sys.modules:
        stub = MagicMock()
        if "tools" in mod_name:
            stub.tool = lambda fn: fn
        if "model_text" in mod_name:
            stub.UNTRUSTED_LEGEND = "[UNTRUSTED CONTENT]"
            stub.count_header = lambda name, shown, total, order: f"--- {name} ({shown}/{total}) ---"
            stub.generated = lambda label, text: f"<{label}>{text}</{label}>"
            stub.truncation_note = lambda shown, total, unit, how_to_get_more: f"... [{shown}/{total} {unit}]"
            stub.untrusted_block = lambda label, text: f"```\n{text}\n```"
        if "log_sanitizer" in mod_name:
            stub.sanitize = lambda s: str(s)
        sys.modules[mod_name] = stub


def _load_direct(name: str, rel_path: str):
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    full_path = os.path.join(base_dir, rel_path)
    spec = importlib.util.spec_from_file_location(name, full_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


perp_mod = _load_direct(
    "utils.retrieval.tools.perplexity_tools",
    "utils/retrieval/tools/perplexity_tools.py"
)
web_mod = _load_direct(
    "utils.retrieval.tools.web_tools",
    "utils/retrieval/tools/web_tools.py"
)

perplexity_web_search_tool = perp_mod.perplexity_web_search_tool
_extract_citations = perp_mod._extract_citations
_model_text = perp_mod._model_text
_format_perplexity_response = perp_mod._format_perplexity_response
fetch_url_tool = web_mod.fetch_url_tool


class TestPerplexityAndWebToolsResilience(unittest.TestCase):

    def test_perplexity_web_search_tool_empty_and_none_queries(self):
        """Verify perplexity_web_search_tool rejects None, empty, and whitespace queries without making API calls."""
        loop = asyncio.new_event_loop()
        try:
            # 1. query = None
            res_none = loop.run_until_complete(perplexity_web_search_tool(None))
            self.assertIn("Error: Search query cannot be empty", res_none)

            # 2. query = ""
            res_empty = loop.run_until_complete(perplexity_web_search_tool(""))
            self.assertIn("Error: Search query cannot be empty", res_empty)

            # 3. query = "    "
            res_ws = loop.run_until_complete(perplexity_web_search_tool("   \n\t  "))
            self.assertIn("Error: Search query cannot be empty", res_ws)

            # 4. query = 12345 (non-string)
            res_non_str = loop.run_until_complete(perplexity_web_search_tool(12345))
            self.assertIn("Error: Search query cannot be empty", res_non_str)
        finally:
            loop.close()

    def test_extract_citations_edge_cases(self):
        """Test _extract_citations defensively handles empty choices, None messages, and non-dict inputs."""
        # Case 1: result with empty choices list (previously caused IndexError: list index out of range)
        res_empty_choices = {"choices": []}
        citations = _extract_citations(res_empty_choices)
        self.assertEqual(citations, [])

        # Case 2: result with choices[0].message is None (previously caused AttributeError: 'NoneType' object has no attribute 'get')
        res_none_message = {"choices": [{"message": None}]}
        citations_none_msg = _extract_citations(res_none_message)
        self.assertEqual(citations_none_msg, [])

        # Case 3: result with non-dict choices[0]
        res_non_dict_choice = {"choices": ["invalid_string_choice"]}
        citations_non_dict = _extract_citations(res_non_dict_choice)
        self.assertEqual(citations_non_dict, [])

        # Case 4: non-dict result
        self.assertEqual(_extract_citations(None), [])
        self.assertEqual(_extract_citations([]), [])
        self.assertEqual(_extract_citations("not_a_dict"), [])

        # Case 5: valid nested citations
        res_valid_nested = {
            "choices": [{"message": {"citations": ["https://solana.com", "https://omi.me"]}}]
        }
        self.assertEqual(_extract_citations(res_valid_nested), ["https://solana.com", "https://omi.me"])

        # Case 6: top-level citations or search_results takes precedence
        res_top_level = {
            "citations": ["https://primary.org"],
            "choices": [{"message": {"citations": ["https://secondary.org"]}}]
        }
        self.assertEqual(_extract_citations(res_top_level), ["https://primary.org"])

    def test_model_text_edge_cases(self):
        """Test _model_text safely handles malformed response envelopes."""
        self.assertEqual(_model_text({}), "")
        self.assertEqual(_model_text({"choices": []}), "")
        self.assertEqual(_model_text({"choices": [{"message": None}]}), "")
        self.assertEqual(_model_text({"choices": [{"message": {"content": None}}]}), "")
        self.assertEqual(_model_text({"choices": [{"message": {"content": "Actual answer"}}]}), "Actual answer")
        self.assertEqual(_model_text(None), "")

    def test_format_perplexity_response_edge_cases(self):
        """Test _format_perplexity_response handles empty choices and None content without crashing."""
        # Empty choices returns standard unexpected format error
        err_out = _format_perplexity_response({"choices": []})
        self.assertIn("Error: Unexpected response format", err_out)

        # None message does not crash
        res_none_msg = {"choices": [{"message": None}]}
        formatted = _format_perplexity_response(res_none_msg)
        self.assertIn("Web Search Results", formatted)

        # Non-dict choice does not crash
        res_str_choice = {"choices": ["raw text choice"]}
        formatted_str = _format_perplexity_response(res_str_choice)
        self.assertIn("Web Search Results", formatted_str)

    def test_fetch_url_tool_guards(self):
        """Test fetch_url_tool input validation guards against empty, None, and whitespace URLs."""
        loop = asyncio.new_event_loop()
        try:
            # 1. url = None
            res_none = loop.run_until_complete(fetch_url_tool(None))
            self.assertIn("Error: URL cannot be empty", res_none)

            # 2. url = ""
            res_empty = loop.run_until_complete(fetch_url_tool(""))
            self.assertIn("Error: URL cannot be empty", res_empty)

            # 3. url = "   "
            res_ws = loop.run_until_complete(fetch_url_tool("   "))
            self.assertIn("Error: URL cannot be empty", res_ws)

            # 4. url with non-http scheme
            res_ftp = loop.run_until_complete(fetch_url_tool("ftp://files.example.com"))
            self.assertIn("Error: URL must start with http:// or https://", res_ftp)

            # 5. url with leading whitespace is trimmed and parsed cleanly
            with patch.object(web_mod, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = (200, "text/plain", "Hello world content")
                res_padded = loop.run_until_complete(fetch_url_tool("   https://example.com/page   "))
                self.assertIn("Content from https://example.com/page", res_padded)
                self.assertIn("Hello world content", res_padded)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
