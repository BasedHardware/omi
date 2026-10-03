"""Tests for the multion auth guard.

Before this fix, POST /multion executed MultiOn browse sessions (real
"add to my Amazon cart" purchases) keyed by a raw uid query param, and
POST /multion/submit_uid wrote the uid -> multion user_id binding with
no verification — anyone could rebind or corrupt any user's state.
Covers require_multion_auth: 503 unconfigured, 401 missing/wrong,
bearer + query token accepted.
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path

import fastapi

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR.parent))  # plugins/ on path so _multion resolves as a package
SECRET = 'test-multion-secret'

from _multion.multion_auth import require_multion_auth  # noqa: E402


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireMultionAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get('MULTION_WEBHOOK_SECRET')
        os.environ['MULTION_WEBHOOK_SECRET'] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop('MULTION_WEBHOOK_SECRET', None)
        else:
            os.environ['MULTION_WEBHOOK_SECRET'] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop('MULTION_WEBHOOK_SECRET', None)
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_multion_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_multion_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={'Authorization': 'Bearer wrong'})
        with self.assertRaises(fastapi.HTTPException) as ctx:
            require_multion_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={'Authorization': f'Bearer {SECRET}'})
        self.assertIsNone(require_multion_auth(req))

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={'multion_token': SECRET})
        self.assertIsNone(require_multion_auth(req))


if __name__ == '__main__':
    unittest.main()
