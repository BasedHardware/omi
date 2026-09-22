import httpx
import pytest
from unittest import mock

from plugins.omi_public_holidays_app.main import (
    get_public_holidays,
    get_next_public_holidays,
    get_long_weekends,
    _SANITIZED_ERROR_MESSAGE,
)
from plugins.omi_public_holidays_app.chat_tool_response import ChatToolResponse


@pytest.fixture
def mock_http_error():
    """Return a mock that raises httpx.HTTPError on any call."""
    def _mock(*args, **kwargs):
        raise httpx.HTTPError("Mock network failure")
    return _mock


@pytest.mark.parametrize(
    "func, args",
    [
        (get_public_holidays, ("US", 2025)),
        (get_next_public_holidays, ("US", 3)),
        (get_long_weekends, ("US", 2025)),
    ],
)
def test_error_sanitization(func, args, mock_http_error):
    """
    Ensure that any httpx.HTTPError raised by the handlers results in a
    sanitized error message that does not expose internal exception details.
    """
    with mock.patch("httpx.get", side_effect=mock_http_error):
        response: ChatToolResponse = func(*args)

    # The response should contain the sanitized error message.
    assert response.error == _SANITIZED_ERROR_MESSAGE

    # The raw exception message should not leak into the response.
    assert "Mock network failure" not in response.error
    assert "httpx" not in response.error
