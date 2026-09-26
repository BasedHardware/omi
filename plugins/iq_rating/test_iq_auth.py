"""Tests for plugins/iq_rating/iq_auth.py — uid-keyed data-plane auth.

Run: python3 plugins/iq_rating/test_iq_auth.py
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_ENV = 'IQ_RATING_SECRET'


class FakeRequest:
    def __init__(self, authorization=None, query_params=None):
        self.headers = {}
        if authorization is not None:
            self.headers['Authorization'] = authorization
        self.query_params = query_params or {}


class _HTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _load():
    """Import iq_auth with a minimal fastapi stub (repo tests run without deps)."""
    fastapi = types.ModuleType('fastapi')

    def _query(default=None, **_kwargs):
        return default

    fastapi.HTTPException = _HTTPException
    fastapi.Query = _query
    fastapi.Request = FakeRequest
    sys.modules.setdefault('fastapi', fastapi)

    for name in ('iq_rating.iq_auth', 'iq_rating'):
        sys.modules.pop(name, None)
    pkg = types.ModuleType('iq_rating')
    pkg.__path__ = [os.path.join(os.path.dirname(__file__))]
    sys.modules['iq_rating'] = pkg

    import importlib
    return importlib.import_module('iq_rating.iq_auth')


class IqAuthTest(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        os.environ[_ENV] = 'test-secret'

    def tearDown(self):
        os.environ.pop(_ENV, None)

    def test_missing_secret_fails_closed_503(self):
        os.environ.pop(_ENV, None)
        with self.assertRaises(_HTTPException) as ctx:
            self.mod.require_iq_auth(FakeRequest(query_params={'uid': 'u1'}), uid='u1')
        self.assertEqual(ctx.exception.status_code, 503)

    def test_blank_secret_fails_closed_503(self):
        os.environ[_ENV] = '   '
        with self.assertRaises(_HTTPException) as ctx:
            self.mod.require_iq_auth(FakeRequest(query_params={'uid': 'u1'}), uid='u1')
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_401(self):
        with self.assertRaises(_HTTPException) as ctx:
            self.mod.require_iq_auth(FakeRequest(query_params={'uid': 'u1'}), uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_401(self):
        req = FakeRequest(authorization='Bearer nope', query_params={'uid': 'u1'})
        with self.assertRaises(_HTTPException) as ctx:
            self.mod.require_iq_auth(req, uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_bearer_scheme_ignored(self):
        req = FakeRequest(authorization='Basic test-secret', query_params={'uid': 'u1'})
        with self.assertRaises(_HTTPException) as ctx:
            self.mod.require_iq_auth(req, uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = FakeRequest(authorization='Bearer test-secret', query_params={'uid': 'u1'})
        self.assertEqual(self.mod.require_iq_auth(req, uid='u1'), 'u1')

    def test_query_token_accepted(self):
        req = FakeRequest(query_params={'uid': 'u1', 'iq_rating_token': 'test-secret'})
        self.assertEqual(self.mod.require_iq_auth(req, uid='u1'), 'u1')

    def test_uid_trimmed(self):
        req = FakeRequest(authorization='Bearer test-secret')
        self.assertEqual(self.mod.require_iq_auth(req, uid='  u1  '), 'u1')

    def test_if_uid_none_passes_unauthenticated(self):
        self.assertIsNone(self.mod.require_iq_auth_if_uid(FakeRequest(), uid=None))
        self.assertIsNone(self.mod.require_iq_auth_if_uid(FakeRequest(), uid='   '))

    def test_if_uid_present_requires_auth(self):
        with self.assertRaises(_HTTPException) as ctx:
            self.mod.require_iq_auth_if_uid(FakeRequest(), uid='victim')
        self.assertEqual(ctx.exception.status_code, 401)
        req = FakeRequest(query_params={'iq_rating_token': 'test-secret'})
        self.assertEqual(self.mod.require_iq_auth_if_uid(req, uid='victim'), 'victim')


class RouteWiringTest(unittest.TestCase):
    """Static check: every uid-keyed iq-rating data route declares the auth dep."""

    def test_routes_use_auth_dependency(self):
        src = open(os.path.join(os.path.dirname(__file__), 'main.py')).read()
        for route in ('/iq/api', '/iq/hide', '/iq/unhide', '/iq/adjust',
                      '/iq/preload', '/iq/refresh'):
            idx = src.find(f'"{route}"')
            self.assertGreater(idx, -1, route)
            body = src[idx:idx + 400]
            self.assertIn('Depends(require_iq_auth)', body, route)
        # /iq page uses the optional-uid variant
        idx = src.find('"/iq", response_class=HTMLResponse')
        self.assertIn('Depends(require_iq_auth_if_uid)', src[idx:idx + 400])
        # JS no longer embeds a raw uid string
        self.assertNotIn("'{uid}'", src)


if __name__ == '__main__':
    unittest.main()
