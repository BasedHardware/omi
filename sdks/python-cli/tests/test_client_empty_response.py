"""Tests for empty HTTP response handling in OmiClient."""

from __future__ import annotations

import httpx
import pytest

from omi_cli.client import OmiClient
from omi_cli.config import Profile
from omi_cli.errors import AuthError, CliError, NotFoundError, RateLimitError, ServerError


@pytest.fixture
def dummy_client() -> OmiClient:
    profile = Profile(
        name="test",
        auth_method="api_key",
        api_key="omi_dev_test_1234567890abcdef12345678",
        api_base="https://api.test.omi.local",
    )
    return OmiClient(profile)


def test_handle_response_empty_200_returns_none(dummy_client: OmiClient) -> None:
    resp = httpx.Response(200, content=b"")
    assert dummy_client._handle_response(resp) is None


def test_handle_response_204_returns_none(dummy_client: OmiClient) -> None:
    resp = httpx.Response(204, content=b"")
    assert dummy_client._handle_response(resp) is None


def test_handle_response_200_json_returns_parsed_data(dummy_client: OmiClient) -> None:
    resp = httpx.Response(200, json={"key": "val"})
    assert dummy_client._handle_response(resp) == {"key": "val"}


@pytest.mark.parametrize(
    "status_code,expected_error,expected_exit_code",
    [
        (400, CliError, 1),
        (401, AuthError, 2),
        (403, AuthError, 2),
        (404, NotFoundError, 5),
        (422, CliError, 1),
        (429, RateLimitError, 4),
        (500, ServerError, 3),
        (502, ServerError, 3),
        (503, ServerError, 3),
    ],
)
def test_handle_response_empty_error_raises_exception(
    dummy_client: OmiClient,
    status_code: int,
    expected_error: type[Exception],
    expected_exit_code: int,
) -> None:
    resp = httpx.Response(status_code, content=b"")
    with pytest.raises(expected_error) as exc_info:
        dummy_client._handle_response(resp)
    assert exc_info.value.exit_code == expected_exit_code
