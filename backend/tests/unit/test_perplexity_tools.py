"""Tests verifying perplexity_tools query validation, error handling, and hop-2 retry logic.

Ensures that empty, whitespace-only, or None queries return a graceful error message without
triggering bad requests or NoneType concatenation errors. Also verifies that hop-2 retry handles
thin misses properly and retains the hop-1 response upon secondary failure.
"""

from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


@pytest.fixture(scope="module", autouse=True)
def _perplexity_module():
    """Load perplexity_tools with temporary stub dependencies."""
    langchain_tools = ModuleType("langchain_core.tools")
    langchain_tools.tool = _tool_decorator

    model_text = load_module_fresh("utils.model_text", str(BACKEND_DIR / "utils" / "model_text.py"))
    log_sanitizer = load_module_fresh("utils.log_sanitizer", str(BACKEND_DIR / "utils" / "log_sanitizer.py"))

    executors = ModuleType("utils.executors")
    executors.db_executor = MagicMock()
    executors.run_blocking = AsyncMock(side_effect=lambda exc, func, *args, **kwargs: func(*args, **kwargs))

    http_client = ModuleType("utils.http_client")
    http_client.get_webhook_client = MagicMock()

    gateway_client = ModuleType("utils.llm.gateway_client")
    gateway_client.feature_auto_lane_id = MagicMock(return_value="sonar-pro")
    gateway_client.get_llm_gateway_base_url = MagicMock(return_value="https://api.test")
    gateway_client.llm_gateway_headers = MagicMock(return_value={})

    generated_compute = ModuleType("utils.generated_compute")
    generated_compute.require_current_generated_compute = MagicMock()
    generated_compute.generated_compute_configured = MagicMock(return_value=False)

    stubs = {
        "langchain_core": ModuleType("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "utils.executors": executors,
        "utils.http_client": http_client,
        "utils.llm": ModuleType("utils.llm"),
        "utils.llm.gateway_client": gateway_client,
        "utils.generated_compute": generated_compute,
        "utils.model_text": model_text,
        "utils.log_sanitizer": log_sanitizer,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools.perplexity_tools",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "perplexity_tools.py"),
        )
        globals()["pt"] = module
        yield
        globals().pop("pt", None)


@pytest.mark.asyncio
async def test_empty_and_whitespace_query_rejection():
    res1 = await pt.perplexity_web_search_tool.func("")
    assert "Error: Search query cannot be empty." in res1

    res2 = await pt.perplexity_web_search_tool.func("   ")
    assert "Error: Search query cannot be empty." in res2

    res3 = await pt.perplexity_web_search_tool.func(None)
    assert "Error: Search query cannot be empty." in res3


@pytest.mark.asyncio
async def test_successful_search_formatting():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Omi is an open-source AI wearable platform."
                }
            }
        ],
        "citations": [
            {"title": "Omi Official Website", "url": "https://omi.me"},
            "https://github.com/BasedHardware/omi",
        ],
    }

    with patch.object(pt, "_post_gateway_chat_completion", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await pt.perplexity_web_search_tool.func("What is Omi?")
        assert "Web Search Results:" in result
        assert "Omi is an open-source AI wearable platform." in result
        assert "Omi Official Website" in result
        assert "https://omi.me" in result
        assert "https://github.com/BasedHardware/omi" in result
        mock_post.assert_awaited_once_with("What is Omi?")


@pytest.mark.asyncio
async def test_thin_miss_triggers_hop2_retry():
    first_response = MagicMock()
    first_response.status_code = 200
    first_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "I couldn't find any public information on the marketing site."
                }
            }
        ],
        "citations": [],
    }

    retry_response = MagicMock()
    retry_response.status_code = 200
    retry_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "According to founder interviews and podcast appearances, the project launched in 2024."
                }
            }
        ],
        "citations": [{"title": "Podcast Interview", "url": "https://example.com/interview"}],
    }

    with patch.object(pt, "_post_gateway_chat_completion", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [first_response, retry_response]
        result = await pt.perplexity_web_search_tool.func("Who founded Omi?")
        assert mock_post.await_count == 2
        call_args_hop2 = mock_post.await_args_list[1][0][0]
        assert "Who founded Omi?" in call_args_hop2
        assert pt.WEB_SEARCH_RETRIEVAL_APPENDIX in call_args_hop2
        assert "According to founder interviews" in result
        assert "Podcast Interview" in result


@pytest.mark.asyncio
async def test_hop2_failure_retains_first_result():
    first_response = MagicMock()
    first_response.status_code = 200
    first_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Limited public information found on product."
                }
            }
        ],
        "citations": [],
    }

    with patch.object(pt, "_post_gateway_chat_completion", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [first_response, Exception("Hop-2 network error")]
        result = await pt.perplexity_web_search_tool.func("Test query")
        assert "Limited public information found on product." in result


@pytest.mark.asyncio
async def test_gateway_http_error():
    err_response = MagicMock()
    err_response.status_code = 502
    err_response.text = "Bad Gateway"

    with patch.object(pt, "_post_gateway_chat_completion", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = err_response
        result = await pt.perplexity_web_search_tool.func("Search query")
        assert "Error: Perplexity API returned status 502" in result


@pytest.mark.asyncio
async def test_gateway_timeout_exception():
    import httpx

    with patch.object(pt, "_post_gateway_chat_completion", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Timeout")
        result = await pt.perplexity_web_search_tool.func("Search query")
        assert "Error: Web search is temporarily unavailable." in result


def test_citation_extraction_edge_cases():
    assert pt._extract_citations({"choices": []}) == []
    assert pt._extract_citations({}) == []
    assert pt._extract_citations({"citations": "invalid"}) == []
    nested = {"choices": [{"message": {"citations": ["https://citation.com"]}}]}
    assert pt._extract_citations(nested) == ["https://citation.com"]


def test_format_perplexity_response_edge_cases():
    assert "Error: Unexpected response format from Perplexity API" in pt._format_perplexity_response({"choices": []})
    assert "Error: Unexpected response format from Perplexity API" in pt._format_perplexity_response("invalid")  # type: ignore[arg-type]
    none_content = {"choices": [{"message": {"content": None}}]}
    formatted = pt._format_perplexity_response(none_content)
    assert "Web Search Results:" in formatted
    assert "Perplexity answer: None" not in formatted
