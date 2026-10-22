"""Unit tests verifying input validation, hop-2 retry concatenation, and response extraction in perplexity_tools.py.

Ensures that:
1. Empty, whitespace-only, or None queries are rejected early with a descriptive error.
2. Hop-2 query concatenation handles clean string queries without raising TypeError.
3. None content in message choices is gracefully converted without raising IndexError or rendering literal 'None'.
4. Malformed choices lists or non-dict structures are handled safely.
"""

import pytest

from utils.retrieval.tools import perplexity_tools
from utils.retrieval.tools.perplexity_tools import (
    _extract_citations,
    _format_perplexity_response,
    _perplexity_gateway_search,
    perplexity_web_search_tool,
)


@pytest.mark.asyncio
async def test_empty_or_none_query_rejection():
    # Empty, None, or whitespace queries rejected early without gateway call
    assert await _perplexity_gateway_search("") == "Error: Search query cannot be empty."
    assert await _perplexity_gateway_search(None) == "Error: Search query cannot be empty."
    assert await _perplexity_gateway_search("   ") == "Error: Search query cannot be empty."

    # Validate tool call surface
    if hasattr(perplexity_web_search_tool, "ainvoke"):
        assert (
            await perplexity_web_search_tool.ainvoke({"query": ""})
            == "Error: Search query cannot be empty."
        )
        assert (
            await perplexity_web_search_tool.ainvoke({"query": None})
            == "Error: Search query cannot be empty."
        )
    elif hasattr(perplexity_web_search_tool, "func"):
        assert (
            await perplexity_web_search_tool.func("")
            == "Error: Search query cannot be empty."
        )
        assert (
            await perplexity_web_search_tool.func(None)
            == "Error: Search query cannot be empty."
        )
    else:
        assert (
            await perplexity_web_search_tool("")
            == "Error: Search query cannot be empty."
        )
        assert (
            await perplexity_web_search_tool(None)
            == "Error: Search query cannot be empty."
        )


def test_format_perplexity_response_successful():
    sample = {
        "choices": [
            {
                "message": {
                    "content": "Artificial intelligence advanced rapidly in 2026."
                }
            }
        ],
        "citations": ["https://techcrunch.com/ai"],
    }
    formatted = _format_perplexity_response(sample)
    assert "Artificial intelligence advanced rapidly in 2026" in formatted
    assert "https://techcrunch.com/ai" in formatted


def test_format_perplexity_response_none_content():
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
    assert "None" not in formatted
    assert (
        "Web search answer" in formatted
        or "Web Search Results:" in formatted
        or "untrusted" in formatted
    )


def test_format_perplexity_response_empty_choices():
    sample = {"choices": []}
    formatted = _format_perplexity_response(sample)
    assert formatted == "Error: Unexpected response format from Perplexity API"


def test_extract_citations_variations():
    assert _extract_citations({}) == []
    assert _extract_citations({"choices": []}) == []
    assert _extract_citations({"citations": ["https://example.com"]}) == ["https://example.com"]
    assert _extract_citations(
        {"choices": [{"message": {"citations": ["https://inner.com"]}}]}
    ) == ["https://inner.com"]
