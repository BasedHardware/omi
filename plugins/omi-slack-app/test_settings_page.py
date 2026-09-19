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


if __name__ == "__main__":
    unittest.main()
