import pytest
import httpx
from plugins.omi_semantic_scholar_app.main import (
    search_papers,
    get_paper,
    get_author_papers,
)

@pytest.fixture
def mock_httpx_get(monkeypatch):
    """
    Helper fixture to replace httpx.get with a mock that can raise exceptions.
    """
    def _mock_get(*args, **kwargs):
        raise httpx.HTTPError("Simulated network failure")
    monkeypatch.setattr(httpx, "get", _mock_get)
    return _mock_get

def test_search_papers_http_error(monkeypatch):
    def mock_get(*args, **kwargs):
        raise httpx.HTTPError("Simulated network failure")
    monkeypatch.setattr(httpx, "get", mock_get)

    resp = search_papers("quantum computing")
    assert resp.error == "Semantic Scholar request failed. Please try again later."
    assert "Simulated network failure" not in resp.error

def test_search_papers_generic_error(monkeypatch):
    def mock_get(*args, **kwargs):
        raise Exception("Unexpected error")
    monkeypatch.setattr(httpx, "get", mock_get)

    resp = search_papers("quantum computing")
    assert resp.error == "An unexpected error occurred. Please try again later."
    assert "Unexpected error" not in resp.error

def test_get_paper_http_error(monkeypatch):
    def mock_get(*args, **kwargs):
        raise httpx.HTTPError("Simulated network failure")
    monkeypatch.setattr(httpx, "get", mock_get)

    resp = get_paper("12345")
    assert resp.error == "Semantic Scholar request failed. Please try again later."
    assert "Simulated network failure" not in resp.error

def test_get_paper_generic_error(monkeypatch):
    def mock_get(*args, **kwargs):
        raise Exception("Unexpected error")
    monkeypatch.setattr(httpx, "get", mock_get)

    resp = get_paper("12345")
    assert resp.error == "An unexpected error occurred. Please try again later."
    assert "Unexpected error" not in resp.error

def test_get_author_papers_http_error(monkeypatch):
    def mock_get(*args, **kwargs):
        raise httpx.HTTPError("Simulated network failure")
    monkeypatch.setattr(httpx, "get", mock_get)

    resp = get_author_papers("67890")
    assert resp.error == "Semantic Scholar request failed. Please try again later."
    assert "Simulated network failure" not in resp.error

def test_get_author_papers_generic_error(monkeypatch):
    def mock_get(*args, **kwargs):
        raise Exception("Unexpected error")
    monkeypatch.setattr(httpx, "get", mock_get)

    resp = get_author_papers("67890")
    assert resp.error == "An unexpected error occurred. Please try again later."
    assert "Unexpected error" not in resp.error
