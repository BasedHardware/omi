"""Hermetic regression test: OAuth client success paths must not print secrets.

Stubs `requests` in sys.modules so the test runs without network access.
The Notion token-exchange response carries the user's fresh access_token;
printing it (or any success response body) leaks credentials to stdout logs.
"""

import contextlib
import io
import sys
import types
import unittest
from unittest import mock


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def load_client_module():
    """Import oauth/client.py with `requests` stubbed."""
    for name in ("oauth.client", "client"):
        sys.modules.pop(name, None)
    fake_requests = types.ModuleType("requests")
    fake_requests.Response = FakeResponse
    fake_requests.get = mock.MagicMock()
    fake_requests.post = mock.MagicMock()
    sys.modules["requests"] = fake_requests
    import importlib.util

    spec = importlib.util.spec_from_file_location("oauth.client", "plugins/oauth/client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, fake_requests


SECRET = "secret_ntn_token_value_12345"


class TestOAuthClientLogSafety(unittest.TestCase):
    def test_get_access_token_does_not_print_token_response(self):
        module, fake_requests = load_client_module()
        fake_requests.post.return_value = FakeResponse(
            {
                "access_token": SECRET,
                "token_type": "bearer",
                "bot_id": "bot-1",
                "workspace_id": "ws-1",
                "workspace_name": "My Workspace",
            }
        )
        notion = module.NotionClient("cid", "csecret", "https://redir", "https://auth")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = notion.get_access_token("auth-code")
        self.assertIn("result", result)
        self.assertNotIn(SECRET, buf.getvalue())
        self.assertNotIn("My Workspace", buf.getvalue())

    def test_get_database_does_not_print_response(self):
        module, fake_requests = load_client_module()
        fake_requests.get.return_value = FakeResponse(
            {
                "id": "db-1",
                "title": [{"plain_text": "Secret DB Name"}],
                "properties": {},
            }
        )
        notion = module.NotionClient("cid", "csecret", "https://redir", "https://auth")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = notion.get_database("db-1", SECRET)
        self.assertIn("result", result)
        self.assertNotIn("Secret DB Name", buf.getvalue())

    def test_get_databases_does_not_print_response(self):
        module, fake_requests = load_client_module()
        fake_requests.post.return_value = FakeResponse({"results": []})
        notion = module.NotionClient("cid", "csecret", "https://redir", "https://auth")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            notion.get_databases_edited_time_desc(SECRET)
        self.assertNotIn("results", buf.getvalue())

    def test_error_path_still_logs_status(self):
        module, fake_requests = load_client_module()
        fake_requests.post.return_value = FakeResponse(
            {"code": "unauthorized", "message": "bad token"}, status_code=401
        )
        notion = module.NotionClient("cid", "csecret", "https://redir", "https://auth")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = notion.get_access_token("bad-code")
        self.assertIn("error", result)
        self.assertIn("HTTP_401", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
