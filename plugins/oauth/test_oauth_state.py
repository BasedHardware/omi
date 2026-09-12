"""Hermetic Notion OAuth state regressions.

`get_oauth_url` handed `f"{auth_url}&state={uid}"` to the template: a uid
containing `&`/`#` split `state` into a second parameter or truncated the
URL, and a `?`-less auth_url got a bare `&`. These tests load the real
`client.py` with a `requests` stub and exercise `NotionClient.get_oauth_url`
directly. No network or credentials required.
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit


def _load_client():
    spec = importlib.util.spec_from_file_location(
        "oauth_client", Path(__file__).with_name("client.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"requests": ModuleType("requests")}):
        spec.loader.exec_module(module)
    return module


client = _load_client()

AUTH_URL = "https://api.notion.com/v1/oauth/authorize?client_id=abc&response_type=code&owner=user"


class OAuthStateTests(unittest.TestCase):
    def make(self, auth_url=AUTH_URL):
        return client.NotionClient(auth_url=auth_url)

    def test_uid_with_ampersand_stays_one_state_parameter(self):
        url = self.make().get_oauth_url("u&admin=1")
        params = dict(parse_qsl(urlsplit(url).query))
        self.assertEqual(params["state"], "u&admin=1")
        self.assertEqual(params["client_id"], "abc")

    def test_uid_with_fragment_characters_is_encoded(self):
        url = self.make().get_oauth_url("u#frag?x")
        params = dict(parse_qsl(urlsplit(url).query))
        self.assertEqual(params["state"], "u#frag?x")
        self.assertEqual(urlsplit(url).fragment, "")

    def test_existing_query_bytes_are_preserved(self):
        url = self.make(AUTH_URL + "&redirect_uri=https%3A%2F%2Fcb.example%2Fdone").get_oauth_url("u1")
        self.assertIn("redirect_uri=https%3A%2F%2Fcb.example%2Fdone&state=u1", url)

    def test_queryless_auth_url_uses_question_mark(self):
        url = self.make("https://example.com/auth").get_oauth_url("u1")
        self.assertEqual(url, "https://example.com/auth?state=u1")

    def test_ordinary_uid_unchanged(self):
        url = self.make().get_oauth_url("firebase-uid-123")
        self.assertTrue(url.endswith("&state=firebase-uid-123"))


if __name__ == "__main__":
    unittest.main()
