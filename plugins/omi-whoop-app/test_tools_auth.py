"""Tests for the whoop chat-tools auth guard (#14453).

Before this fix, all /tools/* routes trusted the uid in the JSON body —
anyone could read a victim's Whoop health data (recovery, strain, sleep,
workouts, body measurements, profile) via their stored OAuth token.
Covers require_whoop_tools_auth at the boundary: 503 when unconfigured,
401 on missing/wrong token, bearer + query token accepted.
"""

import importlib.util
import os
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SECRET = 'test-whoop-tools-secret'

import fastapi


def _load_auth_module():
    spec = importlib.util.spec_from_file_location(
        'whoop_tools_auth', APP_DIR / 'whoop_tools_auth.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = _load_auth_module()


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireWhoopToolsAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get('WHOOP_TOOLS_SECRET')
        os.environ['WHOOP_TOOLS_SECRET'] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop('WHOOP_TOOLS_SECRET', None)
        else:
            os.environ['WHOOP_TOOLS_SECRET'] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop('WHOOP_TOOLS_SECRET', None)
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.require_whoop_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.require_whoop_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={'Authorization': 'Bearer wrong'})
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.require_whoop_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={'Authorization': f'Bearer {SECRET}'})
        self.assertIsNone(auth.require_whoop_tools_auth(req))

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={'whoop_tools_token': SECRET})
        self.assertIsNone(auth.require_whoop_tools_auth(req))


class TestDisconnectSig(unittest.TestCase):
    """/disconnect is a browser GET link — it deletes a victim's tokens by
    uid, so the server signs the rendered link and verifies it here."""

    def setUp(self):
        self._old = os.environ.get('WHOOP_TOOLS_SECRET')
        os.environ['WHOOP_TOOLS_SECRET'] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop('WHOOP_TOOLS_SECRET', None)
        else:
            os.environ['WHOOP_TOOLS_SECRET'] = self._old

    def test_valid_sig_accepted(self):
        sig = auth.disconnect_sig('user-1')
        self.assertIsNone(auth.verify_disconnect_sig('user-1', sig))

    def test_wrong_uid_rejected(self):
        sig = auth.disconnect_sig('user-1')
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.verify_disconnect_sig('user-2', sig)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_missing_sig_rejected(self):
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.verify_disconnect_sig('user-1', '')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_unconfigured_fails_closed(self):
        os.environ.pop('WHOOP_TOOLS_SECRET', None)
        with self.assertRaises(fastapi.HTTPException) as ctx:
            auth.verify_disconnect_sig('user-1', 'x')
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
