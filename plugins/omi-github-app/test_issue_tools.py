"""Hermetic production-handler tests for GitHub issue tools; framework, storage and GitHub API are doubles."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = on_event = get


class ChatToolResponse:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def __repr__(self):
        return f"ChatToolResponse(result={self.result!r}, error={self.error!r})"


def module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


class RequestStub:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def load_main():
    stubs = {
        "dotenv": module("dotenv", load_dotenv=lambda: None),
        "fastapi": module("fastapi", FastAPI=Framework, Request=object, HTTPException=Exception, Query=Mock()),
        "fastapi.responses": module("fastapi.responses", HTMLResponse=object, RedirectResponse=Mock(), JSONResponse=Mock()),
        "simple_storage": module("simple_storage", SimpleUserStorage=Mock()),
        "issue_detector": module("issue_detector", ai_select_labels=Mock()),
        "models": module("models", ChatToolResponse=ChatToolResponse, GitHubRepo=Mock(), GitHubIssue=Mock(), GitHubLabel=Mock()),
        "agent_providers": module(
            "agent_providers",
            run_agent_provider=Mock(),
            PROVIDERS={},
            get_provider_label=Mock(),
            get_provider_default_key=Mock(),
            get_provider_base_url=Mock(),
        ),
    }
    main_path = Path(__file__).parent / "main.py"
    spec = importlib.util.spec_from_file_location("github_main_under_test", main_path)
    main = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(main)
    return main


SAMPLE_USER = {
    "uid": "test_uid",
    "access_token": "gho_test_token_123",
    "selected_repo": "owner/repo",
}

SAMPLE_ISSUE = {
    "number": 42,
    "title": "Fix memory leak in parser",
    "state": "open",
    "body": "Detailed description of the issue.",
    "labels": ["bug", "backend"],
    "assignees": ["octocat"],
    "user": "contributor",
    "comments": 3,
    "url": "https://github.com/owner/repo/issues/42",
    "created_at": "2026-09-14T00:00:00Z",
    "updated_at": "2026-09-14T01:00:00Z",
}


class GitHubIssueToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = load_main()

    def setUp(self):
        self.main.SimpleUserStorage.get_user = Mock(return_value=SAMPLE_USER)

    def run_coro(self, coro):
        return asyncio.run(coro)

    # -------------------------------------------------------------------------
    # Helper coercion function tests
    # -------------------------------------------------------------------------

    def test_coerce_issue_number(self):
        coerce = getattr(self.main, "coerce_issue_number", None)
        self.assertIsNotNone(coerce, "main.py must expose coerce_issue_number")

        # Valid integer / string representations
        self.assertEqual(coerce(42), 42)
        self.assertEqual(coerce("42"), 42)
        self.assertEqual(coerce("#42"), 42)
        self.assertEqual(coerce(" #42 "), 42)
        self.assertEqual(coerce(42.0), 42)

        # Invalid, negative, zero, non-finite, non-numeric
        self.assertIsNone(coerce(None))
        self.assertIsNone(coerce(""))
        self.assertIsNone(coerce("   "))
        self.assertIsNone(coerce("#"))
        self.assertIsNone(coerce("abc"))
        self.assertIsNone(coerce("#abc"))
        self.assertIsNone(coerce(0))
        self.assertIsNone(coerce(-5))
        self.assertIsNone(coerce("-5"))
        self.assertIsNone(coerce(1e309))
        self.assertIsNone(coerce(float("nan")))
        self.assertIsNone(coerce(float("inf")))
        self.assertIsNone(coerce(True))
        self.assertIsNone(coerce(False))
        self.assertIsNone(coerce([42]))

    def test_coerce_limit(self):
        coerce = getattr(self.main, "coerce_limit", None)
        self.assertIsNotNone(coerce, "main.py must expose coerce_limit")

        self.assertEqual(coerce(10), 10)
        self.assertEqual(coerce("25"), 25)
        self.assertEqual(coerce(0), 1)
        self.assertEqual(coerce(-5), 1)
        self.assertEqual(coerce(200), 100)
        self.assertEqual(coerce(1e309), 10)
        self.assertEqual(coerce("abc"), 10)
        self.assertEqual(coerce(None), 10)

    # -------------------------------------------------------------------------
    # tool_get_issue tests
    # -------------------------------------------------------------------------

    def test_get_issue_with_hash_string_and_whitespace(self):
        client = Mock()
        client.get_issue = Mock(return_value=SAMPLE_ISSUE)
        self.main.github_client = client

        req = RequestStub({"uid": "test_uid", "repo": "owner/repo", "issue_number": " #42 "})
        resp = self.run_coro(self.main.tool_get_issue(req))

        self.assertIsNone(resp.error)
        self.assertIn("#42", resp.result)
        self.assertIn("Fix memory leak in parser", resp.result)
        client.get_issue.assert_called_once_with(
            access_token="gho_test_token_123",
            repo_full_name="owner/repo",
            issue_number=42,
        )

    def test_get_issue_invalid_number_returns_clean_error(self):
        client = Mock()
        self.main.github_client = client

        for bad_val in ["#notanumber", "abc", "-5", 0, 1e309]:
            with self.subTest(issue_number=bad_val):
                req = RequestStub({"uid": "test_uid", "repo": "owner/repo", "issue_number": bad_val})
                resp = self.run_coro(self.main.tool_get_issue(req))

                self.assertIsNotNone(resp.error)
                self.assertIn("Invalid issue number", resp.error)
                client.get_issue.assert_not_called()

    def test_get_issue_not_found(self):
        client = Mock()
        client.get_issue = Mock(return_value=None)
        self.main.github_client = client

        req = RequestStub({"uid": "test_uid", "repo": "owner/repo", "issue_number": 999})
        resp = self.run_coro(self.main.tool_get_issue(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("not found", resp.error)

    def test_get_issue_api_error_propagates(self):
        client = Mock()
        client.get_issue = Mock(return_value={"error": "GitHub API error: 401 - Bad credentials"})
        self.main.github_client = client

        req = RequestStub({"uid": "test_uid", "repo": "owner/repo", "issue_number": 42})
        resp = self.run_coro(self.main.tool_get_issue(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("401", resp.error)
        self.assertNotIn("not found", resp.error)

    # -------------------------------------------------------------------------
    # tool_add_comment tests
    # -------------------------------------------------------------------------

    def test_add_comment_with_hash_string(self):
        client = Mock()
        client.add_issue_comment = Mock(return_value={"success": True, "comment_id": 101})
        self.main.github_client = client

        req = RequestStub({
            "uid": "test_uid",
            "repo": "owner/repo",
            "issue_number": "#42",
            "body": "Hermetic regression test comment",
        })
        resp = self.run_coro(self.main.tool_add_comment(req))

        self.assertIsNone(resp.error)
        self.assertIn("Comment Added", resp.result)
        client.add_issue_comment.assert_called_once_with(
            access_token="gho_test_token_123",
            repo_full_name="owner/repo",
            issue_number=42,
            body="Hermetic regression test comment",
        )

    def test_add_comment_invalid_number_returns_clean_error(self):
        client = Mock()
        self.main.github_client = client

        req = RequestStub({
            "uid": "test_uid",
            "repo": "owner/repo",
            "issue_number": "invalid-num",
            "body": "Some comment",
        })
        resp = self.run_coro(self.main.tool_add_comment(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("Invalid issue number", resp.error)
        client.add_issue_comment.assert_not_called()

    # -------------------------------------------------------------------------
    # tool_list_issues tests
    # -------------------------------------------------------------------------

    def test_list_issues_api_error_propagates_without_claiming_empty(self):
        client = Mock()
        client.list_issues = Mock(return_value={"success": False, "error": "GitHub API error: 401 - Bad credentials"})
        self.main.github_client = client

        req = RequestStub({"uid": "test_uid", "repo": "owner/repo", "state": "open"})
        resp = self.run_coro(self.main.tool_list_issues(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("401", resp.error)
        self.assertIsNone(resp.result)

    def test_list_issues_empty_repo_reports_no_issues(self):
        client = Mock()
        client.list_issues = Mock(return_value={"success": True, "issues": []})
        self.main.github_client = client

        req = RequestStub({"uid": "test_uid", "repo": "owner/repo", "state": "open"})
        resp = self.run_coro(self.main.tool_list_issues(req))

        self.assertIsNone(resp.error)
        self.assertIn("No open issues found", resp.result)

    def test_list_issues_returns_formatted_results(self):
        client = Mock()
        client.list_issues = Mock(return_value={
            "success": True,
            "issues": [
                {"number": 1, "title": "First issue", "labels": ["bug"]},
                {"number": 2, "title": "Second issue", "labels": []},
            ],
        })
        self.main.github_client = client

        req = RequestStub({"uid": "test_uid", "repo": "owner/repo", "state": "open"})
        resp = self.run_coro(self.main.tool_list_issues(req))

        self.assertIsNone(resp.error)
        self.assertIn("#1", resp.result)
        self.assertIn("First issue", resp.result)
        self.assertIn("[bug]", resp.result)
        self.assertIn("#2", resp.result)


if __name__ == "__main__":
    unittest.main()
