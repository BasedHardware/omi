import asyncio
from unittest import mock

import httpx
import pytest

# Import the handlers we modified.
from ..main import (
    search_questions,
    get_question,
    get_top_answers,
    SANITIZED_ERROR_MESSAGE,
    ChatToolResponse,
)


@pytest.mark.asyncio
async def test_search_questions_http_error_is_sanitized(monkeypatch):
    async def mock_get(*args, **kwargs):
        raise httpx.HTTPError("Connection failed to 10.0.0.1")

    # Patch the AsyncClient context manager to use our mock_get.
    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, *args, **kwargs):
            return await mock_get(*args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    response: ChatToolResponse = await search_questions("python")
    assert isinstance(response, ChatToolResponse)
    assert response.error == SANITIZED_ERROR_MESSAGE
    # Ensure no raw exception details leak.
    assert "10.0.0.1" not in response.error


@pytest.mark.asyncio
async def test_get_question_http_error_is_sanitized(monkeypatch):
    async def mock_get(*args, **kwargs):
        raise httpx.HTTPError("Proxy timeout at 192.168.0.1")

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, *args, **kwargs):
            return await mock_get(*args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    response: ChatToolResponse = await get_question(123456)
    assert response.error == SANITIZED_ERROR_MESSAGE
    assert "192.168.0.1" not in response.error


@pytest.mark.asyncio
async def test_get_top_answers_http_error_is_sanitized(monkeypatch):
    async def mock_get(*args, **kwargs):
        raise httpx.HTTPError("SSL handshake failed with remote host")

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, *args, **kwargs):
            return await mock_get(*args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    response: ChatToolResponse = await get_top_answers(123456, count=2)
    assert response.error == SANITIZED_ERROR_MESSAGE
    assert "SSL handshake" not in response.error
