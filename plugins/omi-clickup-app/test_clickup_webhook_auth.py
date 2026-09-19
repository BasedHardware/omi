"""Hermetic tests for the clickup transcript-webhook auth guard (#14446).

Before this fix, /webhook trusted the caller-supplied uid query param —
anyone could push transcript segments that posted to a victim's ClickUp
workspace. Covers require_clickup_webhook_auth at the boundary: 503 when
unconfigured, 401 on missing/wrong token, bearer + query token accepted,
422 on blank uid.
"""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SECRET = 'test-clickup-webhook-secret'


def _load_auth_module():
    fa = types.ModuleType('fastapi')

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ''):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class Request:
        pass

    fa.HTTPException = HTTPException
    fa.Request = Request
    fa.Query = lambda default=None, **kwargs: default
    fa.Depends = lambda dependency=None, **kwargs: dependency
    sys.modules.setdefault('fastapi', fa)

    spec = importlib.util.spec_from_file_location(
        'clickup_webhook_auth', APP_DIR / 'clickup_webhook_auth.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = _load_auth_module()


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireClickUpWebhookAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get('CLICKUP_WEBHOOK_SECRET')
        os.environ['CLICKUP_WEBHOOK_SECRET'] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop('CLICKUP_WEBHOOK_SECRET', None)
        else:
            os.environ['CLICKUP_WEBHOOK_SECRET'] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop('CLICKUP_WEBHOOK_SECRET', None)
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_clickup_webhook_auth(_FakeRequest(), uid='u1')
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_clickup_webhook_auth(_FakeRequest(), uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={'Authorization': 'Bearer wrong'})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_clickup_webhook_auth(req, uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={'Authorization': f'Bearer {SECRET}'})
        self.assertEqual(auth.require_clickup_webhook_auth(req, uid='u1'), 'u1')

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={'clickup_webhook_token': SECRET})
        self.assertEqual(auth.require_clickup_webhook_auth(req, uid='u1'), 'u1')

    def test_blank_uid_rejected(self):
        req = _FakeRequest(headers={'Authorization': f'Bearer {SECRET}'})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_clickup_webhook_auth(req, uid='   ')
        self.assertEqual(ctx.exception.status_code, 422)

    def test_non_ascii_token_rejected_with_401(self):
        req = _FakeRequest(query_params={'clickup_webhook_token': 'bad_unicode_🔒_secret'})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_clickup_webhook_auth(req, uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == '__main__':
    unittest.main()
