"""Tests for the OAuth browser flow + refresh logic."""

from __future__ import annotations

import base64
import hashlib
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


def test_browser_login_status_goes_to_stderr_not_stdout(monkeypatch, capsys) -> None:
    """Human status messages during browser login must not pollute stdout.

    In --json mode stdout carries only the JSON payload, so the
    "Opening browser…" / fallback-URL messages belong on stderr.
    """
    monkeypatch.setattr(oauth.webbrowser, "open", lambda *a, **k: True)
    # Make the OAuth wait time out quickly (right after the status prints)
    # instead of the real 300s, without patching Event.wait globally (that
    # would also affect the server's internal shutdown event).
    monkeypatch.setattr(oauth, "_BROWSER_TIMEOUT_SECONDS", 0.2)

    with pytest.raises(oauth.AuthError):
        oauth.login_with_browser(
            "default",
            api_base="https://api.test.omi.local",
            provider="google",
            open_browser=True,
        )

    captured = capsys.readouterr()
    assert captured.out == "", f"stdout should stay clean, got: {captured.out!r}"
    assert "Opening browser for google sign-in..." in captured.err
    assert "api.test.omi.local" in captured.err


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
        code_verifier="verifier-123",
    )
    assert token == "ct_abc"
    assert captured["url"] == "https://api.test.omi.local/v1/auth/token"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["use_custom_token"] == "true"
    assert captured["data"]["code_verifier"] == "verifier-123"


def test_generate_pkce_pair_uses_s256_challenge() -> None:
    code_verifier, code_challenge = oauth._generate_pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    )
    assert 43 <= len(code_verifier) <= 128
    assert code_challenge == expected


def test_exchange_code_raises_on_non_200(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(400, json={"detail": "Invalid or expired code"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    with pytest.raises(AuthError):
        oauth._exchange_code_for_custom_token(
            "https://api.test.omi.local",
            code="bad",
            redirect_uri="http://127.0.0.1:5555/callback",
            code_verifier="verifier-123",
        )


def test_exchange_code_raises_when_custom_token_missing(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"id_token": "google_only", "access_token": "g"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    with pytest.raises(AuthError) as info:
        oauth._exchange_code_for_custom_token(
            "https://api.test.omi.local",
            code="ok",
            redirect_uri="http://127.0.0.1:5555/callback",
            code_verifier="verifier-123",
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


# ---- Firebase session -> dev API key exchange -----------------------------


def test_exchange_firebase_token_mints_key_and_replaces_own(monkeypatch) -> None:
    calls: dict = {"deleted": [], "post": None}
    name = oauth._cli_key_name()

    def fake_get(self, url, **kwargs):  # noqa: ANN001
        # One key that's ours (exact name match) + one unrelated key.
        return httpx.Response(
            200,
            json=[
                {"id": "ours-1", "name": name},
                {"id": "other", "name": "someone elses key"},
            ],
        )

    def fake_delete(self, url, **kwargs):  # noqa: ANN001
        calls["deleted"].append(url)
        return httpx.Response(204)

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        calls["post"] = (url, kwargs.get("json"), kwargs.get("headers"))
        return httpx.Response(200, json={"id": "new", "name": name, "key": "omi_dev_minted"})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "delete", fake_delete)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    key = oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local/", "fb_id_tok")

    assert key == "omi_dev_minted"
    # Only our own key was deleted; the unrelated one was left alone.
    assert calls["deleted"] == ["https://api.test.omi.local/v1/dev/keys/ours-1"]
    url, body, headers = calls["post"]
    assert url == "https://api.test.omi.local/v1/dev/keys"
    assert body["name"] == name
    assert body["scopes"] == oauth._CLI_KEY_SCOPES
    assert headers["Authorization"] == "Bearer fb_id_tok"


def test_exchange_firebase_token_proceeds_when_listing_fails(monkeypatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError("listing unavailable")

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"key": "omi_dev_after_failed_list"})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    key = oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local", "tok")
    assert key == "omi_dev_after_failed_list"


def test_exchange_firebase_token_raises_on_non_200(monkeypatch) -> None:
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: httpx.Response(200, json=[]))
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: httpx.Response(403, json={"detail": "nope"}))
    with pytest.raises(AuthError) as info:
        oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local", "tok")
    assert "create an api key" in str(info.value).lower()


def test_exchange_firebase_token_raises_when_key_field_missing(monkeypatch) -> None:
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: httpx.Response(200, json=[]))
    monkeypatch.setattr(
        httpx.Client, "post", lambda self, url, **kw: httpx.Response(200, json={"id": "x", "name": "y"})
    )
    with pytest.raises(AuthError) as info:
        oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local", "tok")
    assert "missing the api key" in str(info.value).lower()


def test_failed_mint_keeps_previous_key_on_server_error(monkeypatch) -> None:
    deleted_urls: list[str] = []

    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[{"id": "stale-key-1", "name": oauth._cli_key_name()}])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(503, json={"detail": "synthetic failure"})

    def fake_delete(self, url, **kwargs):  # noqa: ANN001
        deleted_urls.append(url)
        return httpx.Response(204)

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(httpx.Client, "delete", fake_delete)

    with pytest.raises(AuthError):
        oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local", "tok")

    assert not deleted_urls, f"DELETE should not have been called on failed mint, called: {deleted_urls}"


def test_failed_mint_keeps_previous_key_on_missing_key_field(monkeypatch) -> None:
    deleted_urls: list[str] = []

    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[{"id": "stale-key-1", "name": oauth._cli_key_name()}])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(201, json={"id": "minted-no-key", "name": oauth._cli_key_name()})

    def fake_delete(self, url, **kwargs):  # noqa: ANN001
        deleted_urls.append(url)
        return httpx.Response(204)

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(httpx.Client, "delete", fake_delete)

    with pytest.raises(AuthError):
        oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local", "tok")

    assert not deleted_urls, f"DELETE should not have been called when key is missing, called: {deleted_urls}"


def test_failed_mint_keeps_previous_key_on_connect_error(monkeypatch) -> None:
    deleted_urls: list[str] = []

    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[{"id": "stale-key-1", "name": oauth._cli_key_name()}])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError("network unreachable")

    def fake_delete(self, url, **kwargs):  # noqa: ANN001
        deleted_urls.append(url)
        return httpx.Response(204)

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(httpx.Client, "delete", fake_delete)

    with pytest.raises(httpx.ConnectError):
        oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local", "tok")

    assert not deleted_urls, f"DELETE should not have been called on transport failure, called: {deleted_urls}"


def test_successful_mint_deletes_only_premint_snapshot_keys(monkeypatch) -> None:
    deleted_urls: list[str] = []

    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[{"id": "stale-key-1", "name": oauth._cli_key_name()}])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(201, json={"id": "new-key-123", "key": "omi_dev_new", "name": oauth._cli_key_name()})

    def fake_delete(self, url, **kwargs):  # noqa: ANN001
        deleted_urls.append(url)
        return httpx.Response(204)

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(httpx.Client, "delete", fake_delete)

    key = oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local", "tok")
    assert key == "omi_dev_new"
    assert deleted_urls == ["https://api.test.omi.local/v1/dev/keys/stale-key-1"]


def test_successful_mint_skips_cleanup_when_key_id_missing_in_response(monkeypatch) -> None:
    deleted_urls: list[str] = []

    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[{"id": "stale-key-1", "name": oauth._cli_key_name()}])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(201, json={"key": "omi_dev_new", "name": oauth._cli_key_name()})

    def fake_delete(self, url, **kwargs):  # noqa: ANN001
        deleted_urls.append(url)
        return httpx.Response(204)

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(httpx.Client, "delete", fake_delete)

    key = oauth._exchange_firebase_token_for_dev_key("https://api.test.omi.local", "tok")
    assert key == "omi_dev_new"
    assert not deleted_urls, f"DELETE should be skipped when new key ID is missing, called: {deleted_urls}"
