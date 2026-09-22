import logging
import httpx

import pytest

from plugins.omi_stack_overflow_app.main import (
    search_questions,
    get_question,
    get_top_answers,
)
from omi import ChatToolResponse


@pytest.fixture
def mock_http_error(monkeypatch):
    """
    Patch httpx.get to raise an HTTPError with a message that contains
    sensitive information (e.g., IP addresses, internal URLs).
    """
    def _mock_get(*args, **kwargs):
        raise httpx.HTTPError(
            "Connection aborted: 403 Forbidden from 192.168.1.1"
        )
    monkeypatch.setattr(httpx, "get", _mock_get)


def _assert_sanitized_error(response: ChatToolResponse, caplog):
    """
    Helper to assert that the error message is sanitized and that the
    detailed exception was logged.
    """
    assert isinstance(response, ChatToolResponse)
    assert response.error == (
        "An error occurred while processing your request. Please try again later."
    )
    # The sanitized message should not leak sensitive details
    assert "192.168.1.1" not in response.error
    assert "Connection aborted" not in response.error
    # The detailed exception should be present in the logs
    assert "Connection aborted" in caplog.text
    assert "192.168.1.1" in caplog.text


def test_search_questions_error_sanitization(
    mock_http_error, caplog
):
    caplog.set_level(logging.ERROR)
    response = search_questions("python logging")
    _assert_sanitized_error(response, caplog)


def test_get_question_error_sanitization(
    mock_http_error, caplog
):
    caplog.set_level(logging.ERROR)
    response = get_question(123456)
    _assert_sanitized_error(response, caplog)


def test_get_top_answers_error_sanitization(
    mock_http_error, caplog
):
    caplog.set_level(logging.ERROR)
    response = get_top_answers(123456, limit=5)
    _assert_sanitized_error(response, caplog)
