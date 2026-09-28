import asyncio
import os
from unittest.mock import patch

import httpx
import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from utils.retrieval.tools import web_tools


@pytest.mark.asyncio
async def test_connect_error_sanitized(caplog):
    sensitive_err = "Failed to connect to 10.0.0.1:8080 [secret_internal_host]"
    with (
        patch.object(
            web_tools,
            "_fetch_page",
            side_effect=httpx.ConnectError(sensitive_err),
        ),
        caplog.at_level("WARNING"),
    ):
        res = await web_tools.fetch_url_tool.coroutine("https://example.com/api")

    assert "10.0.0.1" not in res
    assert "secret_internal_host" not in res
    assert (
        res
        == "Error: Could not connect to the specified URL. Please check that the URL is valid and accessible."
    )
    assert any(
        record.levelname == "WARNING"
        and "fetch_url_tool - connection error fetching" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_generic_exception_sanitized(caplog):
    sensitive_err = "database pool connection failed /internal/certs/key.pem"
    with (
        patch.object(
            web_tools,
            "_fetch_page",
            side_effect=RuntimeError(sensitive_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await web_tools.fetch_url_tool.coroutine("https://example.com/db")

    assert "/internal/certs/key.pem" not in res
    assert (
        res
        == "Error: An error occurred while fetching the URL. Please verify the URL and try again later."
    )
    assert any(
        record.levelname == "ERROR"
        and "database pool connection failed" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_httpx_timeout_sanitized(caplog):
    sensitive_err = "Read timed out with secret_token=sk-999"
    with (
        patch.object(
            web_tools,
            "_fetch_page",
            side_effect=httpx.TimeoutException(sensitive_err),
        ),
        caplog.at_level("WARNING"),
    ):
        res = await web_tools.fetch_url_tool.coroutine("https://example.com/slow")

    assert "sk-999" not in res
    assert res == "Error: The request to the specified URL timed out."
    assert any(
        record.levelname == "WARNING"
        and "fetch_url_tool - timeout fetching" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_asyncio_timeout_sanitized(caplog):
    with (
        patch.object(
            web_tools,
            "_fetch_page",
            side_effect=asyncio.TimeoutError(),
        ),
        caplog.at_level("WARNING"),
    ):
        res = await web_tools.fetch_url_tool.coroutine("https://example.com/async-slow")

    assert res == "Error: The request to the specified URL timed out."
    assert any(
        record.levelname == "WARNING"
        and "fetch_url_tool - timeout fetching" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_value_error_ssrf_preserved():
    with patch.object(
        web_tools,
        "_fetch_page",
        side_effect=ValueError("URL resolves to a private or reserved address"),
    ):
        res = await web_tools.fetch_url_tool.coroutine("https://10.0.0.1/admin")

    assert res == "Error: URL resolves to a private or reserved address"


@pytest.mark.asyncio
async def test_invalid_scheme_direct_return():
    res = await web_tools.fetch_url_tool.coroutine("ftp://example.com/file")
    assert res == "Error: URL must start with http:// or https://"
