"""Hermetic settings-page XSS/breakout regression tests for #14876.

Only SDK, storage, and framework import boundaries are replaced; the full
production main.py executes against in-memory stubs, with no live Slack,
filesystem-backed user data, or network access.
"""
import asyncio
import importlib.util
import html
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote


class Response:
    def __init__(self, content="", status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SettingsPageTests(unittest.TestCase):
    def setUp(self):
        framework = types.ModuleType("fastapi")
        app = Mock()
        for method in ("get", "post", "on_event"):
            getattr(app, method).side_effect = lambda *a, **k: lambda f: f
        framework.FastAPI = lambda **kwargs: app
        framework.Request = object
        framework.HTTPException = Exception
        framework.Query = lambda *a, **k: None
        responses = types.ModuleType("fastapi.responses")
        responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = Response
        storage = types.ModuleType("simple_storage")
        storage.SimpleUserStorage = Mock()
        storage.SimpleUserStorage.get_user.return_value = {"access_token": "fixture"}
        storage.SimpleSessionStorage = Mock()
        client = types.ModuleType("slack_client")
        client.SlackClient = Mock()
        detector = types.ModuleType("message_detector")
        detector.MessageDetector = Mock()
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        modules = {"fastapi": framework, "fastapi.responses": responses,
                   "simple_storage": storage, "slack_client": client,
                   "message_detector": detector, "dotenv": dotenv}
        with patch.dict(sys.modules, modules), patch.dict("os.environ", {}, clear=True):
            self.handler = load("slack_settings_main", "main.py")
        self.SimpleUserStorage = storage.SimpleUserStorage

    def render_root(self, uid):
        return asyncio.run(self.handler.root(uid=uid))

    def authenticated_user(self, team_name="Test Team", channels=None):
        self.SimpleUserStorage.get_user.return_value = {
            "access_token": "fake",
            "team_name": team_name,
            "available_channels": channels or [],
        }

    def test_unauth_uid_breakout(self):
        uid = '"><script>alert(1)</script>'
        self.SimpleUserStorage.get_user.return_value = None
        response = self.render_root(uid)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'uid={quote(uid, safe="")}', response.content)
        self.assertNotIn('"><script>', response.content)

    def test_channel_xss(self):
        self.authenticated_user(channels=[
            {"id": 'C123">', "name": "</option><script>alert(1)</script>"}
        ])
        response = self.render_root("test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;/option&gt;&lt;script&gt;alert(1)&lt;/script&gt;", response.content)
        self.assertIn("C123&quot;&gt;", response.content)
        self.assertNotIn("</option><script>", response.content)

    def test_team_name_xss(self):
        self.authenticated_user(team_name="<script>alert('team')</script>")
        response = self.render_root("test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;script&gt;alert(&#x27;team&#x27;)&lt;/script&gt;", response.content)
        self.assertNotIn("<script>alert", response.content)

    def test_auth_callback_success_xss(self):
        uid = "\"><script>alert('uid')</script>"
        self.handler.oauth_states["fake_state"] = uid

        class FakeSlackClient:
            def exchange_code_for_token(self, code, redirect_uri):
                return {"access_token": "token", "team_id": "T1",
                        "team_name": "<img src=x onerror=alert(1)>"}

            def list_channels(self, token):
                return []

        self.handler.slack_client = FakeSlackClient()
        response = asyncio.run(self.handler.auth_callback(None, code="fake_code", state="fake_state"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", response.content)
        self.assertIn(f'uid={quote(uid, safe="")}', response.content)
        self.assertNotIn("<img src=x", response.content)

    def test_auth_callback_failure_xss(self):
        uid = "\"><script>alert(1)</script>"
        self.handler.oauth_states["err_state"] = uid

        class FailingSlackClient:
            def exchange_code_for_token(self, code, redirect_uri):
                raise Exception("<script>alert('error')</script>")

        self.handler.slack_client = FailingSlackClient()
        response = asyncio.run(self.handler.auth_callback(None, code="fake_code", state="err_state"))
        self.assertEqual(response.status_code, 500)
        self.assertIn(f'uid={quote(uid, safe="")}', response.content)
        self.assertNotIn("<script>alert", response.content)

    def test_normal_input(self):
        self.authenticated_user("Normal Team", [{"id": "C123", "name": "general"}])
        response = self.render_root("normal_user_123")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Normal Team", response.content)
        self.assertIn("general", response.content)
        self.assertIn('value="C123"', response.content)

    def test_authenticated_page_hidden_uid_is_escaped(self):
        """The authenticated settings page renders the hidden #uid input escaped.

        #14876 review: JS reads document.getElementById('uid').value, so the
        hidden input added on the authenticated page must carry the html.escaped
        uid — a raw uid here would re-open the attribute breakout this fix closes.
        """
        uid = '"><script>alert(1)</script>'
        self.authenticated_user(channels=[])
        response = self.render_root(uid)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'id="uid" value="{html.escape(uid)}"', response.content)
        self.assertNotIn('"><script>alert', response.content)
        self.assertIn("Slack Settings", response.content)


if __name__ == "__main__":
    unittest.main()