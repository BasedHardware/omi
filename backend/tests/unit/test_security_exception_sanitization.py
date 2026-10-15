"""Unit tests for OMI router exception sanitization (CWE-209 mitigation).

Verifies that internal database, Redis, filesystem, and external API exceptions
are properly masked in HTTP 500 responses across integrations, imports, and phone_calls routers,
preventing infrastructure information disclosure while maintaining server-side diagnostics.

Matches the architectural pattern in test_google_calendar_exception_sanitization.py
by binding directly to the real router endpoint handlers.
"""

from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
import pytest

from routers import imports as imp_routes
from routers import integrations as int_routes
from routers import phone_calls as phone_routes
from routers.phone_calls import VerifyPhoneNumberRequest


def test_integrations_oauth_state_redis_error_sanitized(monkeypatch):
    """Verify Redis connection/auth errors in get_oauth_url do not leak host or password details."""
    monkeypatch.setenv("BASE_API_URL", "https://api.omi.me")
    monkeypatch.setattr(
        int_routes,
        "resolve_integration_provider",
        lambda app_key: (
            "google_calendar",
            {
                "kind": "oauth",
                "name": "Google Calendar",
                "oauth": {"client_id_env": "GOOGLE_CLIENT_ID", "redirect_path": "/callback"},
            },
        ),
    )
    mock_redis = MagicMock()
    mock_redis.setex.side_effect = ConnectionError(
        "Error connecting to redis://default:secret_password@10.0.4.12:6379/0: timeout"
    )
    monkeypatch.setattr(int_routes.redis_db, "r", mock_redis)

    with pytest.raises(HTTPException) as exc_info:
        int_routes.get_oauth_url(app_key="google_calendar", uid="test-uid-123")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to initialize OAuth flow."
    assert "secret_password" not in exc_info.value.detail
    assert "10.0.4.12" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_imports_file_write_filesystem_error_sanitized(monkeypatch):
    """Verify filesystem disk errors and internal OS paths in import_limitless_data do not leak in HTTP 500 or persisted job error."""
    fake_job = MagicMock()
    fake_job.id = "job-998877"
    mock_update_job = MagicMock()
    monkeypatch.setattr(imp_routes, "create_import_job", MagicMock(return_value=fake_job))
    monkeypatch.setattr(imp_routes.import_jobs_db, "update_import_job", mock_update_job)

    async def mock_run_blocking(executor, func, *args, **kwargs):
        if func == imp_routes.create_import_job:
            return fake_job
        if func == imp_routes.import_jobs_db.update_import_job:
            mock_update_job(*args, **kwargs)
            return None
        # Simulate disk write permission error
        raise PermissionError("[Errno 13] Permission denied: '/var/data/uploads/app_user_9921/secret_export.zip'")

    monkeypatch.setattr(imp_routes, "run_blocking", mock_run_blocking)

    fake_file = MagicMock()
    fake_file.filename = "export.zip"
    fake_file.read = AsyncMock(side_effect=[b"data_chunk", b""])

    with pytest.raises(HTTPException) as exc_info:
        await imp_routes.import_limitless_data(file=fake_file, language=None, uid="test-uid-123")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to save uploaded file."
    assert "/var/data/uploads" not in exc_info.value.detail
    assert "app_user_9921" not in exc_info.value.detail
    # Verify persisted job error in database is also sanitized
    mock_update_job.assert_called_once_with(
        fake_job.id,
        {'status': imp_routes.ImportJobStatus.failed.value, 'error': "Failed to save uploaded file."},
    )


def test_phone_calls_verification_twilio_error_sanitized(monkeypatch):
    """Verify Twilio API error strings and credentials in verify_phone_number are masked."""
    monkeypatch.setattr(phone_routes, "check_call_access", MagicMock())
    monkeypatch.setattr(phone_routes.phone_calls_db, "get_phone_number_by_number", MagicMock(return_value=None))
    monkeypatch.setattr(phone_routes.phone_calls_db, "set_pending_verification", MagicMock())
    monkeypatch.setattr(
        phone_routes,
        "start_caller_id_verification",
        MagicMock(
            side_effect=Exception(
                "TwilioRestException: [HTTP 401] Unable to authenticate: AccountSid AC123456789 AuthToken tok_998877"
            )
        ),
    )
    req = VerifyPhoneNumberRequest(phone_number="+15551234567")

    with pytest.raises(HTTPException) as exc_info:
        phone_routes.verify_phone_number(request=req, uid="test-uid-123")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to start verification."
    assert "AC123456789" not in exc_info.value.detail
    assert "tok_998877" not in exc_info.value.detail


def test_phone_calls_token_generation_error_sanitized(monkeypatch):
    """Verify token generation exceptions in get_phone_token are masked."""
    monkeypatch.setattr(phone_routes, "check_call_access", MagicMock())
    monkeypatch.setattr(phone_routes.phone_calls_db, "get_primary_phone_number", MagicMock(return_value="+15551234567"))
    monkeypatch.setattr(
        phone_routes,
        "generate_access_token",
        MagicMock(
            side_effect=ValueError(
                "JWT signing failed: private key missing or invalid format at /secrets/jwt_key.pem"
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        phone_routes.get_phone_token(uid="test-uid-123")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to generate token."
    assert "/secrets/jwt_key.pem" not in exc_info.value.detail
