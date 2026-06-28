"""Regression tests for the /setup error path leaking the access_token.

Mirrors plugins/omi-telegram-app/test/test_setup_token_leak.py in structure
and intent. The Telegram plugin's blocker was that httpx.HTTPStatusError.__str__
includes the full request URL, which contains the bot token. For WhatsApp, the
analogous concern is that:
- The access_token is in the Authorization HEADER (not URL), so URL-based leaks
  don't expose it directly.
- BUT we still want to ensure the access_token never appears in logs or in
  the 502 detail body, for defense in depth.

These tests verify the access_token never appears in:
- The response body of the 502 (regardless of the underlying httpx error type).
- Any log record emitted during /setup error paths.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

_PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
from conftest import load_main_module

main = load_main_module()


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    from conftest import load_simple_storage

    simple_storage = load_simple_storage()

    monkeypatch.setattr(simple_storage, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(simple_storage, "USERS_FILE", os.path.join(str(tmp_path), "users_data.json"))
    monkeypatch.setattr(simple_storage, "PENDING_FILE", os.path.join(str(tmp_path), "pending_setups.json"))
    monkeypatch.setattr(simple_storage, "users", {})
    monkeypatch.setattr(simple_storage, "pending_setups", {})
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(main.app)


# The access_token we MUST NOT see anywhere in logs or response bodies.
SECRET_TOKEN = "EAASECRET_ACCESS_TOKEN_DO_NOT_LOG_abc123def456"


def _setup_payload():
    return {
        "access_token": SECRET_TOKEN,
        "phone_number_id": "15550001111",
        "verify_token": "VT_1",
        "omi_uid": "u1",
        "persona_id": "p1",
        "omi_dev_api_key": "DEV_KEY_xyz",
        "public_base_url": "https://clone.example.com",
    }


def _build_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Construct an httpx.HTTPStatusError whose __str__ includes a URL.

    Real httpx.HTTPStatusError stores the request URL in its message — when
    the exception is converted via str(e) it leaks the URL. This mirrors
    the test fixture used in the Telegram plugin's regression tests.
    """
    request = httpx.Request("POST", "https://graph.facebook.com/v22.0/15550001111/subscribed_apps")
    response = httpx.Response(status_code, request=request)
    # The stringified form (httpx 0.27) looks like:
    #   "403 Client Error: Forbidden for url: https://graph.facebook.com/..."
    return httpx.HTTPStatusError(
        f"{status_code} Client Error: Forbidden for url: {request.url}",
        request=request,
        response=response,
    )


class TestSetupAccessTokenLeak:
    """Verify the access_token never leaks in response bodies or logs."""

    def test_subscribe_app_http_error_does_not_leak_token_in_response(self, client, caplog):
        """502 response body must not contain the access_token."""
        err = _build_status_error(403)
        with patch("main.whatsapp_client.subscribe_app", new=AsyncMock(side_effect=err)):
            with caplog.at_level(logging.ERROR, logger="omi-whatsapp-clone"):
                r = client.post("/setup", json=_setup_payload())

        assert r.status_code == 502
        assert SECRET_TOKEN not in r.text

    def test_subscribe_app_http_error_does_not_leak_token_in_logs(self, client, caplog):
        """Log records must not contain the access_token."""
        err = _build_status_error(401)
        with patch("main.whatsapp_client.subscribe_app", new=AsyncMock(side_effect=err)):
            with caplog.at_level(logging.ERROR, logger="omi-whatsapp-clone"):
                client.post("/setup", json=_setup_payload())

        for record in caplog.records:
            assert SECRET_TOKEN not in record.getMessage(), f"Token leaked in log: {record.getMessage()}"

    def test_subscribe_app_generic_http_error_does_not_leak_token_in_response(self, client, caplog):
        """ConnectError/Timeout (no status_code) — still must not leak token."""
        err = httpx.ConnectError(
            "boom", request=httpx.Request("POST", "https://graph.facebook.com/v22.0/x/subscribed_apps")
        )
        with patch("main.whatsapp_client.subscribe_app", new=AsyncMock(side_effect=err)):
            with caplog.at_level(logging.ERROR, logger="omi-whatsapp-clone"):
                r = client.post("/setup", json=_setup_payload())

        assert r.status_code == 502
        assert SECRET_TOKEN not in r.text
        for record in caplog.records:
            assert SECRET_TOKEN not in record.getMessage()

    def test_subscribe_app_http_error_does_not_leak_token_in_logs_all_loggers(self, client, caplog):
        """Same as test #2 but uses caplog propagation for thorough assertion.

        Validates that no log record (across all loggers, not just our app's
        logger) contains the access_token, since httpx's internals sometimes
        log via their own logger.
        """
        err = _build_status_error(500)
        with patch("main.whatsapp_client.subscribe_app", new=AsyncMock(side_effect=err)):
            with caplog.at_level(logging.ERROR):
                client.post("/setup", json=_setup_payload())

        for record in caplog.records:
            assert SECRET_TOKEN not in record.getMessage(), f"Token leaked in {record.name}: {record.getMessage()}"


class TestSetupHappyPath:
    """Verify the happy path: subscribed_apps succeeds, deep link is well-formed."""

    def test_setup_returns_deep_link_and_saves_pending(self, client):
        from conftest import load_simple_storage

        simple_storage = load_simple_storage()

        fake_phone_info = {"display_phone_number": "15550001111", "verified_name": "Test"}

        async def fake_subscribe(phone_number_id, access_token):
            return {"success": True}

        async def fake_get_info(phone_number_id, access_token):
            return fake_phone_info

        with patch("main.whatsapp_client.subscribe_app", new=AsyncMock(side_effect=fake_subscribe)):
            with patch("main.whatsapp_client.get_phone_number_info", new=AsyncMock(side_effect=fake_get_info)):
                r = client.post("/setup", json=_setup_payload())

        assert r.status_code == 200
        body = r.json()
        assert body["phone_number_id"] == "15550001111"
        # Deep link format: https://wa.me/<phone>?text=/start%20<token>
        assert body["deep_link"].startswith("https://wa.me/15550001111?text=")
        # URL-encoded "/start " becomes %2Fstart%20
        assert "%2Fstart" in body["deep_link"] or "/start" in body["deep_link"]
        # Pending setup was stored
        assert len(simple_storage.pending_setups) == 1
        stored_token, stored_payload = list(simple_storage.pending_setups.items())[0]
        assert stored_payload["access_token"] == SECRET_TOKEN
        assert stored_payload["phone_number_id"] == "15550001111"
        assert stored_payload["verify_token"] == "VT_1"

    def test_setup_returns_502_when_get_phone_info_fails(self, client):
        """P1.3 fix: no more fallback to phone_number_id. If we can't fetch a
        real display_phone_number from Meta, the setup fails with a 502 so
        the user knows the deep link would be broken."""

        async def fake_subscribe(phone_number_id, access_token):
            return {"success": True}

        async def fake_get_info(phone_number_id, access_token):
            raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://graph.facebook.com/v22.0/x"))

        with patch("main.whatsapp_client.subscribe_app", new=AsyncMock(side_effect=fake_subscribe)):
            with patch("main.whatsapp_client.get_phone_number_info", new=AsyncMock(side_effect=fake_get_info)):
                r = client.post("/setup", json=_setup_payload())

        assert r.status_code == 502
        # Error message must not leak access_token
        assert SECRET_TOKEN not in r.text
        # Maintainer follow-up: a failed phone lookup must NOT leave orphaned
        # pending_setup data on disk — the verify token would otherwise be
        # useless (no way to bind a phone to it) and could leak access_token
        # bytes to anyone who later enumerates /webhook GET verify_token.
        from conftest import load_simple_storage

        simple_storage = load_simple_storage()

        assert len(simple_storage.pending_setups) == 0, (
            f"Orphaned pending_setup left on disk after /setup failure: "
            f"{list(simple_storage.pending_setups.keys())}"
        )
