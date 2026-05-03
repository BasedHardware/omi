"""Tests for the OAuth browser flow + refresh logic."""

from __future__ import annotations

import time

import httpx
import pytest

from omi_cli import config as cfg
from omi_cli.auth import oauth
from omi_cli.auth.store import store_oauth_tokens
from omi_cli.errors import AuthError, UsageError

# ---- needs_refresh ---------------------------------------------------------


def test_needs_refresh_returns_false_for_api_key_profile(config_path) -> None:
    profile = cfg.Profile(name="default", auth_method="api_key", api_key="omi_dev_xxx")
    assert oauth.needs_refresh(profile) is False


def test_needs_refresh_true_when_no_expiry(config_path) -> None:
    profile = cfg.Profile(name="default", auth_method="oauth", id_token="t", refresh_token="r")
    assert oauth.needs_refresh(profile) is True


def test_needs_refresh_true_when_expired(config_path) -> None:
    profile = cfg.Profile(
        name="default",
        auth_method="oauth",
        id_token="t",
        refresh_token="r",
        id_token_expires_at=time.time() - 5,
    )
    assert oauth.needs_refresh(profile) is True


def test_needs_refresh_false_when_far_from_expiry(config_path) -> None:
    profile = cfg.Profile(
        name="default",
        auth_method="oauth",
        id_token="t",
        refresh_token="r",
        id_token_expires_at=time.time() + 3000,
    )
    assert oauth.needs_refresh(profile) is False


# ---- refresh_id_token ------------------------------------------------------


def test_refresh_rejects_non_oauth_profile(config_path) -> None:
    config = cfg.load()
    profile = config.get_profile("default")
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_x"
    config.set_profile(profile)
    cfg.save(config)
    with pytest.raises(UsageError):
        oauth.refresh_id_token("default")


def test_refresh_persists_new_id_token(config_path, monkeypatch) -> None:
    store_oauth_tokens(
        "default",
        id_token="old_id",
        refresh_token="refr_1",
        expires_at=time.time() - 10,
        api_base="https://api.test.omi.local",
    )

    captured: dict = {}

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        return httpx.Response(
            200,
            json={"id_token": "new_id_token", "refresh_token": "refr_1", "expires_in": "3600"},
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    new = oauth.refresh_id_token("default")
    assert new == "new_id_token"
    assert captured["data"] == {"grant_type": "refresh_token", "refresh_token": "refr_1"}

    reloaded = cfg.load().get_profile("default")
    assert reloaded.id_token == "new_id_token"
    assert reloaded.refresh_token == "refr_1"
    # Expiry should be roughly now + 3600 - margin (60).
    assert abs((reloaded.id_token_expires_at or 0) - (time.time() + 3540)) < 5


def test_refresh_persists_rotated_refresh_token(config_path, monkeypatch) -> None:
    store_oauth_tokens(
        "default",
        id_token="old_id",
        refresh_token="refr_old",
        expires_at=time.time() - 10,
        api_base="https://api.test.omi.local",
    )

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(
            200,
            json={"id_token": "new_id", "refresh_token": "refr_new_rotated", "expires_in": "3600"},
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    oauth.refresh_id_token("default")

    reloaded = cfg.load().get_profile("default")
    assert reloaded.id_token == "new_id"
    assert reloaded.refresh_token == "refr_new_rotated"


def test_refresh_surfaces_firebase_error(config_path, monkeypatch) -> None:
    store_oauth_tokens(
        "default",
        id_token="old_id",
        refresh_token="refr_bad",
        expires_at=time.time() - 10,
        api_base="https://api.test.omi.local",
    )

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(401, json={"error": {"message": "INVALID_REFRESH_TOKEN"}})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    with pytest.raises(AuthError) as info:
        oauth.refresh_id_token("default")
    assert "401" in str(info.value)


# ---- login_with_browser surface ------------------------------------------


def test_login_with_browser_rejects_unknown_provider(config_path) -> None:
    with pytest.raises(UsageError):
        oauth.login_with_browser(
            "default",
            api_base="https://api.test.omi.local",
            provider="microsoft",  # unsupported
            open_browser=False,
        )


# ---- code-exchange wiring -------------------------------------------------


def test_exchange_code_for_custom_token_happy_path(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        return httpx.Response(200, json={"custom_token": "ct_abc", "id_token": "google_id"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    token = oauth._exchange_code_for_custom_token(
        "https://api.test.omi.local",
        code="auth_code",
        redirect_uri="http://127.0.0.1:5555/callback",
    )
    assert token == "ct_abc"
    assert captured["url"] == "https://api.test.omi.local/v1/auth/token"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["use_custom_token"] == "true"


def test_exchange_code_raises_on_non_200(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(400, json={"detail": "Invalid or expired code"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    with pytest.raises(AuthError):
        oauth._exchange_code_for_custom_token(
            "https://api.test.omi.local", code="bad", redirect_uri="http://127.0.0.1:5555/callback"
        )


def test_exchange_code_raises_when_custom_token_missing(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"id_token": "google_only", "access_token": "g"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    with pytest.raises(AuthError) as info:
        oauth._exchange_code_for_custom_token(
            "https://api.test.omi.local", code="ok", redirect_uri="http://127.0.0.1:5555/callback"
        )
    assert "custom token" in str(info.value).lower()


def test_firebase_signin_with_custom_token_returns_tokens(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        assert "signInWithCustomToken" in url
        return httpx.Response(
            200,
            json={"idToken": "fb_id", "refreshToken": "fb_refr", "expiresIn": "3600"},
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    id_token, refresh_token, expires_in = oauth._firebase_signin_with_custom_token("ct")
    assert id_token == "fb_id"
    assert refresh_token == "fb_refr"
    assert expires_in == 3600


def test_firebase_signin_raises_on_missing_tokens(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"idToken": "fb_id"})  # missing refreshToken

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    with pytest.raises(AuthError):
        oauth._firebase_signin_with_custom_token("ct")
