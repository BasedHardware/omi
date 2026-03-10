"""Tests for auth endpoint redirect_uri validation and callback template rendering."""
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Stub heavy dependencies before importing the module under test
sys.modules.setdefault('firebase_admin', MagicMock())
sys.modules.setdefault('firebase_admin.auth', MagicMock())
sys.modules.setdefault('firebase_admin.firestore', MagicMock())
sys.modules.setdefault('firebase_admin.messaging', MagicMock())
sys.modules.setdefault('google.cloud', MagicMock())
sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())
sys.modules.setdefault('google.auth', MagicMock())
sys.modules.setdefault('google.auth.transport.requests', MagicMock())

from fastapi import FastAPI

from routers.auth import router as auth_router

# Minimal test app mounting only the auth router
_test_app = FastAPI()
_test_app.include_router(auth_router)


# --- /v1/auth/authorize redirect_uri validation ---

class TestAuthorizeRedirectUriValidation:
    """Tests for redirect_uri allowlist at /v1/auth/authorize."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_uri", [
        "https://evil.com/steal",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://example.com",
        "",
    ])
    async def test_rejects_disallowed_redirect_uri(self, bad_uri):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/authorize",
                params={"provider": "google", "redirect_uri": bad_uri, "state": "test"},
            )
        assert resp.status_code == 400
        assert "allowed app URL scheme" in resp.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("good_uri", [
        "omi://auth/callback",
        "omi-computer://auth/callback",
        "omi-computer-dev://auth/callback",
    ])
    @patch("routers.auth.set_auth_session")
    async def test_accepts_allowed_redirect_schemes(self, mock_set_session, good_uri):
        with patch("routers.auth.os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key, *args: {
                "GOOGLE_CLIENT_ID": "test-client-id",
                "GOOGLE_CLIENT_SECRET": "test-secret",
                "BASE_API_URL": "https://api.omi.me",
                "APPLE_CLIENT_ID": "me.omi.web",
                "APPLE_TEAM_ID": "TEST",
                "APPLE_KEY_ID": "TEST",
                "APPLE_PRIVATE_KEY": "TEST",
            }.get(key, args[0] if args else None)

            async with AsyncClient(
                transport=ASGITransport(app=_test_app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await client.get(
                    "/v1/auth/authorize",
                    params={"provider": "google", "redirect_uri": good_uri, "state": "test123"},
                )
            # Should redirect to Google OAuth (307) or return 200, not 400
            assert resp.status_code != 400
            # Verify session was stored with the redirect_uri
            mock_set_session.assert_called_once()
            session_data = mock_set_session.call_args[0][1]
            assert session_data["redirect_uri"] == good_uri

    @pytest.mark.asyncio
    async def test_rejects_missing_redirect_uri(self):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/authorize",
                params={"provider": "google", "state": "test"},
            )
        # FastAPI returns 422 for missing required query param
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_invalid_provider(self):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/authorize",
                params={"provider": "github", "redirect_uri": "omi://auth/callback"},
            )
        assert resp.status_code == 400
        assert "Unsupported provider" in resp.json()["detail"]


# --- Google callback template rendering ---

class TestGoogleCallbackRedirectUri:
    """Tests for redirect_uri in Google OAuth callback template."""

    @pytest.mark.asyncio
    @patch("routers.auth.get_auth_session")
    @patch("routers.auth._exchange_provider_code_for_oauth_credentials", new_callable=AsyncMock)
    @patch("routers.auth.set_auth_code")
    async def test_uses_session_redirect_uri(self, mock_set_code, mock_exchange, mock_get_session):
        mock_get_session.return_value = {
            "provider": "google",
            "redirect_uri": "omi-computer://auth/callback",
            "state": "test_state",
            "flow_type": "user_auth",
        }
        mock_exchange.return_value = '{"id_token": "test"}'

        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/callback/google",
                params={"code": "test_code", "state": "test_state"},
            )
        assert resp.status_code == 200
        body = resp.text
        # Template should contain the desktop redirect scheme
        assert "omi-computer://auth/callback" in body

    @pytest.mark.asyncio
    @patch("routers.auth.get_auth_session")
    @patch("routers.auth._exchange_provider_code_for_oauth_credentials", new_callable=AsyncMock)
    @patch("routers.auth.set_auth_code")
    async def test_falls_back_to_default_redirect_uri(self, mock_set_code, mock_exchange, mock_get_session):
        mock_get_session.return_value = {
            "provider": "google",
            "state": "test_state",
            "flow_type": "user_auth",
            # No redirect_uri in session
        }
        mock_exchange.return_value = '{"id_token": "test"}'

        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/callback/google",
                params={"code": "test_code", "state": "test_state"},
            )
        assert resp.status_code == 200
        body = resp.text
        # Should fall back to omi:// scheme
        assert "omi://auth/callback" in body


# --- Apple callback template rendering ---

class TestAppleCallbackRedirectUri:
    """Tests for redirect_uri in Apple OAuth callback template."""

    @pytest.mark.asyncio
    @patch("routers.auth.get_auth_session")
    @patch("routers.auth._exchange_provider_code_for_oauth_credentials", new_callable=AsyncMock)
    @patch("routers.auth.set_auth_code")
    async def test_uses_session_redirect_uri(self, mock_set_code, mock_exchange, mock_get_session):
        mock_get_session.return_value = {
            "provider": "apple",
            "redirect_uri": "omi-computer://auth/callback",
            "state": "test_state",
            "flow_type": "user_auth",
        }
        mock_exchange.return_value = '{"id_token": "test"}'

        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/auth/callback/apple",
                data={"code": "test_code", "state": "test_state"},
            )
        assert resp.status_code == 200
        body = resp.text
        assert "omi-computer://auth/callback" in body

    @pytest.mark.asyncio
    @patch("routers.auth.get_auth_session")
    @patch("routers.auth._exchange_provider_code_for_oauth_credentials", new_callable=AsyncMock)
    @patch("routers.auth.set_auth_code")
    async def test_falls_back_to_default_redirect_uri(self, mock_set_code, mock_exchange, mock_get_session):
        mock_get_session.return_value = {
            "provider": "apple",
            "state": "test_state",
            "flow_type": "user_auth",
        }
        mock_exchange.return_value = '{"id_token": "test"}'

        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/auth/callback/apple",
                data={"code": "test_code", "state": "test_state"},
            )
        assert resp.status_code == 200
        body = resp.text
        assert "omi://auth/callback" in body


# --- Template XSS safety ---

class TestCallbackTemplateXssSafety:
    """Verify that redirect_uri is safely serialized in the callback template."""

    @pytest.mark.asyncio
    @patch("routers.auth.get_auth_session")
    @patch("routers.auth._exchange_provider_code_for_oauth_credentials", new_callable=AsyncMock)
    @patch("routers.auth.set_auth_code")
    async def test_redirect_uri_json_escaped(self, mock_set_code, mock_exchange, mock_get_session):
        # Use a redirect_uri with quotes to test JSON escaping
        mock_get_session.return_value = {
            "provider": "google",
            "redirect_uri": 'omi://auth/callback"test',
            "state": "test_state",
            "flow_type": "user_auth",
        }
        mock_exchange.return_value = '{"id_token": "test"}'

        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/callback/google",
                params={"code": "test_code", "state": "test_state"},
            )
        assert resp.status_code == 200
        body = resp.text
        # The quote should be JSON-escaped, not raw
        assert r'omi://auth/callback\"test' in body or r'omi:\/\/auth\/callback\"test' in body
        # Should NOT contain unescaped quote that breaks out of the JS string
        assert 'const redirectUri = "omi://auth/callback"test"' not in body
