import sys
from unittest.mock import AsyncMock, patch

sys.path.append(".")
import main
from main import (
    ChatToolResponse,
    _safe_get,
    search_articles,
    get_random_article,
    get_article_summary,
    _request_json
)

def test_safe_get_normal_nested_values():
    data = {"a": {"b": {"c": 42}}}
    assert _safe_get(data, "a", "b", "c") == 42

def test_safe_get_missing_key():
    data = {"a": {"b": {}}}
    assert _safe_get(data, "a", "b", "c") is None
    assert _safe_get(data, "x", "y") is None

def test_safe_get_none_argument():
    assert _safe_get(None, "a") is None

def test_safe_get_non_dict_intermediate():
    data = {"a": None}
    assert _safe_get(data, "a", "b") is None

def test_safe_get_string_input():
    data = {"a": "string instead of dict"}
    assert _safe_get(data, "a", "b") is None

def test_safe_get_default_return():
    data = {"a": None}
    result = _safe_get(data, "a", default="fallback")
    assert result == "fallback"

def test_safe_get_wikipedia_payload_structure():
    data = {
        "query": {
            "search": [
                {"title": "Test Article", "snippet": "Test snippet"}
            ]
        }
    }
    results = _safe_get(data, "query", "search", default=[])
    assert len(results) == 1
    assert _safe_get(results[0], "title") == "Test Article"

@patch("main._request_json")
async def test_search_articles_query_none_mock(mock_request):
    """Test search_articles handles {"query": null} without crashing"""
    
    mock_request.return_value = {"query": None}
    
    response = await search_articles({"query": "python"})
    
    assert isinstance(response, ChatToolResponse)
    assert response.error is None
    assert "No Wikipedia articles found" in response.result

@patch("main._request_json")
async def test_get_random_article_query_none_mock(mock_request):
    """Test get_random_article handles {"query": null} without crashing"""
    mock_request.return_value = {"query": None}
    
    response = await get_random_article({"language": "en"})
    
    assert isinstance(response, ChatToolResponse)
    assert response.error is None

@patch("main._request_json")
async def test_get_article_summary_content_urls_none_mock(mock_request):
    mock_request.return_value = {
        "title": "Test Article",
        "extract": "This is a test extract.",
        "content_urls": None,
        "description": None,
        "type": "standard"
    }
    
    response = await get_article_summary({"title": "Test Article"})
    
    assert isinstance(response, ChatToolResponse)
    assert response.error is None
    assert "Test Article" in response.result

@patch("main._request_json")
async def test_search_empty_dict_mock(mock_request):
    """Test empty top-level dict doesn't crash"""
    mock_request.return_value = {}
    
    response = await search_articles({"query": "python"})
    
    assert isinstance(response, ChatToolResponse)
    assert response.error is None
    assert "No Wikipedia articles found" in response.result

@patch("main._request_json")
async def test_search_error_page_mock(mock_request):
    """Test error payloads handled correctly"""
    mock_request.return_value = {
        "error": {
            "code": "badsearch",
            "info": "The search value must be set"
        }
    }
    
    response = await search_articles({"query": "python"})
    
    assert isinstance(response, ChatToolResponse)
    assert response.error is None
    assert "No Wikipedia articles found" in response.result

@patch("main._request_json")
async def test_search_results_item_not_dict_mock(mock_request):
    mock_request.return_value = {
        "query": {
            "search": [
                {"title": "Valid One", "snippet": "Valid"},
                ["not", "dict"],
                {"title": "Another Valid", "snippet": "Valid snippet"}
            ]
        }
    }
    
    response = await search_articles({"query": "python"})
    
    assert isinstance(response, ChatToolResponse)
    assert response.error is None
    assert "Valid One" in response.result
    assert "Another Valid" in response.result

@patch("main._request_json")
async def test_search_random_response_missing_title_mock(mock_request):
    """Test random article response missing title"""
    mock_request.return_value = {
        "query": {
            "random": [{"id": 123}]
        }
    }
    response = await get_random_article({})
    
    assert isinstance(response, ChatToolResponse)
    assert "without a title" in response.result