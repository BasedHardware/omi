"""Resilience tests for the OAuth token exchange/refresh and the local webhook receiver.

Every failure the hardening for issue #22546 introduced a branch for is covered
here:

* ``httpx.HTTPError`` on any of the four token endpoints becomes a
  :class:`TransportError` (exit code 3) instead of a raw traceback.
* A ``200`` response whose body is not a JSON object becomes an
  :class:`AuthError` (exit code 2) instead of ``JSONDecodeError`` /
  ``AttributeError``.
* ``expires_in`` / ``expiresIn`` values that are missing, boolean, non-numeric
  or non-positive fall back to 3600 seconds.
* Token strings are type-checked and stripped before they are persisted, so a
  whitespace-only token can no longer overwrite stored credentials.
* ``Content-Length`` headers that are missing, non-integer or negative are
  clamped to ``0`` by the local receiver.
* A failing ``HTTPServer`` bind becomes a :class:`UsageError` (exit code 1).
"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any, Optional

import httpx
import pytest
import typer
from click import Command

from omi_cli import config as cfg
from omi_cli.auth import oauth
from omi_cli.auth.store import store_oauth_tokens
from omi_cli.commands import app as app_cmd
from omi_cli.errors import EXIT_AUTH, EXIT_SERVER, EXIT_USAGE, AuthError, TransportError, UsageError
from omi_cli.main import AppContext, app
from omi_cli.output import Renderer

FAKE_API_BASE = "https://api.test.omi.local"

# Every transport-level failure httpx can raise while a token call is in flight.
TRANSPORT_ERRORS = [
    httpx.ConnectError("connection refused"),
    httpx.TimeoutException("timed out"),
    httpx.ReadTimeout("read timed out"),
    httpx.RemoteProtocolError("server disconnected"),
]

# 200 bodies that decode to JSON but are not an object.
NON_OBJECT_BODIES = [
    [],
    ["a", "b"],
    "just a string",
    42,
    3.5,
    True,
    None,
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _non_object_response(payload: Any) -> httpx.Response:
    """A 200 response whose body is valid JSON but not a JSON object."""
    return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))


def _oauth_profile() -> None:
    """Seed the default profile with a stale OAuth session."""
    store_oauth_tokens(
        "default",
        id_token="old_id",
        refresh_token="refr_1",
        expires_at=time.time() - 10,
        api_base=FAKE_API_BASE,
    )


# ---------------------------------------------------------------------------
# _parse_json_object
# ---------------------------------------------------------------------------


def test_parse_json_object_returns_the_decoded_object() -> None:
    resp = httpx.Response(200, json={"id_token": "abc"})

    assert oauth._parse_json_object(resp, "Firebase refresh") == {"id_token": "abc"}


def test_parse_json_object_rejects_a_body_that_is_not_json() -> None:
    """A proxy's HTML error page must not raise a raw JSONDecodeError."""
    resp = httpx.Response(200, text="<html><body>502 Bad Gateway</body></html>")

    with pytest.raises(AuthError) as info:
        oauth._parse_json_object(resp, "Firebase refresh")

    assert "invalid json" in str(info.value).lower()
    assert info.value.exit_code == EXIT_AUTH


def test_parse_json_object_rejects_an_empty_body() -> None:
    resp = httpx.Response(200, content=b"")

    with pytest.raises(AuthError):
        oauth._parse_json_object(resp, "Firebase refresh")


@pytest.mark.parametrize("payload", NON_OBJECT_BODIES)
def test_parse_json_object_rejects_a_json_body_that_is_not_an_object(payload: Any) -> None:
    resp = _non_object_response(payload)

    with pytest.raises(AuthError) as info:
        oauth._parse_json_object(resp, "Firebase refresh")

    assert "unexpected json shape" in str(info.value).lower()
    assert info.value.exit_code == EXIT_AUTH


def test_parse_json_object_names_the_calling_endpoint() -> None:
    resp = httpx.Response(200, json=[])

    with pytest.raises(AuthError) as info:
        oauth._parse_json_object(resp, "OAuth token exchange")

    assert "oauth token exchange" in str(info.value).lower()


# ---------------------------------------------------------------------------
# _parse_expires_in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, True, False, "abc", "", "  ", 0, -1, -3600, "0", "-1", [1]])
def test_parse_expires_in_falls_back_to_the_default_for_unusable_values(value: Any) -> None:
    assert oauth._parse_expires_in(value) == 3600


@pytest.mark.parametrize(
    "value,expected",
    [
        (3600, 3600),
        ("3600", 3600),
        (" 1800 ", 1800),
        (60, 60),
        (60.9, 60),
        (900.0, 900),
    ],
)
def test_parse_expires_in_keeps_a_usable_value(value: Any, expected: int) -> None:
    assert oauth._parse_expires_in(value) == expected


def test_parse_expires_in_honours_a_caller_supplied_default() -> None:
    assert oauth._parse_expires_in(None, default=60) == 60
    assert oauth._parse_expires_in("abc", default=60) == 60
    assert oauth._parse_expires_in(-1, default=60) == 60
    assert oauth._parse_expires_in(True, default=60) == 60


# ---------------------------------------------------------------------------
# httpx.HTTPError -> TransportError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error", TRANSPORT_ERRORS)
def test_refresh_maps_a_transport_failure_to_a_transport_error(config_path, monkeypatch, error: Exception) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        raise error

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(TransportError) as info:
        oauth.refresh_id_token("default")

    assert info.value.exit_code == EXIT_SERVER
    # The stored session must survive a failed refresh untouched.
    reloaded = cfg.load().get_profile("default")
    assert reloaded.id_token == "old_id"


@pytest.mark.parametrize("error", TRANSPORT_ERRORS)
def test_code_exchange_maps_a_transport_failure_to_a_transport_error(monkeypatch, error: Exception) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        raise error

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(TransportError) as info:
        oauth._exchange_code_for_custom_token(
            FAKE_API_BASE,
            code="auth_code",
            redirect_uri="http://127.0.0.1:5555/callback",
            code_verifier="verifier-123",
        )

    assert info.value.exit_code == EXIT_SERVER


@pytest.mark.parametrize("error", TRANSPORT_ERRORS)
def test_firebase_signin_maps_a_transport_failure_to_a_transport_error(monkeypatch, error: Exception) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        raise error

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(TransportError) as info:
        oauth._firebase_signin_with_custom_token("ct")

    assert info.value.exit_code == EXIT_SERVER


@pytest.mark.parametrize("error", TRANSPORT_ERRORS)
def test_dev_key_exchange_maps_a_transport_failure_to_a_transport_error(monkeypatch, error: Exception) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        raise error

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(TransportError) as info:
        oauth._exchange_firebase_token_for_dev_key(FAKE_API_BASE, "fb_id_tok")

    assert info.value.exit_code == EXIT_SERVER


# ---------------------------------------------------------------------------
# 200 responses whose body is not a JSON object
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", NON_OBJECT_BODIES)
def test_refresh_rejects_a_200_body_that_is_not_a_json_object(config_path, monkeypatch, payload: Any) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return _non_object_response(payload)

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError) as info:
        oauth.refresh_id_token("default")

    assert info.value.exit_code == EXIT_AUTH


def test_refresh_rejects_a_200_body_that_is_not_json(config_path, monkeypatch) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, text="<html>login required</html>")

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth.refresh_id_token("default")


@pytest.mark.parametrize("payload", NON_OBJECT_BODIES)
def test_code_exchange_rejects_a_200_body_that_is_not_a_json_object(monkeypatch, payload: Any) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return _non_object_response(payload)

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError) as info:
        oauth._exchange_code_for_custom_token(
            FAKE_API_BASE,
            code="auth_code",
            redirect_uri="http://127.0.0.1:5555/callback",
            code_verifier="verifier-123",
        )

    assert info.value.exit_code == EXIT_AUTH


@pytest.mark.parametrize("payload", NON_OBJECT_BODIES)
def test_firebase_signin_rejects_a_200_body_that_is_not_a_json_object(monkeypatch, payload: Any) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return _non_object_response(payload)

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError) as info:
        oauth._firebase_signin_with_custom_token("ct")

    assert info.value.exit_code == EXIT_AUTH


@pytest.mark.parametrize("payload", NON_OBJECT_BODIES)
def test_dev_key_exchange_rejects_a_200_body_that_is_not_a_json_object(monkeypatch, payload: Any) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return _non_object_response(payload)

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError) as info:
        oauth._exchange_firebase_token_for_dev_key(FAKE_API_BASE, "fb_id_tok")

    assert info.value.exit_code == EXIT_AUTH


# ---------------------------------------------------------------------------
# Whitespace-only / non-string tokens are rejected before they are persisted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["   ", "\t", "\n", " \n\t "])
def test_refresh_rejects_a_whitespace_only_id_token(config_path, monkeypatch, token: str) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"id_token": token, "refresh_token": "refr_1", "expires_in": "3600"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth.refresh_id_token("default")

    # The blank token never reached the profile.
    reloaded = cfg.load().get_profile("default")
    assert reloaded.id_token == "old_id"


@pytest.mark.parametrize("token", [123, None, True, ["t"], {"t": 1}])
def test_refresh_rejects_a_non_string_id_token(config_path, monkeypatch, token: Any) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"id_token": token, "refresh_token": "refr_1", "expires_in": "3600"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth.refresh_id_token("default")

    reloaded = cfg.load().get_profile("default")
    assert reloaded.id_token == "old_id"


def test_refresh_rejects_a_missing_id_token(config_path, monkeypatch) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"refresh_token": "refr_1", "expires_in": "3600"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth.refresh_id_token("default")

    reloaded = cfg.load().get_profile("default")
    assert reloaded.id_token == "old_id"


def test_refresh_keeps_the_stored_refresh_token_when_the_new_one_is_blank(config_path, monkeypatch) -> None:
    """A blank refresh token must not wipe the token we still need."""
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"id_token": "new_id", "refresh_token": "   ", "expires_in": "3600"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    oauth.refresh_id_token("default")

    reloaded = cfg.load().get_profile("default")
    assert reloaded.id_token == "new_id"
    assert reloaded.refresh_token == "refr_1"


@pytest.mark.parametrize("token", ["   ", "\t\n"])
def test_firebase_signin_rejects_a_whitespace_only_id_token(monkeypatch, token: str) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"idToken": token, "refreshToken": "fb_refr", "expiresIn": "3600"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth._firebase_signin_with_custom_token("ct")


def test_firebase_signin_rejects_a_whitespace_only_refresh_token(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"idToken": "fb_id", "refreshToken": "   ", "expiresIn": "3600"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth._firebase_signin_with_custom_token("ct")


@pytest.mark.parametrize("token", [42, None, True, ["t"]])
def test_firebase_signin_rejects_a_non_string_token(monkeypatch, token: Any) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"idToken": token, "refreshToken": "fb_refr", "expiresIn": "3600"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth._firebase_signin_with_custom_token("ct")


def test_code_exchange_rejects_a_whitespace_only_custom_token(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"custom_token": "   "})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth._exchange_code_for_custom_token(
            FAKE_API_BASE,
            code="auth_code",
            redirect_uri="http://127.0.0.1:5555/callback",
            code_verifier="verifier-123",
        )


def test_dev_key_exchange_rejects_a_whitespace_only_key(monkeypatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"key": "   "})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth._exchange_firebase_token_for_dev_key(FAKE_API_BASE, "fb_id_tok")


def test_dev_key_exchange_rejects_a_non_string_key(monkeypatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=[])

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"key": 12345})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with pytest.raises(AuthError):
        oauth._exchange_firebase_token_for_dev_key(FAKE_API_BASE, "fb_id_tok")


# ---------------------------------------------------------------------------
# expires_in handling through the refresh flow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expires_in", [None, True, False, "abc", 0, -1, -3600, "", "not-a-number"])
def test_refresh_uses_a_safe_expiry_when_the_server_sends_a_bad_expires_in(
    config_path, monkeypatch, expires_in: Any
) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(
            200,
            json={"id_token": "new_id", "refresh_token": "refr_1", "expires_in": expires_in},
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    oauth.refresh_id_token("default")

    reloaded = cfg.load().get_profile("default")
    # now + 3600 - the 60s refresh margin.
    assert abs((reloaded.id_token_expires_at or 0) - (time.time() + 3540)) < 5


def test_refresh_uses_a_safe_expiry_when_the_server_omits_expires_in(config_path, monkeypatch) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"id_token": "new_id", "refresh_token": "refr_1"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    oauth.refresh_id_token("default")

    reloaded = cfg.load().get_profile("default")
    assert abs((reloaded.id_token_expires_at or 0) - (time.time() + 3540)) < 5


def test_refresh_honours_a_numeric_expires_in(config_path, monkeypatch) -> None:
    _oauth_profile()

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(
            200,
            json={"id_token": "new_id", "refresh_token": "refr_1", "expires_in": "1800"},
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    oauth.refresh_id_token("default")

    reloaded = cfg.load().get_profile("default")
    assert abs((reloaded.id_token_expires_at or 0) - (time.time() + 1740)) < 5


def test_firebase_signin_uses_a_safe_expiry_for_a_bad_expires_in(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(
            200,
            json={"idToken": "fb_id", "refreshToken": "fb_refr", "expiresIn": "abc"},
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    _, _, expires_in = oauth._firebase_signin_with_custom_token("ct")

    assert expires_in == 3600


# ---------------------------------------------------------------------------
# Stale dev-key cleanup must not assume a list of dicts
# ---------------------------------------------------------------------------


def test_dev_key_exchange_survives_a_listing_that_is_not_a_list(monkeypatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"unexpected": "object"})

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"key": "omi_dev_minted"})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    assert oauth._exchange_firebase_token_for_dev_key(FAKE_API_BASE, "tok") == "omi_dev_minted"


def test_dev_key_exchange_survives_a_listing_that_is_not_json(monkeypatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, text="<html>not json</html>")

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"key": "omi_dev_minted"})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    assert oauth._exchange_firebase_token_for_dev_key(FAKE_API_BASE, "tok") == "omi_dev_minted"


def test_dev_key_exchange_ignores_non_dict_entries_in_the_listing(monkeypatch) -> None:
    deleted: list[str] = []

    def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=["not-a-dict", 42, None, {"name": "someone else's key"}])

    def fake_delete(self, url, **kwargs):  # noqa: ANN001
        deleted.append(url)
        return httpx.Response(204)

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json={"key": "omi_dev_minted"})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "delete", fake_delete)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    assert oauth._exchange_firebase_token_for_dev_key(FAKE_API_BASE, "tok") == "omi_dev_minted"
    assert deleted == []


# ---------------------------------------------------------------------------
# _parse_content_length
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [None, "", "   ", "abc", "12abc", "1.5", "0.0", "-1", "-999", "0", "+", "0x10"],
)
def test_parse_content_length_clamps_unusable_headers_to_zero(header: Optional[str]) -> None:
    assert app_cmd._parse_content_length(header) == 0


@pytest.mark.parametrize(
    "header,expected",
    [("42", 42), (" 42 ", 42), ("+7", 7), ("1000000", 1000000), ("0", 0)],
)
def test_parse_content_length_keeps_a_valid_length(header: str, expected: int) -> None:
    assert app_cmd._parse_content_length(header) == expected


# ---------------------------------------------------------------------------
# A failing bind becomes a UsageError (exit code 1)
# ---------------------------------------------------------------------------


def test_serve_reports_a_bind_failure_as_a_usage_error(cli_runner, config_path, monkeypatch) -> None:
    def boom(*args, **kwargs):  # noqa: ANN001
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(app_cmd, "HTTPServer", boom)

    result = cli_runner.invoke(app, ["app", "serve", "--port", "8787"])

    assert result.exit_code == EXIT_USAGE
    assert "Could not bind" in result.stderr
    assert "127.0.0.1:8787" in result.stderr


def test_serve_raises_a_usage_error_when_the_port_is_taken(config_path) -> None:
    """The real kernel error has to reach the user as a UsageError, not a traceback."""
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = int(occupied.getsockname()[1])
        context = typer.Context(
            Command("serve"),
            obj=AppContext(
                profile_name="default",
                api_base_override=None,
                renderer=Renderer(),
                verbose=False,
            ),
        )

        with pytest.raises(UsageError) as info:
            app_cmd.serve(context, port=port, host="127.0.0.1", status=200, reply="{}", requests=1)

    assert info.value.exit_code == EXIT_USAGE
    assert "Could not bind" in str(info.value)
    assert str(port) in str(info.value)


# ---------------------------------------------------------------------------
# The receiver itself must survive a broken Content-Length header
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("content_length", ["abc", "-5", "0", "not-a-number"])
def test_serve_ignores_a_broken_content_length(cli_runner, config_path, content_length: str) -> None:
    """A negative length used to reach rfile.read(), which reads until EOF."""
    port = _free_port()
    captured: dict[str, Any] = {}

    def deliver() -> None:
        request = (
            "POST /webhook HTTP/1.0\r\n"
            "Host: localhost\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {content_length}\r\n"
            "\r\n"
        ).encode("ascii")
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                chunks: list[str] = []
                with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                    sock.sendall(request)
                    sock.settimeout(5)
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        chunks.append(chunk.decode("utf-8", "replace"))
                captured["response"] = "".join(chunks)
                return
            except OSError:
                time.sleep(0.05)

    sender = threading.Thread(target=deliver, daemon=True)
    sender.start()
    result = cli_runner.invoke(app, ["--json", "app", "serve", "--port", str(port), "--requests", "1"])
    sender.join(timeout=10)

    assert result.exit_code == 0, result.output
    assert "200" in (captured.get("response") or "")
    received = json.loads(result.stdout)
    assert received[0]["bytes"] == 0
