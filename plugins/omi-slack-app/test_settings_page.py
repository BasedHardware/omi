"""Hermetic unit tests for omi-slack-app settings page and OAuth callback HTML encoding.

Verifies that user-controlled and Slack-supplied inputs (channel names, channel IDs,
team names, and user IDs) are properly escaped and URL-encoded at HTML boundaries
to prevent Cross-Site Scripting (XSS), attribute breakout, and query string corruption.
Framework and storage are stubbed with zero external dependencies.
"""
import asyncio
import html
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote

BREAKOUT_SCRIPT = '"><script>alert(1)</script>'
QUERY_BREAKER = 'user&admin=1#frag'


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = on_event = get


class Response:
    def __init__(self, content=None, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.__dict__.update(kwargs)


def _make_module(name, **attributes):
    mod = types.ModuleType(name)
    mod.__dict__.update(attributes)
    return mod


# Construct doubles for external imports
stubs = {
    "dotenv": _make_module("dotenv", load_dotenv=lambda: None),
    "fastapi": _make_module("fastapi", FastAPI=Framework, Request=Framework, Query=lambda default=None, **k: default, HTTPException=Exception),
    "fastapi.responses": _make_module("fastapi.responses", HTMLResponse=Response, RedirectResponse=Response, JSONResponse=Response),
    "simple_storage": _make_module("simple_storage", SimpleUserStorage=Mock(), SimpleSessionStorage=Mock()),
    "slack_client": _make_module("slack_client", SlackClient=Mock),
    "message_detector": _make_module("message_detector", MessageDetector=Mock),
}

spec = importlib.util.spec_from_file_location("slack_main_under_test", Path(__file__).with_name("main.py"))
main = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(main)


class SlackSettingsPageEncodingTests(unittest.TestCase):
    def test_channel_names_and_ids_are_escaped_in_picker(self):
        """Channel names and IDs supplied by Slack must be HTML-escaped in the select options."""
        malicious_channels = [
            {
                "id": 'C123" onfocus="alert(1)',
                "name": '<script>alert("xss")</script>',
                "is_private": False
            },
            {
                "id": "C456",
                "name": "<b>Bold & Beautiful</b>",
                "is_private": True
            }
        ]
        user = {
            "access_token": "xoxp-test-token",
            "team_name": "Test Team",
            "selected_channel": "C456",
            "available_channels": malicious_channels
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            res = asyncio.run(main.root(uid="u1"))
            page = res.content

        # Script tags and unescaped quotes must NOT appear inside the HTML
        self.assertNotIn('<script>alert("xss")</script>', page)
        self.assertNotIn('<b>Bold & Beautiful</b>', page)
        self.assertNotIn('value="C123" onfocus="alert(1)"', page)

        # Escaped versions must appear
        self.assertIn('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;', page)
        self.assertIn('&lt;b&gt;Bold &amp; Beautiful&lt;/b&gt;', page)
        self.assertIn('value="C123&quot; onfocus=&quot;alert(1)"', page)

    def test_team_name_is_escaped_in_settings_page(self):
        """Team/workspace name must be escaped on the settings page."""
        malicious_team = '<img src=x onerror=alert("team")>'
        user = {
            "access_token": "xoxp-test-token",
            "team_name": malicious_team,
            "selected_channel": "",
            "available_channels": []
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            res = asyncio.run(main.root(uid="u1"))
            page = res.content

        self.assertNotIn(malicious_team, page)
        self.assertIn(html.escape(malicious_team), page)

    def test_team_name_is_escaped_in_oauth_callback(self):
        """Team/workspace name must be escaped on the OAuth callback success page."""
        malicious_team = '<script>alert("oauth")</script>'
        token_data = {
            "access_token": "xoxp-test-token",
            "team_id": "T123",
            "team_name": malicious_team
        }
        mock_client = Mock()
        mock_client.exchange_code_for_token.return_value = token_data
        mock_client.list_channels.return_value = []

        main.oauth_states["valid_state"] = "user_test_uid"
        try:
            with patch.object(main, "slack_client", mock_client), \
                 patch.object(main.SimpleUserStorage, "save_user", return_value=True):
                res = asyncio.run(main.auth_callback(request=Mock(), code="valid_code", state="valid_state"))
                page = res.content

            self.assertNotIn(malicious_team, page)
            self.assertIn(html.escape(malicious_team), page)
        finally:
            main.oauth_states.pop("valid_state", None)

    def test_oauth_callback_error_is_escaped(self):
        """Reflected error parameter on OAuth callback must be HTML-escaped."""
        malicious_error = '<script>alert("denied")</script>'
        res = asyncio.run(main.auth_callback(request=Mock(), error=malicious_error))
        page = res.content
        self.assertEqual(res.status_code, 400)
        self.assertNotIn(malicious_error, page)
        self.assertIn(html.escape(malicious_error), page)

    def test_unauthenticated_uid_is_url_encoded(self):
        """Unauthenticated connect link must percent-encode uid to prevent attribute breakout."""
        with patch.object(main.SimpleUserStorage, "get_user", return_value=None):
            res = asyncio.run(main.root(uid=BREAKOUT_SCRIPT))
            page = res.content

        # Raw breakout must not be in href
        self.assertNotIn(BREAKOUT_SCRIPT, page)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn(quote(BREAKOUT_SCRIPT, safe=""), page)

    def test_uid_query_separators_do_not_corrupt_link(self):
        """Characters like & and # in uid must be percent-encoded so queries are not hijacked."""
        with patch.object(main.SimpleUserStorage, "get_user", return_value=None):
            res = asyncio.run(main.root(uid=QUERY_BREAKER))
            page = res.content

        self.assertNotIn(f"uid={QUERY_BREAKER}", page)
        self.assertIn(f"uid={quote(QUERY_BREAKER, safe='')}", page)

    def test_ordinary_inputs_render_normally(self):
        """Normal inputs without special characters must render cleanly and correctly."""
        normal_channels = [
            {"id": "C_GEN", "name": "general", "is_private": False},
            {"id": "C_RAND", "name": "random", "is_private": True}
        ]
        user = {
            "access_token": "xoxp-test-token",
            "team_name": "Acme Workspace",
            "selected_channel": "C_GEN",
            "available_channels": normal_channels
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            res = asyncio.run(main.root(uid="usr_12345"))
            page = res.content

        self.assertIn("Acme Workspace", page)
        self.assertIn('<option value="C_GEN" selected># general</option>', page)
        self.assertIn('<option value="C_RAND" >🔒 random</option>', page)
        self.assertIn("/logout?uid=usr_12345", page)


    def test_authenticated_inline_js_uid_encoding(self):
        """Authenticated page inline JS (updateChannel, refreshChannels, logoutUser) must encode uid."""
        malicious_uid = "u1' + alert('pwn') + '"
        user = {
            "access_token": "xoxp-test-token",
            "team_name": "Test Team",
            "selected_channel": "C123",
            "available_channels": []
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            res = asyncio.run(main.root(uid=malicious_uid))
            page = res.content

        # Raw single-quote JS injection string must not appear anywhere
        self.assertNotIn("update-channel?uid=u1' + alert('pwn')", page)
        self.assertNotIn("refresh-channels?uid=u1' + alert('pwn')", page)
        self.assertNotIn("logout?uid=u1' + alert('pwn')", page)

        # Encoded version must be used everywhere
        expected_encoded_uid = quote(malicious_uid, safe="")
        self.assertIn(f"/update-channel?uid={expected_encoded_uid}&channel=", page)
        self.assertIn(f"/refresh-channels?uid={expected_encoded_uid}", page)
        self.assertIn(f"/logout?uid={expected_encoded_uid}", page)
        self.assertIn(f"/?uid={expected_encoded_uid}", page)

    def test_dev_test_interface_escapes_uid(self):
        """The /test development interface must escape uid to prevent reflected XSS."""
        malicious_uid = 'test_user"><script>alert("reflected")</script>'
        res = asyncio.run(main.test_interface(uid=malicious_uid, dev="true"))
        page = res.content
        self.assertEqual(res.status_code, 200)

        # Raw script tag must NOT be present
        self.assertNotIn('<script>alert("reflected")</script>', page)
        self.assertNotIn(f'value="{malicious_uid}"', page)

        # HTML-escaped attribute value must be present
        escaped_uid = html.escape(malicious_uid, quote=True)
        self.assertIn(f'value="{escaped_uid}"', page)

    def test_dev_test_interface_without_dev_returns_404(self):
        """The /test interface without dev=true returns 404."""
        res = asyncio.run(main.test_interface(uid="test", dev=None))
        self.assertEqual(res.status_code, 404)
        self.assertIn("Page Not Found", res.content)

    def test_none_team_name_renders_fallback(self):
        """If team_name is None, it should fall back to 'Unknown' gracefully without error."""
        user = {
            "access_token": "xoxp-test-token",
            "team_name": None,
            "selected_channel": "",
            "available_channels": []
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            res = asyncio.run(main.root(uid="u1"))
            page = res.content

        self.assertIn("Connected to <span class=\"username\">Unknown</span>", page)
        self.assertNotIn("Connected to <span class=\"username\">None</span>", page)

    def test_html_responses_contain_meta_charset(self):
        """All HTML responses must declare utf-8 charset."""
        with patch.object(main.SimpleUserStorage, "get_user", return_value=None):
            unauth_page = asyncio.run(main.root(uid="u1")).content
            self.assertIn('<meta charset="utf-8">', unauth_page)

        auth_user = {
            "access_token": "xoxp-test-token",
            "team_name": "Team",
            "selected_channel": "",
            "available_channels": []
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=auth_user):
            auth_page = asyncio.run(main.root(uid="u1")).content
            self.assertIn('<meta charset="utf-8">', auth_page)


if __name__ == "__main__":
    unittest.main()
