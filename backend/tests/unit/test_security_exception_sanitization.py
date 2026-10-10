"""CWE-209: internal exception details must never leak into HTTP error responses.

Covers the three routers named in issue #21146:
  - backend/routers/integrations.py  (OAuth state Redis failure)
  - backend/routers/imports.py       (Limitless ZIP upload failure)
  - backend/routers/phone_calls.py   (Twilio verification + token failures)

The fix pattern (mirroring google_calendar.py and PR #20896): full exception
detail goes to server-side logs via ``logger.error(..., exc_info=True)``;
the client-facing HTTPException detail is a fixed generic message.

Hermetic: every external dependency is patched in-process; the network guard
in tests/conftest.py blocks any real outbound call.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.integrations as integrations_mod
import routers.imports as imports_mod
import routers.phone_calls as phone_calls_mod

UID = "u1"


def _assert_sanitized(exc_info, expected_detail, *secrets):
    exc = exc_info.value
    assert exc.status_code == 500
    assert exc.detail == expected_detail
    for secret in secrets:
        assert secret not in exc.detail, f"leaked into client response: {secret!r}"


class TestOAuthStateSanitization:
    """integrations.py — Redis socket/connection errors stay server-side."""

    def test_redis_failure_returns_generic_detail(self):
        redis_secret = "redis://:s3cr3t-redis-pass@10.0.4.15:6379/0"

        def fake_resolve(app_key):
            return ("google", {"kind": "oauth", "name": "Google", "oauth": {"client_id_env": "GOOGLE_CLIENT_ID"}})

        def boom(*args, **kwargs):
            raise ConnectionError(f"Connection to 10.0.4.15:6379 timed out after 3.0s ({redis_secret})")

        with (
            patch.dict("os.environ", {"BASE_API_URL": "https://api.test.example"}),
            patch.object(integrations_mod, "resolve_integration_provider", fake_resolve),
            patch.object(integrations_mod.redis_db.r, "setex", boom),
        ):
            with pytest.raises(HTTPException) as ei:
                integrations_mod.get_oauth_url("google_calendar", uid=UID)

        _assert_sanitized(
            ei,
            "Failed to initialize OAuth flow. Please try again later.",
            "10.0.4.15",
            "s3cr3t-redis-pass",
            "timed out",
        )


class TestImportUploadSanitization:
    """imports.py — filesystem/OS errors stay server-side."""

    @pytest.mark.asyncio
    async def test_upload_failure_returns_generic_detail(self, tmp_path):
        job = SimpleNamespace(id="job-1")

        async def fake_run_blocking(executor, fn, *args, **kwargs):
            if fn is imports_mod.create_import_job:
                return job
            if fn is open:
                return open(*args, **kwargs)
            # import_jobs_db.update_import_job and any other sync helper: call directly
            return fn(*args, **kwargs)

        async def boom_read(n):
            raise OSError("Disk quota exceeded on /var/lib/omi/uploads (errno 122)")

        fake_file = SimpleNamespace(filename="export.zip", read=boom_read)

        with (
            patch.object(imports_mod, "run_blocking", fake_run_blocking),
            patch.object(imports_mod, "TEMP_DIR", str(tmp_path)),
            patch.object(imports_mod.import_jobs_db, "update_import_job", return_value=True),
        ):
            with pytest.raises(HTTPException) as ei:
                await imports_mod.import_limitless_data(file=fake_file, language="en", uid=UID)

        _assert_sanitized(
            ei,
            "Failed to save uploaded file. Please try again later.",
            "/var/lib/omi/uploads",
            "Disk quota exceeded",
            "errno 122",
        )


class TestPhoneVerificationSanitization:
    """phone_calls.py — Twilio API errors stay server-side."""

    def _patch_common(self):
        return (
            patch.object(phone_calls_mod, "check_call_access", lambda uid: None),
            patch.object(
                phone_calls_mod.phone_calls_db,
                "get_phone_number_by_number",
                return_value=None,
            ),
        )

    def test_twilio_failure_returns_generic_detail(self):
        from twilio.base.exceptions import TwilioRestException

        def boom(number):
            raise TwilioRestException(
                500,
                "https://api.twilio.com/2010-04-01/Accounts/ACxxx/Validations.json",
                "Authenticate failed: invalid API key SKlive_9f8e7d at " "https://api.twilio.com (error 20003)",
                code=20003,
            )

        p1, p2 = self._patch_common()
        with p1, p2, patch.object(phone_calls_mod, "start_caller_id_verification", boom):
            with pytest.raises(HTTPException) as ei:
                phone_calls_mod.verify_phone_number(
                    phone_calls_mod.VerifyPhoneNumberRequest(phone_number="+15551234567"),
                    uid=UID,
                    _=None,
                )

        _assert_sanitized(
            ei,
            "Failed to start verification. Please try again later.",
            "SKlive_9f8e7d",
            "api.twilio.com",
            "20003",
        )

    def test_token_generation_failure_returns_generic_detail(self):
        def boom(uid):
            raise RuntimeError("JWT signing failed: bad RS256 private key bytes at /etc/omi/keys/twilio.pem")

        p1, _ = self._patch_common()
        with (
            p1,
            patch.object(
                phone_calls_mod.phone_calls_db,
                "get_primary_phone_number",
                return_value={"id": "n1"},
            ),
            patch.object(phone_calls_mod, "generate_access_token", boom),
        ):
            with pytest.raises(HTTPException) as ei:
                phone_calls_mod.get_phone_token(uid=UID)

        _assert_sanitized(
            ei,
            "Failed to generate token. Please try again later.",
            "/etc/omi/keys/twilio.pem",
            "RS256",
        )
