"""Hermetic regression tests for Notion OAuth state binding.

Before this fix, get_oauth_url sent the raw uid as ``state`` and the
callback did ``uid = state`` verbatim — nothing proved the callback was
the continuation of a flow this server started. An attacker could
initiate OAuth with a victim's uid, complete it for their own Notion
workspace, and the callback would bind the attacker's credentials under
the victim's uid — routing the victim's conversation rows into the
attacker's database. Runs under stdlib unittest (requests stubbed).
"""

import sys
import types
import unittest
from unittest.mock import MagicMock

if "requests" not in sys.modules:
    req = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    req.RequestException = RequestException
    req.post = MagicMock()
    req.get = MagicMock()
    sys.modules["requests"] = req

from oauth import client


def make_client(secret="test-secret"):
    return client.NotionClient(
        oauth_client_id="id",
        oauth_client_secret=secret,
        oauth_redirect_uri="https://example.com/cb",
        auth_url="https://api.notion.com/v1/oauth/authorize?client_id=id",
    )


class TestSignedState(unittest.TestCase):
    def test_oauth_url_carries_signed_state(self):
        c = make_client()
        url = c.get_oauth_url("uid-abc")
        self.assertIn("state=", url)
        state = url.split("state=", 1)[1]
        # URL-quoted signed state; decoded it resolves back to the uid.
        import urllib.parse
        decoded = urllib.parse.unquote(state)
        self.assertEqual(c.uid_from_state(decoded), "uid-abc")

    def test_round_trip(self):
        c = make_client()
        self.assertEqual(c.uid_from_state(c._signed_state("u1")), "u1")

    def test_tampered_uid_rejected(self):
        c = make_client()
        state = c._signed_state("u1")
        self.assertIsNone(c.uid_from_state("victim" + state[2:]))

    def test_tampered_signature_rejected(self):
        c = make_client()
        state = c._signed_state("u1")
        self.assertIsNone(c.uid_from_state(state[:-2] + "00"))

    def test_unsigned_state_rejected(self):
        c = make_client()
        self.assertIsNone(c.uid_from_state("victim-uid"))
        self.assertIsNone(c.uid_from_state(""))
        self.assertIsNone(c.uid_from_state(":sig"))

    def test_wrong_secret_rejected(self):
        issued = make_client("secret-a")._signed_state("u1")
        self.assertIsNone(make_client("secret-b").uid_from_state(issued))


if __name__ == "__main__":
    unittest.main()
