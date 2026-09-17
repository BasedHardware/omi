"""Hermetic regression test: OAuth plugin success paths must not print secrets.

Stubs `requests` in sys.modules so the test runs without network access.
The Notion token-exchange response carries the user's fresh access_token;
printing it (or any success response body) leaks credentials to stdout logs.

The last test class is a static source check, not behavioral coverage: it
scans every plugin file for log calls that name secrets, response bodies,
or transcript buffers (most plugin modules are too import-heavy to stub
hermetically).
"""

import contextlib
import importlib.util
import io
import os
import re
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
    """Import oauth/client.py with `requests` stubbed, then restore sys.modules."""
    for name in ("oauth.client", "client"):
        sys.modules.pop(name, None)
    real_requests = sys.modules.get("requests")
    fake_requests = types.ModuleType("requests")
    fake_requests.Response = FakeResponse
    fake_requests.get = mock.MagicMock()
    fake_requests.post = mock.MagicMock()
    sys.modules["requests"] = fake_requests
    try:
        spec = importlib.util.spec_from_file_location("oauth.client", "plugins/oauth/client.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if real_requests is not None:
            sys.modules["requests"] = real_requests
        else:
            sys.modules.pop("requests", None)
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
        fake_requests.post.return_value = FakeResponse(
            {"results": [{"id": "db-9", "title": [{"plain_text": "Sentinel DB"}], "properties": {}}]}
        )
        notion = module.NotionClient("cid", "csecret", "https://redir", "https://auth")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            notion.get_databases_edited_time_desc(SECRET)
        self.assertNotIn("Sentinel DB", buf.getvalue())

    def test_error_path_logs_status_not_body(self):
        module, fake_requests = load_client_module()
        fake_requests.post.return_value = FakeResponse(
            {"code": "unauthorized", "message": "bad token"}, status_code=401
        )
        notion = module.NotionClient("cid", "csecret", "https://redir", "https://auth")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = notion.get_access_token("bad-code")
        self.assertIn("error", result)
        out = buf.getvalue()
        self.assertIn("HTTP_401", out)
        self.assertNotIn("bad token", out)


class TestPluginSourceSafety(unittest.TestCase):
    """Static tripwire: log statements anywhere under plugins/ must not name
    credential variables, provider response bodies, webhook URLs, raw
    transcript buffers, or exception strings (which embed request URLs).
    Static checker, not behavioral coverage (most plugin modules are too
    import-heavy to stub hermetically)."""

    BANNED_TOKENS = [
        "access_token",
        "refresh_token",
        "api_key",
        "token_data",
        "target_url",
        "response.text",
        "resp.text",
        "resp.json()",
        "full_text",
        "accumulated",
        "question_part",
        "full_question",
        "request.dict()",
        "str(e)",
        "response_message",
        "cleaned_content",
    ]

    def test_no_log_call_emits_secrets_or_response_bodies(self):
        import ast
        import glob

        def is_log_call(node):
            # print(...), log(...), logger.info/warning/error/debug/exception(...)
            if isinstance(node.func, ast.Name):
                return node.func.id in ("print", "log")
            return isinstance(node.func, ast.Attribute) and node.func.attr in (
                "info", "warning", "error", "debug", "exception", "critical",
            )

        for path in sorted(glob.glob("plugins/**/*.py", recursive=True)):
            if os.path.basename(path).startswith("test_"):
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                source = f.read()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not is_log_call(node):
                    continue
                args_src = ast.get_source_segment(source, node) or ""
                for token in self.BANNED_TOKENS:
                    self.assertNotIn(
                        token, args_src, f"{path}:{node.lineno} logs {token}"
                    )


if __name__ == "__main__":
    unittest.main()
