"""Regression test: the bot token must never appear in /setup logs or response.

Triggered by maintainer review: set_webhook / getMe were logging str(httpx_error)
and including it in HTTPException detail. For httpx.HTTPStatusError, the
exception's string representation includes the full request URL — which
contains the bot token. This test simulates a Telegram failure with a
token-bearing URL and asserts the token is not present in either the log
output or the response body.

This is a guard against re-introducing the token-leak path that the reviewer
flagged on PR #8437 (commit f041851a2).
"""

import logging
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_PLUGIN_DIR, ".."))
_SHARED = os.path.abspath(os.path.join(_PLUGIN_ROOT, "..", "_shared"))
for p in (_PLUGIN_ROOT, _SHARED):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def telegram_api_token_url_error():
    """Mock httpx so that set_webhook and get_me raise HTTPStatusError whose
    request URL contains a bot token.

    The HTTPStatusError's __str__ includes 'Client error \'404\' for url
    \'https://api.telegram.org/bot<TOKEN>/...\' — which is exactly what
    leaked into logs/responses before the fix.
    """
    secret_token = "BOT_TOKEN_LEAK_TEST_abc123"  # recognizable string

    def _make_status_error(url_path: str) -> httpx.HTTPStatusError:
        # Construct an HTTPStatusError the way httpx itself does: with the
        # verbose message that includes the full request URL. This is what
        # `response.raise_for_status()` does when Telegram returns 4xx/5xx.
        # The message includes the bot token because the URL includes it.
        url = f"https://api.telegram.org/bot{secret_token}/{url_path}"
        request = httpx.Request("POST", url)
        response = httpx.Response(404, request=request, json={"ok": False, "description": "not found"})
        message = f"404 Client Error: Not Found for url: {url}"
        return httpx.HTTPStatusError(message, request=request, response=response)

    # AsyncClient whose .post() always raises the status error.
    # AsyncMock needs an *async* side_effect function for it to raise on
    # call — sync functions get auto-awaited and their return values are
    # returned, not raised. We use async functions that raise.
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    async def _side_effect(url, **kwargs):
        if "setWebhook" in url:
            raise _make_status_error("setWebhook")
        raise _make_status_error("getMe")

    client.post = AsyncMock(side_effect=_side_effect)

    return {"client": client, "secret_token": secret_token}


def _post_setup() -> dict:
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    return client.post(
        "/setup",
        json={
            "bot_token": "BOT_TOKEN_LEAK_TEST_abc123",
            "omi_uid": "u-1",
            "persona_id": "p-1",
            "omi_dev_api_key": "k",
            "public_base_url": "https://clone.example.com",
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestSetupTokenLeak:
    def test_set_webhook_failure_does_not_leak_token_in_response(self, telegram_api_token_url_error, caplog):
        with patch("telegram_client.httpx.AsyncClient", return_value=telegram_api_token_url_error["client"]), patch(
            "telegram_client._get_client", return_value=telegram_api_token_url_error["client"]
        ):
            with caplog.at_level(logging.ERROR, logger="omi-telegram-clone"):
                resp = _post_setup()

        assert resp.status_code == 502
        body_text = resp.text
        assert "BOT_TOKEN_LEAK_TEST_abc123" not in body_text, f"bot token leaked into response body: {body_text}"
        # Sanity: the generic detail IS there
        assert "Telegram setWebhook failed" in body_text

    def test_set_webhook_failure_does_not_leak_token_in_logs(self, telegram_api_token_url_error, caplog):
        with patch("telegram_client.httpx.AsyncClient", return_value=telegram_api_token_url_error["client"]), patch(
            "telegram_client._get_client", return_value=telegram_api_token_url_error["client"]
        ):
            with caplog.at_level(logging.ERROR, logger="omi-telegram-clone"):
                _post_setup()

        # Walk all log records; the token must not appear anywhere.
        token = telegram_api_token_url_error["secret_token"]
        leaked = [r for r in caplog.records if token in r.getMessage()]
        assert not leaked, f"bot token leaked into logs: {[r.getMessage() for r in leaked]}"

    def test_getme_failure_does_not_leak_token_in_response(self, telegram_api_token_url_error, caplog):
        """When setWebhook succeeds but getMe fails, the error path must still
        not leak. This is the second half of the setup flow."""

        # Build a client where setWebhook succeeds but getMe raises.
        # We reuse the fixture's client but make its first post() succeed
        # (setWebhook) and second post() fail (getMe).

        success_resp = httpx.Response(
            200,
            json={"ok": True, "result": True},
            request=httpx.Request("POST", "https://api.telegram.org/bot/X/setWebhook"),
        )

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        async def _post(url, **kwargs):
            if "setWebhook" in url:
                return success_resp
            # getMe path — raise the same kind of error, with URL-containing message
            token = "BOT_TOKEN_LEAK_TEST_abc123"
            err_url = f"https://api.telegram.org/bot{token}/getMe"
            request = httpx.Request("POST", err_url)
            response = httpx.Response(401, request=request, json={"ok": False})
            message = f"401 Client Error: Unauthorized for url: {err_url}"
            raise httpx.HTTPStatusError(message, request=request, response=response)

        client.post = AsyncMock(side_effect=_post)

        with patch("telegram_client.httpx.AsyncClient", return_value=client), patch(
            "telegram_client._get_client", return_value=client
        ):
            from fastapi.testclient import TestClient

            from main import app

            with caplog.at_level(logging.ERROR, logger="omi-telegram-clone"):
                resp = TestClient(app).post(
                    "/setup",
                    json={
                        "bot_token": "BOT_TOKEN_LEAK_TEST_abc123",
                        "omi_uid": "u-1",
                        "persona_id": "p-1",
                        "omi_dev_api_key": "k",
                        "public_base_url": "https://clone.example.com",
                    },
                )

        assert resp.status_code == 502
        body_text = resp.text
        assert "BOT_TOKEN_LEAK_TEST_abc123" not in body_text, f"bot token leaked into response body: {body_text}"
        # Sanity: the generic detail IS there
        assert "Telegram getMe failed" in body_text

        # Logs
        token = "BOT_TOKEN_LEAK_TEST_abc123"
        leaked = [r for r in caplog.records if token in r.getMessage()]
        assert not leaked, f"bot token leaked into logs: {[r.getMessage() for r in leaked]}"

    def test_non_status_http_error_does_not_leak_token(self, telegram_api_token_url_error, caplog):
        """Even non-HTTPStatusError exceptions (ConnectError, TimeoutException)
        should not include str(e) — its repr may include the request URL too
        in some httpx versions."""

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        token = "BOT_TOKEN_LEAK_TEST_abc123"
        url = f"https://api.telegram.org/bot{token}/setWebhook"

        async def _connect_error(url, **kwargs):
            raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

        client.post = AsyncMock(side_effect=_connect_error)

        with patch("telegram_client.httpx.AsyncClient", return_value=client), patch(
            "telegram_client._get_client", return_value=client
        ):
            with caplog.at_level(logging.ERROR, logger="omi-telegram-clone"):
                resp = _post_setup()

        assert resp.status_code == 502
        assert "BOT_TOKEN_LEAK_TEST_abc123" not in resp.text
        # And not in logs
        leaked = [r for r in caplog.records if token in r.getMessage()]
        assert not leaked
