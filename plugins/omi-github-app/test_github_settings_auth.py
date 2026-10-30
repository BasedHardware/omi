"""Tests for the signed settings session used by the GitHub App routes."""

import ast
import os
import sys
import unittest
from pathlib import Path

import fastapi

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from github_settings_auth import (  # noqa: E402
    COOKIE_NAME,
    require_settings_session,
    session_matches,
    session_value,
)

SECRET = "test-github-settings-secret"
UID = "uid-github-1"


class _FakeRequest:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}


class TestRequireSettingsSession(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("GITHUB_SETTINGS_SECRET")
        os.environ["GITHUB_SETTINGS_SECRET"] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop("GITHUB_SETTINGS_SECRET", None)
        else:
            os.environ["GITHUB_SETTINGS_SECRET"] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop("GITHUB_SETTINGS_SECRET", None)
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_settings_session(_FakeRequest({COOKIE_NAME: "anything"}), UID)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_cookie_rejected(self):
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_settings_session(_FakeRequest(), UID)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_cookie_for_another_uid_rejected(self):
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_settings_session(_FakeRequest({COOKIE_NAME: session_value("someone-else")}), UID)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_tampered_signature_rejected(self):
        uid, _, signature = session_value(UID).rpartition(".")
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_settings_session(_FakeRequest({COOKIE_NAME: f"{uid}.{'0' * len(signature)}"}), UID)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_valid_cookie_accepted(self):
        request = _FakeRequest({COOKIE_NAME: session_value(UID)})
        self.assertIsNone(require_settings_session(request, UID))
        self.assertTrue(session_matches(request, UID))

    def test_mismatch_is_not_a_match(self):
        request = _FakeRequest({COOKIE_NAME: session_value("other-uid")})
        self.assertFalse(session_matches(request, UID))


class TestSettingsRoutesAreWired(unittest.TestCase):
    PROTECTED = {
        "update_repo",
        "refresh_repos",
        "check_repo_access",
        "save_agent_provider",
        "save_agent_key",
        "delete_agent_key",
        "test_agent",
    }

    def test_every_settings_write_requires_a_session(self):
        tree = ast.parse((APP_DIR / "main.py").read_text(encoding="utf-8"))
        wired = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in self.PROTECTED:
                continue
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and getattr(child.func, "id", None) == "require_settings_session"
                    and len(child.args) == 2
                ):
                    wired.add(node.name)
        self.assertEqual(wired, self.PROTECTED)

    def test_oauth_callback_issues_the_session_cookie(self):
        tree = ast.parse((APP_DIR / "main.py").read_text(encoding="utf-8"))
        callback = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "auth_callback"
        )
        calls = [child for child in ast.walk(callback) if isinstance(child, ast.Call)]
        self.assertTrue(any(getattr(call.func, "attr", None) == "set_cookie" for call in calls))
        self.assertTrue(any(getattr(call.func, "id", None) == "session_value" for call in calls))


if __name__ == "__main__":
    unittest.main()
