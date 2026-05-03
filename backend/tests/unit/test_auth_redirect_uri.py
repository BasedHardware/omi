"""Tests for ``backend.routers.auth._validate_redirect_uri``.

The validator must accept every ``redirect_uri`` shape the Omi clients
already use today (mobile, desktop, named-bundle desktop builds, CLI) and
reject anything that could leak the OAuth code off-device. These tests
serve as a regression guard — if the allowlist tightens in a way that
rejects an existing client's URI, CI will fail here before any deploy.

Mapping to real-world clients:

* ``omi://auth/callback``                — Flutter app (``app/lib/services/auth_service.dart``)
* ``omi-computer://auth/callback``       — desktop prod build
* ``omi-computer-dev://auth/callback``   — desktop dev build (``Desktop/Info.plist``)
* ``omi-fix-rewind://auth/callback``     — example named test bundle
* ``com.omi.app://auth/callback``        — reverse-DNS form (RFC 8252-recommended)
* ``http://127.0.0.1:PORT/callback``     — omi-cli loopback server
* ``http://localhost:PORT/callback``     — omi-cli loopback (alt)
* ``http://[::1]:PORT/callback``         — IPv6 loopback
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# Backend modules expect ENCRYPTION_SECRET to be set at import time.
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_test_secret_for_redirect_uri_validation_unit_test_only",
)
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test")
os.environ.setdefault("BASE_API_URL", "http://localhost:8080")

# Pre-mock heavy deps before importing the module under test (Python 3.9 compat —
# database.redis_db uses dict | None syntax that requires 3.10+).
_mock = MagicMock()
for mod in ['firebase_admin.auth', 'database.redis_db', 'utils.http_client', 'utils.log_sanitizer']:
    sys.modules.setdefault(mod, _mock)

# Allow importing ``backend.routers.auth`` without running the full backend
# entrypoint — same trick the rest of tests/unit uses.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from routers.auth import _validate_redirect_uri  # noqa: E402

# ---------------------------------------------------------------------------
# Acceptance — every shape an existing Omi client uses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        # Flutter mobile
        "omi://auth/callback",
        # Desktop prod
        "omi-computer://auth/callback",
        # Desktop dev (Desktop/Info.plist)
        "omi-computer-dev://auth/callback",
        # Named test bundle (CLAUDE.md "omi-{anything}" convention)
        "omi-fix-rewind://auth/callback",
        # Reverse-DNS custom scheme (RFC 8252-recommended)
        "com.omi.app://auth/callback",
        # CLI loopback — IPv4 numeric
        "http://127.0.0.1:8765/callback",
        # CLI loopback — hostname
        "http://localhost:5000/callback",
        # CLI loopback — IPv6
        "http://[::1]:5000/callback",
        # Custom scheme without a path (degenerate but valid)
        "omi://",
        # Custom scheme carrying its own state in the query
        "omi-computer://auth/callback?from=settings",
    ],
)
def test_validator_accepts_every_known_client_shape(uri: str) -> None:
    # Should not raise for anything an Omi client actually sends.
    _validate_redirect_uri(uri)


# ---------------------------------------------------------------------------
# Rejection — every shape a malicious caller might try
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        # Empty / whitespace
        "",
        "   ",
        # Garbage with no scheme
        "auth/callback",
        # https — would leak code off-device
        "https://attacker.example.com/cb",
        "https://localhost/cb",  # https NEVER allowed, even on loopback
        # http — non-loopback hostname rejected
        "http://attacker.example.com/cb",
        "http://omi.me/cb",
        "http://192.168.1.42/cb",
        # Browser-executable schemes
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "blob:http://localhost/abc",
        "filesystem:http://localhost/abc",
        "about:blank",
        # Malformed scheme
        "://x",
        "1omi://auth/callback",  # scheme must start with a letter
        "omi$://auth/callback",  # ``$`` not allowed in scheme
        # Non-ASCII letters: RFC 3986 forbids these in scheme names. Python's
        # ``str.isalpha`` would accept them — we explicitly use ASCII-only.
        "ômi://auth/callback",
        "омi://auth/callback",  # cyrillic 'о'
    ],
)
def test_validator_rejects_dangerous_or_malformed_uris(uri: str) -> None:
    with pytest.raises(HTTPException) as info:
        _validate_redirect_uri(uri)
    assert info.value.status_code == 400


def test_https_is_never_accepted_even_for_loopback() -> None:
    """RFC 8252 §7.3 explicitly mandates HTTP (not HTTPS) for loopback."""
    with pytest.raises(HTTPException):
        _validate_redirect_uri("https://127.0.0.1:5000/callback")


def test_http_remote_host_rejection_message_mentions_loopback() -> None:
    with pytest.raises(HTTPException) as info:
        _validate_redirect_uri("http://attacker.example.com/cb")
    assert "loopback" in info.value.detail.lower()


def test_default_omi_redirect_unchanged() -> None:
    """The mobile app's exact redirect MUST keep working — most-load-bearing case."""
    _validate_redirect_uri("omi://auth/callback")


# ---------------------------------------------------------------------------
# Auth code binding — redirect_uri is stored in the auth code and enforced
# at /v1/auth/token exchange time (#7020)
# ---------------------------------------------------------------------------

import json
from unittest.mock import AsyncMock

from routers.auth import auth_token, _DEFAULT_MOBILE_REDIRECT  # noqa: E402


class TestAuthCodeBinding:
    """Test that auth codes are bound to redirect_uri at token exchange."""

    def test_token_rejects_redirect_uri_mismatch(self):
        """Verify /v1/auth/token returns 400 when redirect_uri doesn't match stored value."""
        code_data = json.dumps(
            {
                'credentials': json.dumps(
                    {
                        'provider': 'google',
                        'id_token': 'fake-id-token',
                        'access_token': 'fake-access-token',
                        'provider_id': 'google.com',
                    }
                ),
                'redirect_uri': 'omi-computer://auth/callback',
            }
        )

        with patch('routers.auth.get_auth_code', return_value=code_data), patch('routers.auth.delete_auth_code'):
            import asyncio

            request = MagicMock()

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    auth_token(
                        request=request,
                        grant_type='authorization_code',
                        code='test-code',
                        redirect_uri='omi-evil://auth/callback',  # mismatch
                        use_custom_token=False,
                    )
                )
            assert exc_info.value.status_code == 400
            assert 'mismatch' in exc_info.value.detail

    def test_token_accepts_matching_redirect_uri(self):
        """Verify /v1/auth/token succeeds when redirect_uri matches stored value."""
        code_data = json.dumps(
            {
                'credentials': json.dumps(
                    {
                        'provider': 'google',
                        'id_token': 'fake-id-token',
                        'access_token': 'fake-access-token',
                        'provider_id': 'google.com',
                    }
                ),
                'redirect_uri': 'omi-computer://auth/callback',
            }
        )

        with patch('routers.auth.get_auth_code', return_value=code_data), patch('routers.auth.delete_auth_code'):
            import asyncio

            request = MagicMock()

            result = asyncio.get_event_loop().run_until_complete(
                auth_token(
                    request=request,
                    grant_type='authorization_code',
                    code='test-code',
                    redirect_uri='omi-computer://auth/callback',  # match
                    use_custom_token=False,
                )
            )
            assert result['provider'] == 'google'
            assert result['id_token'] == 'fake-id-token'

    def test_token_handles_legacy_format(self):
        """Verify /v1/auth/token still works with legacy code format (no redirect_uri binding)."""
        legacy_data = json.dumps(
            {
                'provider': 'apple',
                'id_token': 'legacy-id-token',
                'access_token': 'legacy-access-token',
                'provider_id': 'apple.com',
            }
        )

        with patch('routers.auth.get_auth_code', return_value=legacy_data), patch('routers.auth.delete_auth_code'):
            import asyncio

            request = MagicMock()

            result = asyncio.get_event_loop().run_until_complete(
                auth_token(
                    request=request,
                    grant_type='authorization_code',
                    code='legacy-code',
                    redirect_uri='omi://auth/callback',
                    use_custom_token=False,
                )
            )
            assert result['provider'] == 'apple'
            assert result['id_token'] == 'legacy-id-token'

    def test_token_rejects_new_format_without_redirect_uri(self):
        """New-format auth code (has 'credentials' key) must include redirect_uri — fail closed."""
        code_data = json.dumps(
            {
                'credentials': json.dumps(
                    {'provider': 'google', 'id_token': 't', 'access_token': 'a', 'provider_id': 'google.com'}
                ),
                # redirect_uri intentionally missing
            }
        )
        request = MagicMock()
        with patch('routers.auth.get_auth_code', return_value=code_data), patch('routers.auth.delete_auth_code'):
            import asyncio

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    auth_token(
                        request=request,
                        grant_type='authorization_code',
                        code='c',
                        redirect_uri='omi://auth/callback',
                        use_custom_token=False,
                    )
                )
            assert exc_info.value.status_code == 400
            assert 'malformed' in exc_info.value.detail.lower()


class TestCallbackTemplateRendering:
    """Test that the callback template receives and uses dynamic redirect_uri."""

    def test_template_uses_dynamic_redirect_uri(self):
        """Verify auth_callback.html renders with the session's redirect_uri, not hardcoded."""
        from jinja2 import Environment, FileSystemLoader
        import pathlib

        templates_dir = pathlib.Path(__file__).parent.parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        template = env.get_template("auth_callback.html")

        html = template.render(
            code="test-auth-code",
            state="test-state",
            redirect_uri="omi-computer://auth/callback",
        )

        assert 'omi-computer://auth/callback' in html
        assert "omi://auth/callback" not in html  # hardcoded value must not appear

    def test_template_json_escapes_redirect_uri(self):
        """Verify redirect_uri is JSON-escaped in the template (XSS prevention)."""
        from jinja2 import Environment, FileSystemLoader
        import pathlib

        templates_dir = pathlib.Path(__file__).parent.parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        template = env.get_template("auth_callback.html")

        html = template.render(
            code='test</script><script>alert(1)',
            state='test-state',
            redirect_uri='omi-computer://auth/callback',
        )

        assert '</script><script>' not in html

    def test_template_defaults_when_redirect_uri_missing(self):
        """Verify template falls back to omi://auth/callback when redirect_uri not provided."""
        from jinja2 import Environment, FileSystemLoader
        import pathlib

        templates_dir = pathlib.Path(__file__).parent.parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        template = env.get_template("auth_callback.html")

        html = template.render(
            code="test-code",
            state="test-state",
        )

        assert 'omi://auth/callback' in html


class TestCallbackEndpoints:
    """Test Google and Apple callback endpoints bind auth codes correctly."""

    def test_google_callback_binds_redirect_uri_to_auth_code(self):
        """Google callback wraps credentials with redirect_uri and stores with TTL 300."""
        from routers.auth import auth_callback_google
        import asyncio

        session_data = {
            'provider': 'google',
            'redirect_uri': 'omi-computer://auth/callback',
            'state': 'test-state',
            'flow_type': 'user_auth',
        }
        fake_creds = json.dumps(
            {'provider': 'google', 'id_token': 'tok', 'access_token': 'at', 'provider_id': 'google.com'}
        )

        request = MagicMock()
        with patch('routers.auth.get_auth_session', return_value=session_data), patch(
            'routers.auth._exchange_provider_code_for_oauth_credentials',
            new_callable=AsyncMock,
            return_value=fake_creds,
        ), patch('routers.auth.set_auth_code') as mock_set_code, patch('routers.auth.templates') as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            asyncio.get_event_loop().run_until_complete(
                auth_callback_google(request=request, code='oauth-code', state='session-id')
            )
            mock_set_code.assert_called_once()
            stored_json = mock_set_code.call_args[0][1]
            ttl = mock_set_code.call_args[0][2]
            stored = json.loads(stored_json)
            assert stored['redirect_uri'] == 'omi-computer://auth/callback'
            assert 'credentials' in stored
            assert ttl == 300

    def test_callback_defaults_redirect_uri_when_missing_from_session(self):
        """When session has no redirect_uri, callback falls back to default."""
        from routers.auth import auth_callback_google
        import asyncio

        session_data = {
            'provider': 'google',
            'state': 'test-state',
            'flow_type': 'user_auth',
        }
        fake_creds = json.dumps(
            {'provider': 'google', 'id_token': 't', 'access_token': 'a', 'provider_id': 'google.com'}
        )

        request = MagicMock()
        with patch('routers.auth.get_auth_session', return_value=session_data), patch(
            'routers.auth._exchange_provider_code_for_oauth_credentials',
            new_callable=AsyncMock,
            return_value=fake_creds,
        ), patch('routers.auth.set_auth_code') as mock_set_code, patch('routers.auth.templates') as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            asyncio.get_event_loop().run_until_complete(auth_callback_google(request=request, code='c', state='s'))
            stored = json.loads(mock_set_code.call_args[0][1])
            assert stored['redirect_uri'] == _DEFAULT_MOBILE_REDIRECT


class TestTokenEdgeCases:
    """Test token endpoint edge cases: malformed data, single-use codes, credentials-as-dict."""

    def test_token_deletes_code_on_use(self):
        """Auth code is single-use — delete_auth_code must be called."""
        import asyncio

        code_data = json.dumps(
            {'provider': 'google', 'id_token': 't', 'access_token': 'a', 'provider_id': 'google.com'}
        )
        request = MagicMock()

        with patch('routers.auth.get_auth_code', return_value=code_data), patch(
            'routers.auth.delete_auth_code'
        ) as mock_delete:
            asyncio.get_event_loop().run_until_complete(
                auth_token(
                    request=request,
                    grant_type='authorization_code',
                    code='the-code',
                    redirect_uri='omi://auth/callback',
                    use_custom_token=False,
                )
            )
            mock_delete.assert_called_once_with('the-code')

    def test_token_rejects_expired_code(self):
        """Expired/missing code returns 400."""
        import asyncio

        request = MagicMock()
        with patch('routers.auth.get_auth_code', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    auth_token(
                        request=request,
                        grant_type='authorization_code',
                        code='gone',
                        redirect_uri='omi://auth/callback',
                        use_custom_token=False,
                    )
                )
            assert exc_info.value.status_code == 400
            assert 'expired' in exc_info.value.detail.lower()

    def test_token_handles_credentials_as_dict(self):
        """When credentials is already a dict (not JSON string), parsing succeeds."""
        import asyncio

        code_data = json.dumps(
            {
                'credentials': {
                    'provider': 'google',
                    'id_token': 'dict-tok',
                    'access_token': 'dict-at',
                    'provider_id': 'google.com',
                },
                'redirect_uri': 'omi://auth/callback',
            }
        )
        request = MagicMock()

        with patch('routers.auth.get_auth_code', return_value=code_data), patch('routers.auth.delete_auth_code'):
            result = asyncio.get_event_loop().run_until_complete(
                auth_token(
                    request=request,
                    grant_type='authorization_code',
                    code='c',
                    redirect_uri='omi://auth/callback',
                    use_custom_token=False,
                )
            )
            assert result['provider'] == 'google'
            assert result['id_token'] == 'dict-tok'

    def test_token_rejects_unsupported_grant_type(self):
        """Non-authorization_code grant type returns 400."""
        import asyncio

        request = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                auth_token(
                    request=request,
                    grant_type='client_credentials',
                    code='c',
                    redirect_uri='omi://auth/callback',
                    use_custom_token=False,
                )
            )
        assert exc_info.value.status_code == 400
