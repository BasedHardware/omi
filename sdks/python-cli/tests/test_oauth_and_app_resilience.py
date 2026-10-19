"""Resilience tests for OAuth token exchange/refresh and local webhook receiver."""

from __future__ import annotations

import socket
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from omi_cli import config as cfg
from omi_cli.auth import oauth
from omi_cli.auth.store import store_oauth_tokens
from omi_cli.commands import app as app_cmd
from omi_cli.errors import AuthError, TransportError
from omi_cli.main import app

# ---- _parse_expires_in & _parse_json_object --------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("7200", 7200),
        ("  1800  ", 1800),
        (900, 900),
        (None, 3600),
        ("", 3600),
        ("not-an-int", 3600),
        ("0", 3600),
        ("-60", 3600),
        (True, 3600),
        (False, 3600),
        ([], 3600),
    ],
)
def test_parse_expires_in_coerces_valid_and_falls_back_on_invalid(raw: Any, expected: int) -> None:
    assert oauth._parse_expires_in(raw, default=3600) == expected


def test_parse_json_object_rejects_non_json_body() -> None:
    resp = httpx.Response(200, text="<html>bad gateway</html>")
    with pytest.raises(AuthError, match="OAuth test returned invalid JSON"):
        oauth._parse_json_object(resp, "OAuth test")


@pytest.mark.parametrize("payload", [[1, 2, 3], "just-a-string", 42, True])
def test_parse_json_object_rejects_non_dict_json(payload: Any) -> None:
    resp = httpx.Response(200, json=payload)
    with pytest.raises(AuthError, match="OAuth test returned an unexpected JSON shape"):
        oauth._parse_json_object(resp, "OAuth test")


def test_parse_json_object_rejects_json_null() -> None:
    resp = httpx.Response(200, text="null")
    with pytest.raises(AuthError, match="OAuth test returned an unexpected JSON shape"):
        oauth._parse_json_object(resp, "OAuth test")


# ---- refresh_id_token resilience -------------------------------------------


def _seed_oauth_profile() -> None:
    store_oauth_tokens(
        "default",
        id_token="old_id",
        refresh_token="refr_1",
        expires_at=time.time() - 10,
        api_base="https://api.test.omi.local",
    )


def test_refresh_id_token_translates_httpx_error_to_transport_error(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_oauth_profile()

    def boom(self: Any, url: str, **kwargs: Any) -> Any:
        raise httpx.ConnectError("DNS lookup failed")

    monkeypatch.setattr(httpx.Client, "post", boom)

    with pytest.raises(TransportError, match="Could not reach Firebase token service"):
        oauth.refresh_id_token("default")


def test_refresh_id_token_rejects_non_json_200_response(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_oauth_profile()
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(200, text="not json"),
    )

    with pytest.raises(AuthError, match="Firebase refresh returned invalid JSON"):
        oauth.refresh_id_token("default")


def test_refresh_id_token_rejects_blank_id_token(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_oauth_profile()
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(200, json={"id_token": "   ", "expires_in": "3600"}),
    )

    with pytest.raises(AuthError, match="Firebase refresh response was missing id_token"):
        oauth.refresh_id_token("default")


def test_refresh_id_token_falls_back_when_expires_in_malformed(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_oauth_profile()
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(
            200,
            json={"id_token": "  fresh_id  ", "refresh_token": "   ", "expires_in": "invalid"},
        ),
    )

    token = oauth.refresh_id_token("default")
    assert token == "fresh_id"
    reloaded = cfg.load().get_profile("default")
    assert reloaded.id_token == "fresh_id"
    # Blank rotated refresh_token should preserve existing refresh_token "refr_1"
    assert reloaded.refresh_token == "refr_1"
    assert abs((reloaded.id_token_expires_at or 0) - (time.time() + 3540)) < 5


# ---- _exchange_code_for_custom_token resilience ----------------------------


def test_exchange_code_translates_httpx_error_to_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(self: Any, url: str, **kwargs: Any) -> Any:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.Client, "post", boom)

    with pytest.raises(TransportError, match="Could not reach https://api.omi.me/v1/auth/token"):
        oauth._exchange_code_for_custom_token("https://api.omi.me", "code123", "verifier123", "state123")


def test_exchange_code_rejects_non_dict_200_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(200, json=["unexpected"]),
    )

    with pytest.raises(AuthError, match="OAuth token exchange returned an unexpected JSON shape"):
        oauth._exchange_code_for_custom_token("https://api.omi.me", "code123", "verifier123", "state123")


def test_exchange_code_rejects_whitespace_custom_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(200, json={"custom_token": "   "}),
    )

    with pytest.raises(AuthError, match="Server did not return a Firebase custom token"):
        oauth._exchange_code_for_custom_token("https://api.omi.me", "code123", "verifier123", "state123")


# ---- _firebase_signin_with_custom_token resilience -------------------------


def test_firebase_signin_translates_httpx_error_to_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(self: Any, url: str, **kwargs: Any) -> Any:
        raise httpx.ConnectError("connection reset")

    monkeypatch.setattr(httpx.Client, "post", boom)

    with pytest.raises(TransportError, match="Could not reach Firebase sign-in service"):
        oauth._firebase_signin_with_custom_token("custom_tok")


def test_firebase_signin_rejects_missing_or_blank_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(200, json={"idToken": "tok", "refreshToken": "  "}),
    )

    with pytest.raises(AuthError, match="Firebase signin response missing tokens"):
        oauth._firebase_signin_with_custom_token("custom_tok")


def test_firebase_signin_falls_back_on_malformed_expires_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(
            200,
            json={"idToken": " id_1 ", "refreshToken": " ref_1 ", "expiresIn": "bad-ttl"},
        ),
    )

    id_token, refresh_token, expires_in = oauth._firebase_signin_with_custom_token("custom_tok")
    assert id_token == "id_1"
    assert refresh_token == "ref_1"
    assert expires_in == 3600


# ---- _exchange_firebase_token_for_dev_key resilience -----------------------


def test_exchange_dev_key_translates_post_httpx_error_to_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, **kw: httpx.Response(200, json=[]),
    )

    def boom(self: Any, url: str, **kwargs: Any) -> Any:
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx.Client, "post", boom)

    with pytest.raises(TransportError, match="Could not reach https://api.omi.me/v1/dev/keys"):
        oauth._exchange_firebase_token_for_dev_key("https://api.omi.me", "fb_tok")


def test_exchange_dev_key_tolerates_non_json_or_dict_keys_list_before_creating_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Even if GET /v1/dev/keys returns non-list JSON or invalid JSON, key creation still succeeds.
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, **kw: httpx.Response(200, text="<<<not json>>>"),
    )
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(200, json={"key": " omi_dev_new123 "}),
    )

    key = oauth._exchange_firebase_token_for_dev_key("https://api.omi.me", "fb_tok")
    assert key == "omi_dev_new123"


def test_exchange_dev_key_rejects_blank_key_in_200_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, **kw: httpx.Response(200, json={"items": []}),
    )
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda self, url, **kw: httpx.Response(200, json={"key": "   "}),
    )

    with pytest.raises(AuthError, match="Key-mint response was missing the API key"):
        oauth._exchange_firebase_token_for_dev_key("https://api.omi.me", "fb_tok")


# ---- app.py _parse_content_length & serve() resilience ---------------------


@pytest.mark.parametrize(
    "header_val,expected",
    [
        (None, 0),
        ("", 0),
        ("0", 0),
        ("42", 42),
        ("  128  ", 128),
        ("-1", 0),
        ("-999", 0),
        ("invalid", 0),
        ("12.5", 0),
    ],
)
def test_parse_content_length_handles_malformed_and_negative_values(header_val: str | None, expected: int) -> None:
    assert app_cmd._parse_content_length(header_val) == expected


def test_webhook_handler_survives_malformed_and_negative_content_length() -> None:
    records: list[dict[str, Any]] = []
    handler_cls = type(
        "_TestWebhookHandler",
        (app_cmd._WebhookHandler,),
        {"reply_status": 200, "reply_body": b'{"ok":true}', "on_request": staticmethod(records.append)},
    )

    with HTTPServer(("127.0.0.1", 0), handler_cls) as server:
        port = server.server_address[1]

        # Send a raw HTTP/1.0 request with a negative Content-Length header
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(
                b"POST /webhook?uid=test HTTP/1.0\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: -10\r\n"
                b"\r\n"
            )
            server.handle_request()
            raw_reply = sock.recv(4096)

    assert b"200 OK" in raw_reply
    assert len(records) == 1
    assert records[0]["bytes"] == 0
    assert records[0]["query"] == {"uid": "test"}


def test_serve_translates_port_bind_oserror_to_usage_error(
    cli_runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_bind(addr: tuple[str, int], handler: Any) -> Any:
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(app_cmd, "HTTPServer", fail_bind)

    result = cli_runner.invoke(
        app,
        ["app", "serve", "--host", "127.0.0.1", "--port", "8787", "--requests", "1"],
    )

    assert result.exit_code == 1
    assert "Could not bind http://127.0.0.1:8787" in result.stderr
