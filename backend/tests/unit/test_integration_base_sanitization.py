import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from utils.retrieval.tools.integration_base import (
    get_integration_checked,
    parse_iso_with_tz,
    retry_on_auth,
    retry_on_auth_async,
)


def test_get_integration_checked_sanitizes_database_exception():
    """Assert get_integration_checked does not leak database credentials/tracebacks."""
    sensitive_db_err = "postgres://user:super_secret_password@db.internal:5432/omi"
    with (
        patch(
            "utils.retrieval.tools.integration_base.users_db.get_integration",
            side_effect=RuntimeError(sensitive_db_err),
        ),
        patch("utils.retrieval.tools.integration_base.logger.error") as mock_logger,
    ):
        integration, err = get_integration_checked(
            uid="user-123",
            key="google_calendar",
            connection_name="Google Calendar",
            not_connected_msg="Error: Not connected",
            error_prefix="Google Calendar",
        )
        assert integration is None
        assert err == "Google Calendar: Failed to retrieve integration"
        assert "super_secret_password" not in err
        assert "postgres://" not in err

        mock_logger.assert_called_once()
        log_msg = mock_logger.call_args[0][0]
        assert sensitive_db_err in log_msg
        assert mock_logger.call_args[1].get("exc_info") is True


def test_get_integration_checked_sanitizes_timeout_error():
    """Assert get_integration_checked does not leak internal timeout errors."""
    with (
        patch(
            "utils.retrieval.tools.integration_base.users_db.get_integration",
            side_effect=TimeoutError("FirestoreTimeoutError: Deadline exceeded in cluster us-central1"),
        ),
        patch("utils.retrieval.tools.integration_base.logger.error") as mock_logger,
    ):
        integration, err = get_integration_checked(
            uid="user-123",
            key="slack",
            connection_name="Slack",
            not_connected_msg="Error: Not connected",
            error_prefix="Slack",
        )
        assert integration is None
        assert err == "Slack: Failed to retrieve integration"
        assert "FirestoreTimeoutError" not in err
        mock_logger.assert_called_once()


def test_parse_iso_with_tz_sanitizes_value_error():
    """Assert parse_iso_with_tz formats a clean error without raw Python ValueError text."""
    with patch("utils.retrieval.tools.integration_base.logger.warning") as mock_logger:
        dt, err = parse_iso_with_tz(
            field_name="start_time",
            value="invalid-date-format-12345",
            tz_required_msg="ISO-8601 string with timezone",
        )
        assert dt is None
        assert (
            err == "Error: Invalid start_time format. Expected ISO-8601 string with timezone: invalid-date-format-12345"
        )
        assert "ValueError" not in err
        assert "fromisoformat" not in err
        mock_logger.assert_called_once()
        assert "invalid-date-format-12345" in mock_logger.call_args[0][0]


def test_retry_on_auth_sanitizes_sensitive_non_auth_exception():
    """Assert retry_on_auth does not leak bearer tokens or internal server error details."""
    sensitive_msg = "Bearer secret_token_12345 failed with 500: Internal cluster gateway failure"
    call_fn = MagicMock(side_effect=RuntimeError(sensitive_msg))
    refresh_fn = MagicMock()

    with patch("utils.retrieval.tools.integration_base.logger.error") as mock_logger:
        res, err = retry_on_auth(
            call_fn=call_fn,
            call_kwargs={"param": "value"},
            refresh_fn=refresh_fn,
            uid="user-123",
            integration={"connected": True},
            expired_msg="Token expired",
        )

        assert res is None
        assert err == "Error: An error occurred while communicating with the service"
        assert "secret_token_12345" not in err
        assert "Internal cluster gateway failure" not in err
        refresh_fn.assert_not_called()

        mock_logger.assert_called_once()
        log_msg = mock_logger.call_args[0][0]
        assert sensitive_msg in log_msg
        assert "user-123" in log_msg
        assert mock_logger.call_args[1].get("exc_info") is True


@pytest.mark.asyncio
async def test_retry_on_auth_async_sanitizes_sensitive_non_auth_exception():
    """Assert retry_on_auth_async does not leak bearer tokens or internal server error details."""
    sensitive_msg = "Bearer secret_async_token_99999 failed with 502 Bad Gateway"
    call_fn = MagicMock(side_effect=RuntimeError(sensitive_msg))
    refresh_fn = MagicMock()

    with patch("utils.retrieval.tools.integration_base.logger.error") as mock_logger:
        res, err = await retry_on_auth_async(
            call_fn=call_fn,
            call_kwargs={"param": "value"},
            refresh_fn=refresh_fn,
            uid="user-456",
            integration={"connected": True},
            expired_msg="Token expired",
        )

        assert res is None
        assert err == "Error: An error occurred while communicating with the service"
        assert "secret_async_token_99999" not in err
        refresh_fn.assert_not_called()

        mock_logger.assert_called_once()
        log_msg = mock_logger.call_args[0][0]
        assert sensitive_msg in log_msg
        assert "user-456" in log_msg
        assert mock_logger.call_args[1].get("exc_info") is True


def test_retry_on_auth_sanitizes_error_after_token_refresh():
    """Assert retry_on_auth does not leak exception details if call fails after token refresh."""
    sensitive_err_after_refresh = (
        "Internal database connection failed to internal-db.cluster.local:5432 with password secret_pw"
    )
    attempts = 0

    def mock_call(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("401 Unauthorized: token may be expired")
        raise RuntimeError(sensitive_err_after_refresh)

    refresh_fn = MagicMock(return_value="new_fresh_token_123")

    with patch("utils.retrieval.tools.integration_base.logger.error") as mock_logger:
        res, err = retry_on_auth(
            call_fn=mock_call,
            call_kwargs={"access_token": "expired_token"},
            refresh_fn=refresh_fn,
            uid="user-789",
            integration={"connected": True},
            expired_msg="Token expired",
        )

        assert res is None
        assert err == "Error: Service temporarily unavailable after token refresh"
        assert "internal-db.cluster.local" not in err
        assert "secret_pw" not in err
        refresh_fn.assert_called_once_with("user-789", {"connected": True})

        mock_logger.assert_called_once()
        log_msg = mock_logger.call_args[0][0]
        assert sensitive_err_after_refresh in log_msg
        assert "user-789" in log_msg
        assert mock_logger.call_args[1].get("exc_info") is True


@pytest.mark.asyncio
async def test_retry_on_auth_async_sanitizes_error_after_token_refresh():
    """Assert retry_on_auth_async does not leak exception details if call fails after token refresh."""
    sensitive_err_after_refresh = "Async connection pool exhausted on redis://auth:secret@redis-internal:6379"
    attempts = 0

    async def mock_async_call(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Authentication failed: token may be expired or invalid")
        raise RuntimeError(sensitive_err_after_refresh)

    async def mock_async_refresh(uid, integration):
        return "new_async_token_456"

    with patch("utils.retrieval.tools.integration_base.logger.error") as mock_logger:
        res, err = await retry_on_auth_async(
            call_fn=mock_async_call,
            call_kwargs={"access_token": "expired_token"},
            refresh_fn=mock_async_refresh,
            uid="user-101",
            integration={"connected": True},
            expired_msg="Token expired",
        )

        assert res is None
        assert err == "Error: Service temporarily unavailable after token refresh"
        assert "redis-internal" not in err
        assert "secret" not in err

        mock_logger.assert_called_once()
        log_msg = mock_logger.call_args[0][0]
        assert sensitive_err_after_refresh in log_msg
        assert "user-101" in log_msg
        assert mock_logger.call_args[1].get("exc_info") is True
