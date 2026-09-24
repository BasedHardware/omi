"""Hermetic error handling and exception sanitization tests for GitHub App.

Verifies that internal exceptions, system paths, network addresses, and raw
tracebacks never leak into client-facing ChatToolResponse or error dictionaries.
"""

import ast
from pathlib import Path
import types
import unittest
from unittest.mock import MagicMock

CLIENT_PATH = Path(__file__).resolve().parent / "github_client.py"
MAIN_PATH = Path(__file__).resolve().parent / "main.py"


class GitHubAppErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/gh_token.json: connection reset by 192.168.1.88:443"
        self.client_text = CLIENT_PATH.read_text(encoding="utf-8")
        self.main_text = MAIN_PATH.read_text(encoding="utf-8")

    def test_client_error_message_does_not_leak_response_text(self):
        self.assertNotIn('getattr(response, "text"', self.client_text)
        from github_client import GitHubClient
        mock_resp = types.SimpleNamespace(status_code=502, text=self.sensitive_leak, json=lambda: (_ for _ in ()).throw(ValueError()))
        msg = GitHubClient._error_message(mock_resp)
        self.assertNotIn(self.sensitive_leak, msg)
        self.assertNotIn("192.168.1.88", msg)
        self.assertEqual(msg, "HTTP 502")

    def test_client_list_issues_sanitizes_exception(self):
        from github_client import GitHubClient
        client = GitHubClient()
        client.timeout = 0.001
        # Calling without valid network/token will raise and enter exception handler
        res = client.list_issues(access_token="tok", repo_full_name="a/b")
        self.assertIn("error", res)
        self.assertEqual(res["error"], "Failed to list issues")

    def test_client_get_issue_sanitizes_exception(self):
        from github_client import GitHubClient
        client = GitHubClient()
        client.timeout = 0.001
        res = client.get_issue(access_token="tok", repo_full_name="a/b", issue_number=1)
        self.assertIn("error", res)
        self.assertEqual(res["error"], "Failed to get issue")

    def test_main_create_issue_sanitized(self):
        self.assertIn('return ChatToolResponse(error="Failed to create issue.")', self.main_text)
        self.assertNotIn('return ChatToolResponse(error=f"Failed to create issue: {error}")', self.main_text)

    def test_main_get_issue_sanitized(self):
        self.assertIn('return ChatToolResponse(error="Failed to get issue.")', self.main_text)
        self.assertNotIn('return ChatToolResponse(error=f"Failed to get issue: {result[\'error\']}")', self.main_text)

    def test_main_add_comment_sanitized(self):
        self.assertIn('return ChatToolResponse(error="Failed to add comment.")', self.main_text)
        self.assertNotIn('return ChatToolResponse(error=f"Failed to add comment: {error}")', self.main_text)

    def test_ast_audit_no_raw_exception_reflection(self):
        tree = ast.parse(self.main_text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Name) and func.id == "ChatToolResponse") or \
                   (isinstance(func, ast.Attribute) and func.attr == "ChatToolResponse"):
                    for kw in node.keywords:
                        if kw.arg == "error" and isinstance(kw.value, ast.JoinedStr):
                            for part in kw.value.values:
                                if isinstance(part, ast.FormattedValue):
                                    val = ast.unparse(part.value)
                                    self.assertNotIn(val, {"e", "str(e)", "exc", "error"},
                                                     f"Raw error reflection found in main.py: {val}")


if __name__ == "__main__":
    unittest.main()
