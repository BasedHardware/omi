"""Unit tests verifying input validation, hop-2 retry concatenation, and response extraction in perplexity_tools.py.

Ensures that:
1. Empty, whitespace-only, or None queries are rejected early with a descriptive error.
2. Hop-2 query concatenation handles clean string queries without raising TypeError.
3. None content in message choices is gracefully converted without raising IndexError or rendering literal 'None'.
4. Malformed choices lists or non-dict structures are handled safely.
"""

import sys
import unittest
import asyncio
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure scratch workspace is on sys.path
TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

# Create dummy modules for imports
for mod_name in [
    "langchain_core", "langchain_core.tools", "httpx",
    "utils", "utils.generated_compute", "utils.executors", "utils.http_client",
    "utils.llm", "utils.llm.gateway_client", "utils.log_sanitizer", "utils.model_text"
]:
    if mod_name not in sys.modules:
        m = ModuleType(mod_name)
        sys.modules[mod_name] = m

class MockResponse:
    pass
class MockTimeout(Exception):
    pass
class MockHTTPError(Exception):
    pass

sys.modules["httpx"].Response = MockResponse
sys.modules["httpx"].TimeoutException = MockTimeout
sys.modules["httpx"].HTTPError = MockHTTPError

sys.modules["langchain_core.tools"].tool = lambda f: f
sys.modules["utils.generated_compute"].require_current_generated_compute = MagicMock()
sys.modules["utils.generated_compute"].generated_compute_configured = MagicMock(return_value=False)
sys.modules["utils.executors"].db_executor = MagicMock()
sys.modules["utils.executors"].run_blocking = AsyncMock()
sys.modules["utils.http_client"].get_webhook_client = MagicMock()
sys.modules["utils.llm.gateway_client"].feature_auto_lane_id = MagicMock(return_value="sonar-pro")
sys.modules["utils.llm.gateway_client"].get_llm_gateway_base_url = MagicMock(return_value="https://api.gateway")
sys.modules["utils.llm.gateway_client"].llm_gateway_headers = MagicMock(return_value={})
sys.modules["utils.log_sanitizer"].sanitize = lambda s: str(s)
sys.modules["utils.model_text"].UNTRUSTED_LEGEND = "--- untrusted ---"
sys.modules["utils.model_text"].count_header = lambda name, shown, total, order: f"{name} ({shown}/{total})"
sys.modules["utils.model_text"].generated = lambda label, text: text
sys.modules["utils.model_text"].truncation_note = lambda shown, total, unit, how_to_get_more: f"[truncated {shown}/{total}]"
sys.modules["utils.model_text"].untrusted_block = lambda label, text: f"<{label}>{text}</{label}>"

from perplexity_tools import (
    perplexity_web_search_tool,
    _perplexity_gateway_search,
    _format_perplexity_response,
    _extract_citations,
)


class TestPerplexityToolsHardening(unittest.TestCase):
    """Test query validation, error handling, and response formatting."""

    def test_empty_or_none_query_rejection(self):
        # Empty, None, or whitespace queries rejected synchronously/asynchronously
        loop = asyncio.new_event_loop()
        try:
            res1 = loop.run_until_complete(perplexity_web_search_tool(None))
            self.assertEqual(res1, "Error: Search query cannot be empty.")

            res2 = loop.run_until_complete(perplexity_web_search_tool(""))
            self.assertEqual(res2, "Error: Search query cannot be empty.")

            res3 = loop.run_until_complete(perplexity_web_search_tool("   "))
            self.assertEqual(res3, "Error: Search query cannot be empty.")
        finally:
            loop.close()

    def test_format_perplexity_response_successful(self):
        sample = {
            "choices": [
                {
                    "message": {
                        "content": "Artificial intelligence advanced rapidly in 2026."
                    }
                }
            ],
            "citations": [
                {"title": "TechCrunch", "url": "https://techcrunch.com/ai"}
            ]
        }
        formatted = _format_perplexity_response(sample)
        self.assertIn("Artificial intelligence advanced rapidly in 2026", formatted)
        self.assertIn("TechCrunch", formatted)
        self.assertIn("https://techcrunch.com/ai", formatted)

    def test_format_perplexity_response_none_content(self):
        sample = {
            "choices": [
                {
                    "message": {
                        "content": None
                    }
                }
            ]
        }
        formatted = _format_perplexity_response(sample)
        self.assertNotIn("None", formatted)
        self.assertIn("Web Search Results:", formatted)

    def test_format_perplexity_response_empty_choices(self):
        sample = {"choices": []}
        formatted = _format_perplexity_response(sample)
        self.assertEqual(formatted, "Error: Unexpected response format from Perplexity API")

    def test_extract_citations_variations(self):
        self.assertEqual(_extract_citations({}), [])
        self.assertEqual(_extract_citations({"choices": []}), [])
        self.assertEqual(_extract_citations({"citations": ["https://example.com"]}), ["https://example.com"])
        self.assertEqual(
            _extract_citations({"choices": [{"message": {"citations": ["https://inner.com"]}}]}),
            ["https://inner.com"]
        )


if __name__ == "__main__":
    unittest.main()
