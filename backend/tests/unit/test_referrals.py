from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Iterator

from fastapi import HTTPException
import pytest

from routers import auth
from testing.import_isolation import load_module_fresh, stub_modules
from utils.referrals import (
    REFERRAL_COOKIE_NAME,
    REFERRAL_SIGNUP_URL,
    ReferralCodeError,
    create_referral_code,
    is_new_referral_account,
    referral_claim_patch,
    referrer_uid_from_code,
)

TEST_SECRET = b"referral-test-secret-that-is-at-least-32-bytes"
REFERRALS_ROUTER_PATH = Path(__file__).resolve().parents[2] / "routers" / "referrals.py"


@contextmanager
def _loaded_referrals_router() -> Iterator[ModuleType]:
    endpoints = ModuleType("utils.other.endpoints")
    endpoints.get_current_user_uid = lambda: "test-user"
    with stub_modules({"utils.other.endpoints": endpoints}):
        yield load_module_fresh("routers.referrals", str(REFERRALS_ROUTER_PATH))


def test_referral_code_round_trips_and_rejects_tampering():
    code = create_referral_code("referrer-123", secret=TEST_SECRET)

    assert referrer_uid_from_code(code, secret=TEST_SECRET) == "referrer-123"

    with pytest.raises(ReferralCodeError, match="invalid_referral_signature"):
        referrer_uid_from_code(f"{code[:-1]}x", secret=TEST_SECRET)


def test_referral_claim_grants_exactly_30_days_of_operator():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    patch, reason = referral_claim_patch(
        referred_uid="new-user",
        referrer_uid="referrer",
        is_new_user=True,
        user_data={"subscription": {"plan": "basic", "status": "active"}},
        now=now,
    )

    assert patch is not None
    assert reason == "granted"
    assert patch["subscription"]["plan"] == "operator"
    assert patch["subscription"]["status"] == "active"
    assert patch["subscription"]["cancel_at_period_end"] is True
    assert patch["subscription"]["current_period_end"] - patch["subscription"]["current_period_start"] == 30 * 86400
    assert patch["referral"]["program"] == "desktop_operator_month_v1"
    assert patch["referral"]["referrer_uid"] == "referrer"


@pytest.mark.parametrize(
    ("user_data", "is_new_user", "expected_reason"),
    [
        (
            {"subscription": {"plan": "basic", "status": "active"}},
            False,
            "existing_account",
        ),
        (
            {
                "subscription": {"plan": "basic", "status": "active"},
                "referral": {"claimed_at": 123},
            },
            True,
            "already_claimed",
        ),
        (
            {
                "subscription": {"plan": "operator", "status": "active"},
            },
            True,
            "paid",
        ),
        (
            {
                "subscription": {"plan": "basic", "status": "active"},
            },
            True,
            "self_refer",
        ),
    ],
)
def test_referral_claim_rejects_already_claimed_or_ineligible_users(user_data, is_new_user, expected_reason):
    referrer_uid = "same-user" if expected_reason == "self_refer" else "different-referrer"
    patch, reason = referral_claim_patch(
        referred_uid="same-user",
        referrer_uid=referrer_uid,
        is_new_user=is_new_user,
        user_data=user_data,
        now=datetime.now(timezone.utc),
    )

    assert patch is None
    assert reason == expected_reason


@pytest.mark.parametrize(
    ("uid", "referrer_uid", "reason"),
    [
        ("user-1", "user-1", "self_refer"),
        ("user-2", "referrer-2", "existing_account"),
        ("user-3", "referrer-3", "already_claimed"),
        ("user-4", "referrer-4", "paid"),
    ],
)
def test_referral_claim_emits_ineligible_reason(monkeypatch, uid, referrer_uid, reason):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())
    code = create_referral_code(referrer_uid)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    with _loaded_referrals_router() as referrals:
        events = []
        monkeypatch.setattr(
            referrals.firebase_admin.auth,
            "get_user",
            lambda _uid: SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=now_ms)),
        )
        monkeypatch.setattr(referrals, "claim_referral_trial", lambda *_args, **_kwargs: (False, reason))
        monkeypatch.setattr(referrals, "emit_posthog_event", lambda *event: events.append(event))
        response = referrals.claim_referral(referrals.ReferralClaimRequest(code=code), uid)

    assert response.claimed is False
    assert events == [
        (
            uid,
            "Referral Claimed",
            {
                "program": "desktop_operator_month_v1",
                "claimed": False,
                "reason": reason,
            },
        )
    ]


def test_referral_claim_rejects_an_invalid_code_before_loading_the_user(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())

    with _loaded_referrals_router() as referrals:
        get_user = lambda _uid: pytest.fail("invalid referral must not load the user")
        monkeypatch.setattr(referrals.firebase_admin.auth, "get_user", get_user)

        with pytest.raises(HTTPException) as error:
            referrals.claim_referral(referrals.ReferralClaimRequest(code="invalid"), "new-user")

    assert error.value.status_code == 404
    assert error.value.detail == "Referral link not found"


def test_referral_claim_rejects_empty_or_whitespace_code():
    with _loaded_referrals_router() as referrals:
        for empty_code in ["", "   ", "\t\n"]:
            with pytest.raises(HTTPException) as error:
                referrals.claim_referral(referrals.ReferralClaimRequest(code=empty_code), "new-user")
            assert error.value.status_code == 400
            assert error.value.detail == "Referral code cannot be empty"


def test_referral_claim_sanitizes_auth_lookup_failure_to_503(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())
    code = create_referral_code("referrer-123")

    with _loaded_referrals_router() as referrals:

        def auth_failure(_uid):
            raise RuntimeError("firebase_admin.exceptions.FirebaseError: Connection reset")

        monkeypatch.setattr(referrals.firebase_admin.auth, "get_user", auth_failure)

        with pytest.raises(HTTPException) as error:
            referrals.claim_referral(referrals.ReferralClaimRequest(code=code), "new-user")

        assert error.value.status_code == 503
        assert error.value.detail == "User authentication metadata temporarily unavailable"
        assert "firebase_admin" not in str(error.value.detail)


def test_referral_claim_sanitizes_trial_grant_storage_failure_to_503(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())
    code = create_referral_code("referrer-123")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    with _loaded_referrals_router() as referrals:
        monkeypatch.setattr(
            referrals.firebase_admin.auth,
            "get_user",
            lambda _uid: SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=now_ms)),
        )

        def store_failure(*_args, **_kwargs):
            raise RuntimeError("google.cloud.exceptions.GoogleCloudError: 503 Deadline Exceeded")

        monkeypatch.setattr(referrals, "claim_referral_trial", store_failure)

        with pytest.raises(HTTPException) as error:
            referrals.claim_referral(referrals.ReferralClaimRequest(code=code), "new-user")

        assert error.value.status_code == 503
        assert error.value.detail == "Referral claim service temporarily unavailable"
        assert "GoogleCloudError" not in str(error.value.detail)


def test_safe_emit_posthog_event_swallows_telemetry_errors(monkeypatch):
    with _loaded_referrals_router() as referrals:

        def exploding_emit(*_args, **_kwargs):
            raise RuntimeError("PostHog socket closed")

        monkeypatch.setattr(referrals, "emit_posthog_event", exploding_emit)
        # Must not raise or bubble up
        referrals._safe_emit_posthog_event("user-1", "Test Event", {"key": "val"})


def test_referral_new_user_window_rejects_missing_future_and_old_timestamps():
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)

    assert is_new_referral_account(int(now.timestamp() * 1000), now=now) is True
    assert is_new_referral_account(None, now=now) is False
    assert is_new_referral_account(int((now.timestamp() + 1) * 1000), now=now) is False
    assert is_new_referral_account(int((now.timestamp() - 901) * 1000), now=now) is False


def test_authenticated_referrer_receives_a_stable_unique_https_link(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())
    monkeypatch.delenv("REFERRAL_PUBLIC_BASE_URL", raising=False)

    with _loaded_referrals_router() as referrals:
        events = []
        monkeypatch.setattr(referrals, "emit_posthog_event", lambda *event: events.append(event))
        first = referrals.get_referral_link("referrer-123").referral_url
        second = referrals.get_referral_link("referrer-123").referral_url
        other = referrals.get_referral_link("another-user").referral_url

    assert first == second
    assert first != other
    assert first.startswith("https://omi.me/r/ref1.")
    assert events == [
        (
            "referrer-123",
            "Referral Link Issued",
            {"program": "desktop_operator_month_v1"},
        ),
        (
            "referrer-123",
            "Referral Link Issued",
            {"program": "desktop_operator_month_v1"},
        ),
        (
            "another-user",
            "Referral Link Issued",
            {"program": "desktop_operator_month_v1"},
        ),
    ]


def test_authenticated_referrer_uses_configured_dev_public_origin(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())
    monkeypatch.setenv("REFERRAL_PUBLIC_BASE_URL", "https://api.omiapi.com/")

    with _loaded_referrals_router() as referrals:
        referral_url = referrals.get_referral_link("referrer-123").referral_url

    assert referral_url.startswith("https://api.omiapi.com/r/ref1.")
    assert referrer_uid_from_code(referral_url.rsplit("/", 1)[-1]) == "referrer-123"


def test_referral_link_returns_sanitized_unavailable_response_when_signing_fails(
    monkeypatch,
):
    with _loaded_referrals_router() as referrals:

        def signing_failure(_uid):
            raise ReferralCodeError("missing_referral_signing_secret")

        monkeypatch.setattr(referrals, "referral_link", signing_failure)

        with pytest.raises(HTTPException) as error:
            referrals.get_referral_link("user-1")

    assert error.value.status_code == 503
    assert error.value.detail == "Referral links are temporarily unavailable"


def test_capture_referral_redirects_to_signup_with_cookie(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())
    code = create_referral_code("referrer-123")

    with _loaded_referrals_router() as referrals:
        events = []
        monkeypatch.setattr(referrals, "emit_posthog_event", lambda *event: events.append(event))
        response = referrals.capture_referral(code)

    assert response.status_code == 302
    assert response.headers["location"].startswith(f"{REFERRAL_SIGNUP_URL}?")
    assert "environment=" in response.headers["location"]
    set_cookie = response.headers.get("set-cookie", "")
    assert REFERRAL_COOKIE_NAME in set_cookie
    assert f"{REFERRAL_COOKIE_NAME}={code}" in set_cookie
    assert events == [
        (
            "referrer-123",
            "Referral Link Captured",
            {"program": "desktop_operator_month_v1"},
        ),
    ]


def test_capture_referral_rejects_invalid_code(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())

    with _loaded_referrals_router() as referrals:
        with pytest.raises(HTTPException) as error:
            referrals.capture_referral("invalid")

    assert error.value.status_code == 404
    assert error.value.detail == "Referral link not found"


def test_static_zero_raw_exception_reflection_referrals():
    candidates = [
        REFERRALS_ROUTER_PATH,
        Path(__file__).resolve().parent / "referrals.py",
    ]
    target = next((p for p in candidates if p.exists()), None)
    assert target is not None, "referrals.py router file must exist"
    source = target.read_text(encoding="utf-8")
    assert "detail=str(e)" not in source
    assert "detail=str(exc)" not in source
    assert 'detail=f"{e' not in source
    assert 'detail=f"{exc' not in source


@pytest.mark.asyncio
async def test_google_auth_with_new_user_redeems_referral(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())
    monkeypatch.setenv("FIREBASE_API_KEY", "test-key")
    referral_code = create_referral_code("referrer-123")
    claims = []
    events = []

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"localId": "new-user", "isNewUser": True}

    class Client:
        @staticmethod
        async def post(*_args, **_kwargs):
            return Response()

    def claim(referred_uid, referrer_uid, *, is_new_user):
        claims.append((referred_uid, referrer_uid, is_new_user))
        return True, "granted"

    async def run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(auth, "get_auth_client", lambda: Client())
    monkeypatch.setattr(auth, "claim_referral_trial", claim)
    monkeypatch.setattr(auth, "emit_posthog_event", lambda *event: events.append(event))
    monkeypatch.setattr(auth, "run_blocking", run_inline)
    monkeypatch.setattr(
        auth.firebase_admin.auth,
        "create_custom_token",
        lambda _uid: b"custom-token",
        raising=False,
    )

    token = await auth._generate_custom_token("google", "provider-token", referral_code=referral_code)

    assert token == "custom-token"
    assert claims == [("new-user", "referrer-123", True)]
    assert events == [
        (
            "new-user",
            "Referral Claimed",
            {
                "program": "desktop_operator_month_v1",
                "claimed": True,
                "reason": "granted",
            },
        )
    ]


@pytest.mark.asyncio
async def test_existing_user_auth_does_not_redeem_referral(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_SECRET", TEST_SECRET.decode())
    monkeypatch.setenv("FIREBASE_API_KEY", "test-key")
    referral_code = create_referral_code("referrer-123")
    claims = []

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"localId": "existing-user", "isNewUser": False}

    class Client:
        @staticmethod
        async def post(*_args, **_kwargs):
            return Response()

    async def run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(auth, "get_auth_client", lambda: Client())
    monkeypatch.setattr(
        auth,
        "claim_referral_trial",
        lambda *args, **kwargs: claims.append((args, kwargs)),
    )
    monkeypatch.setattr(auth, "run_blocking", run_inline)
    monkeypatch.setattr(
        auth.firebase_admin.auth,
        "create_custom_token",
        lambda _uid: b"custom-token",
        raising=False,
    )

    await auth._generate_custom_token("google", "provider-token", referral_code=referral_code)

    assert claims == []
