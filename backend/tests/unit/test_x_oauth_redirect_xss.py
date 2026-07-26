"""GET /v1/x/oauth-url and the /v1/x/oauth/callback HTML page must not be exploitable via
success_redirect_url.

Before this fix, _redirect_html only escaped '"' in the deep_link before splicing it into
both an HTML attribute (meta refresh) and a JS string literal (script tag). A
success_redirect_url containing "</script><script>...</script>" would break out of the
script block and execute as HTML/JS in the backend's own origin (reflected XSS), and
nothing restricted the scheme, so https://attacker.example was also accepted as a valid
post-auth landing (open redirect).

x_oauth_url now validates success_redirect_url with utils.redirect_uri.validate_redirect_uri
(the same native-app-scheme/loopback allowlist used by /v1/auth), and _redirect_html now
escapes deep_link correctly for each context it's spliced into.

Test isolation: routers.x_connector imports cleanly (see test_x_posts_list_endpoint.py).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from routers import x_connector as x_mod  # noqa: E402


class TestRedirectHtmlEscaping:
    def test_script_breakout_payload_is_neutralized(self):
        payload = 'omi://x/callback?status=</script><script>alert(document.cookie)</script>'
        response = x_mod._redirect_html(payload, True, 'X connected')
        body = response.body.decode()

        assert '</script><script>alert' not in body, "raw </script><script> sequence must not appear in the response"
        # The JS string literal must have '<' escaped so a parser can't see a real "</script>".
        assert '\\u003c/script>\\u003cscript>' in body

    def test_quote_breakout_payload_is_neutralized(self):
        payload = 'omi://x/callback?status="><script>alert(1)</script>'
        response = x_mod._redirect_html(payload, True, 'X connected')
        body = response.body.decode()

        assert '<script>alert(1)</script>' not in body
        assert '"><script>' not in body

    def test_plain_deep_link_still_redirects(self):
        response = x_mod._redirect_html('omi://x/callback?status=success', True, 'X connected')
        body = response.body.decode()

        assert 'omi://x/callback?status=success' in body
        assert response.status_code == 200

    def test_message_is_html_escaped(self):
        response = x_mod._redirect_html('omi://x/callback', False, '<img src=x onerror=alert(1)>')
        body = response.body.decode()

        assert '<img src=x onerror=alert(1)>' not in body


class TestOauthUrlRedirectValidation:
    def test_rejects_https_redirect(self, monkeypatch):
        monkeypatch.setattr(x_mod.x_connector, 'is_oauth_configured', lambda: True)

        with pytest.raises(HTTPException) as exc_info:
            x_mod.x_oauth_url(success_redirect_url='https://attacker.example/steal', uid='u1')

        assert exc_info.value.status_code == 400

    def test_rejects_javascript_scheme(self, monkeypatch):
        monkeypatch.setattr(x_mod.x_connector, 'is_oauth_configured', lambda: True)

        with pytest.raises(HTTPException) as exc_info:
            x_mod.x_oauth_url(success_redirect_url='javascript:alert(1)', uid='u1')

        assert exc_info.value.status_code == 400

    def test_allows_native_app_scheme(self, monkeypatch):
        monkeypatch.setattr(x_mod.x_connector, 'is_oauth_configured', lambda: True)
        monkeypatch.setattr(x_mod.x_connector, 'build_authorize_url', lambda uid, success_redirect_url=None: 'https://x.com/oauth')

        result = x_mod.x_oauth_url(success_redirect_url='omi://x/callback', uid='u1')
        assert result.success is True

    def test_no_redirect_url_is_fine(self, monkeypatch):
        monkeypatch.setattr(x_mod.x_connector, 'is_oauth_configured', lambda: True)
        monkeypatch.setattr(x_mod.x_connector, 'build_authorize_url', lambda uid, success_redirect_url=None: 'https://x.com/oauth')

        result = x_mod.x_oauth_url(success_redirect_url=None, uid='u1')
        assert result.success is True
