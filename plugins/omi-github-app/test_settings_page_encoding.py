"""Hermetic tests for HTML escaping and URL encoding on GitHub app pages."""
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


class Response:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Response, RedirectResponse=Response, JSONResponse=Response),
    "simple_storage": module("simple_storage", SimpleUserStorage=Mock()),
    "github_client": module("github_client", GitHubClient=Mock),
    "issue_detector": module("issue_detector", ai_select_labels=Mock()),
    "agent_providers": module(
        "agent_providers",
        run_agent_provider=Mock(),
        PROVIDERS={"claude_code": {"label": "Claude Code"}},
        get_provider_label=lambda p: "Claude Code",
        get_provider_default_key=lambda p: "",
        get_provider_base_url=lambda p: "",
    ),
    "models": module("models", ChatToolResponse=Mock()),
}
spec = importlib.util.spec_from_file_location("github_main_under_test", Path(__file__).with_name("main.py"))
main = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(main)


class GitHubSettingsEncodingTests(unittest.TestCase):
    def test_unauthenticated_page_encodes_uid_and_escapes_auth_url(self):
        malicious_uid = 'test" user<script>alert(1)</script>'
        with patch.object(main.SimpleUserStorage, "get_user", return_value=None):
            content = asyncio.run(main.root(uid=malicious_uid)).content

        self.assertIn('/auth?uid=test%22%20user%3Cscript%3Ealert%281%29%3C%2Fscript%3E', content)
        self.assertNotIn('<a href="/auth?uid=test" user<script>', content)

    def test_authenticated_page_escapes_username(self):
        user = {
            "access_token": "valid_token",
            "github_username": "<script>alert('xss')</script>",
            "selected_repo": "owner/repo",
            "available_repos": [{"full_name": "owner/repo", "private": False}]
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            content = asyncio.run(main.root(uid="u123")).content

        self.assertIn('&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;', content)
        self.assertNotIn("<span class=\"username\">@<script>", content)

    def test_authenticated_page_escapes_repo_names(self):
        user = {
            "access_token": "valid_token",
            "github_username": "octocat",
            "selected_repo": 'malicious"><script>alert(1)</script>',
            "available_repos": [
                {"full_name": 'malicious"><script>alert(1)</script>', "private": True}
            ]
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            content = asyncio.run(main.root(uid="u123")).content

        self.assertIn('&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;', content)
        self.assertNotIn('<option value="malicious"><script>', content)

    def test_authenticated_page_safely_serializes_uid_in_script(self):
        malicious_uid = "user'; alert('pwned'); //"
        user = {
            "access_token": "valid_token",
            "github_username": "octocat",
            "selected_repo": "owner/repo",
            "available_repos": [{"full_name": "owner/repo", "private": False}]
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            content = asyncio.run(main.root(uid=malicious_uid)).content

        self.assertIn('const CURRENT_UID = "user\'; alert(\'pwned\'); //";', content)
        self.assertIn('const ENCODED_UID = encodeURIComponent(CURRENT_UID);', content)
        self.assertNotIn("uid: 'user'; alert('pwned'); //'", content)
        self.assertIn("'/update-repo?uid=' + ENCODED_UID", content)
        self.assertIn("'/refresh-repos?uid=' + ENCODED_UID", content)

    def test_authenticated_page_escapes_script_element_terminator_in_uid(self):
        malicious_uid = "user</script><script>alert('xss')</script>"
        user = {
            "access_token": "valid_token",
            "github_username": "octocat",
            "selected_repo": "owner/repo",
            "available_repos": [{"full_name": "owner/repo", "private": False}]
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            content = asyncio.run(main.root(uid=malicious_uid)).content

        self.assertIn('const CURRENT_UID = "user<\\/script><script>alert(\'xss\')<\\/script>";', content)
        self.assertNotIn('const CURRENT_UID = "user</script>', content)
        self.assertNotIn('</script><script>alert', content)

    def test_callback_success_escapes_username_and_encodes_uid(self):
        mock_github = Mock()
        mock_github.exchange_code_for_token.return_value = {"access_token": "tok123"}
        mock_github.get_user_info.return_value = {"login": "<script>alert(1)</script>"}
        mock_github.list_user_repos.return_value = [{"full_name": "owner/repo"}]

        malicious_uid = 'u123" onmouseover="alert(1)'
        main.oauth_states["valid_state"] = malicious_uid

        with patch.object(main, "github_client", mock_github), \
             patch.object(main.SimpleUserStorage, "save_user", Mock()):
            response = asyncio.run(main.auth_callback(Mock(), code="c1", state="valid_state"))
            content = response.content

        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', content)
        self.assertIn('href="/?uid=u123%22%20onmouseover%3D%22alert%281%29"', content)
        self.assertNotIn('href="/?uid=u123" onmouseover="alert(1)"', content)

    def test_callback_error_escapes_exception_and_encodes_uid(self):
        mock_github = Mock()
        mock_github.exchange_code_for_token.side_effect = Exception("<b>Token Error</b>")

        malicious_uid = 'err_user"><svg/onload=alert(1)>'
        main.oauth_states["valid_state"] = malicious_uid

        with patch.object(main, "github_client", mock_github):
            response = asyncio.run(main.auth_callback(Mock(), code="c1", state="valid_state"))
            content = response.content

        self.assertIn('&lt;b&gt;Token Error&lt;/b&gt;', content)
        self.assertNotIn('<b>Token Error</b>', content)
        self.assertIn('href="/auth?uid=err_user%22%3E%3Csvg%2Fonload%3Dalert%281%29%3E"', content)
        self.assertNotIn('href="/auth?uid=err_user"><svg/onload=alert(1)>', content)


if __name__ == "__main__":
    unittest.main()
