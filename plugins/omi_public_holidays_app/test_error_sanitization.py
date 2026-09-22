import httpx
import pytest

from .main import (
    get_public_holidays,
    get_next_public_holidays,
    get_long_weekends,
    list_supported_countries,
)
from .chat_tool_response import ChatToolResponse


@pytest.fixture
def mock_http_error(monkeypatch):
    def raise_error(*args, **kwargs):
        raise httpx.HTTPError("Simulated network failure")

    monkeypatch.setattr(httpx, "get", raise_error)


def test_get_public_holidays_error_sanitization(mock_http_error):
    response = get_public_holidays("US", 2024)
    assert isinstance(response, ChatToolResponse)
    assert response.error is not None
    assert "httpx" not in response.error
    assert "Traceback" not in response.error


def test_get_next_public_holidays_error_sanitization(mock_http_error):
    response = get_next_public_holidays("US")
    assert isinstance(response, ChatToolResponse)
    assert response.error is not None
    assert "httpx" not in response.error
    assert "Traceback" not in response.error


def test_get_long_weekends_error_sanitization(mock_http_error):
    response = get_long_weekends("US", 2024)
    assert isinstance(response, ChatToolResponse)
    assert response.error is not None
    assert "httpx" not in response.error
    assert "Traceback" not in response.error


def test_list_supported_countries_error_sanitization(mock_http_error):
    response = list_supported_countries()
    assert isinstance(response, ChatToolResponse)
    assert response.error is not None
    assert "httpx" not in response.error
    assert "Traceback" not in response.error
