"""Hermetic unit tests for ShipBob plugin security: script-context breakout and error escaping."""

import asyncio
import html
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi import Request

APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT.parent / "omi-plugin-sdk" / "src"))
sys.path.insert(0, str(APP_ROOT))

import main as shipbob_main


def _run(coro):
    return asyncio.run(coro)


class ShipBobSecurityTests(unittest.TestCase):
    def setUp(self):
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.scope = {"type": "http", "method": "GET"}

    def test_setup_escapes_script_tag_breakout_in_uid(self):
        evil_uid = "attacker</script><script>alert('pwned')</script>"
        with patch.object(shipbob_main, "get_shipbob_tokens", return_value={"access_token": "tok"}), \
             patch.object(shipbob_main, "get_channels", return_value=[]):
            resp = _run(shipbob_main.home(request=self.mock_request, uid=evil_uid))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else str(resp)
            self.assertNotIn("uid: 'attacker</script>", body)
            self.assertIn("<\\/script>", body)

    def test_setup_escapes_single_quotes_in_uid(self):
        evil_uid = "user' + alert(1) + '"
        with patch.object(shipbob_main, "get_shipbob_tokens", return_value={"access_token": "tok"}), \
             patch.object(shipbob_main, "get_channels", return_value=[]):
            resp = _run(shipbob_main.home(request=self.mock_request, uid=evil_uid))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else str(resp)
            self.assertNotIn("uid: 'user' + alert(1) + ''", body)
            self.assertIn("const currentUid =", body)

    def test_setup_url_encodes_links(self):
        uid_with_spaces = "user with spaces"
        with patch.object(shipbob_main, "get_shipbob_tokens", return_value={"access_token": "tok"}), \
             patch.object(shipbob_main, "get_channels", return_value=[]):
            resp = _run(shipbob_main.home(request=self.mock_request, uid=uid_with_spaces))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else str(resp)
            self.assertIn("/disconnect?uid=user%20with%20spaces", body)

    def test_callback_escapes_error_message(self):
        evil_err = "<script>alert('xss')</script>"
        resp = _run(shipbob_main.handle_shipbob_callback(
            request=self.mock_request,
            error=evil_err,
        ))
        body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else str(resp)
        self.assertNotIn(evil_err, body)
        self.assertIn("&lt;script&gt;alert(", body)


if __name__ == "__main__":
    unittest.main()
