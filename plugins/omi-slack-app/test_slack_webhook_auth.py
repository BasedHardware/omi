"""Hermetic tests for the slack transcript-webhook auth guard (#14446).

Before this fix, /webhook trusted the caller-supplied uid query param —
anyone could push transcript segments that posted to a victim's Slack
workspace. Covers require_slack_webhook_auth at the boundary: 503 when
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
SECRET = 'test-slack-webhook-secret'


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
        'slack_webhook_auth', APP_DIR / 'slack_webhook_auth.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = _load_auth_module()


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestRequireSlackWebhookAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get('SLACK_WEBHOOK_SECRET')
        os.environ['SLACK_WEBHOOK_SECRET'] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop('SLACK_WEBHOOK_SECRET', None)
        else:
            os.environ['SLACK_WEBHOOK_SECRET'] = self._old

    def test_unconfigured_secret_fails_closed(self):
        os.environ.pop('SLACK_WEBHOOK_SECRET', None)
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_slack_webhook_auth(_FakeRequest(), uid='u1')
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_rejected(self):
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_slack_webhook_auth(_FakeRequest(), uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected(self):
        req = _FakeRequest(headers={'Authorization': 'Bearer wrong'})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_slack_webhook_auth(req, uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_accepted(self):
        req = _FakeRequest(headers={'Authorization': f'Bearer {SECRET}'})
        self.assertEqual(auth.require_slack_webhook_auth(req, uid='u1'), 'u1')

    def test_query_token_accepted(self):
        req = _FakeRequest(query_params={'slack_webhook_token': SECRET})
        self.assertEqual(auth.require_slack_webhook_auth(req, uid='u1'), 'u1')

    def test_blank_uid_rejected(self):
        req = _FakeRequest(headers={'Authorization': f'Bearer {SECRET}'})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_slack_webhook_auth(req, uid='   ')
        self.assertEqual(ctx.exception.status_code, 422)

    def test_non_ascii_token_rejected_with_401(self):
        req = _FakeRequest(query_params={'slack_webhook_token': 'bad_unicode_🔒_secret'})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_slack_webhook_auth(req, uid='u1')
        self.assertEqual(ctx.exception.status_code, 401)


class TestRequireSlackToolAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get('SLACK_WEBHOOK_SECRET')
        os.environ['SLACK_WEBHOOK_SECRET'] = SECRET

    def tearDown(self):
        if self._old is None:
            os.environ.pop('SLACK_WEBHOOK_SECRET', None)
        else:
            os.environ['SLACK_WEBHOOK_SECRET'] = self._old

    def test_tool_call_without_token_rejected(self):
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_slack_tool_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_tool_call_with_token_accepted(self):
        req = _FakeRequest(headers={'Authorization': f'Bearer {SECRET}'})
        self.assertIsNone(auth.require_slack_tool_auth(req))

    def test_non_ascii_tool_token_rejected_with_401(self):
        req = _FakeRequest(query_params={'slack_webhook_token': 'bad_unicode_🔒_secret'})
        with self.assertRaises(auth.HTTPException) as ctx:
            auth.require_slack_tool_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)


class TestSlackRouteDependencyWiring(unittest.TestCase):
    """Static tripwire: assert auth Depends(...) is attached to /webhook and /api/* routes."""

    def test_routes_declare_expected_auth_dependencies(self):
        import ast

        source = (APP_DIR / 'main.py').read_text(encoding='utf-8')
        tree = ast.parse(source)

        funcs = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        expected = {
            'webhook': 'require_slack_webhook_auth',
            'chat_tool_send_message': 'require_slack_tool_auth',
            'chat_tool_search_messages': 'require_slack_tool_auth',
            'chat_tool_search_channels': 'require_slack_tool_auth',
        }

        for fn_name, expected_dep in expected.items():
            self.assertIn(fn_name, funcs, f'Route handler {fn_name} must exist')
            fn = funcs[fn_name]
            dep_names = [
                getattr(d.args[0], 'id', getattr(d.args[0], 'attr', None))
                for d in fn.args.defaults
                if isinstance(d, ast.Call)
                and getattr(d.func, 'id', getattr(d.func, 'attr', None)) == 'Depends'
                and d.args
            ]
            self.assertIn(
                expected_dep,
                dep_names,
                f'Route handler {fn_name} must declare Depends({expected_dep})',
            )


if __name__ == '__main__':
    unittest.main()
