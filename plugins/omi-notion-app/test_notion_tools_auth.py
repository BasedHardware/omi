"""Hermetic regression tests for the Notion chat-tool shared-secret guard.

Covers the `notion_tools_auth` dependency (fail-closed 503 when unconfigured,
401 on missing/wrong token, accept on Bearer header or `notion_tools_token`
query param) and asserts every chat-tool route is wired to it.
"""

import os
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# The app's models import from omi_plugin_sdk; mirror test_main.py's path setup.
SDK_DIR = os.path.abspath(os.path.join(APP_DIR, "..", "omi-plugin-sdk", "src"))
if os.path.exists(SDK_DIR) and SDK_DIR not in sys.path:
    sys.path.insert(0, SDK_DIR)

from fastapi import HTTPException

import notion_tools_auth as auth

TEST_SECRET = 'test-notion-tools-secret'

PROTECTED_PATHS = {
    '/tools/search',
    '/tools/list_pages',
    '/tools/get_page',
    '/tools/create_page',
    '/tools/update_page',
    '/tools/append_content',
    '/tools/list_databases',
    '/tools/query_database',
}


class _FakeRequest:
    """Minimal stand-in for a FastAPI Request: headers + query_params only."""

    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class NotionToolsAuthUnitTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get('NOTION_TOOLS_SECRET')

    def tearDown(self):
        if self._old is None:
            os.environ.pop('NOTION_TOOLS_SECRET', None)
        else:
            os.environ['NOTION_TOOLS_SECRET'] = self._old

    def test_fails_closed_when_unconfigured(self):
        os.environ.pop('NOTION_TOOLS_SECRET', None)
        with self.assertRaises(HTTPException) as ctx:
            auth.require_notion_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 503)

    def test_401_when_no_token(self):
        os.environ['NOTION_TOOLS_SECRET'] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_notion_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_wrong_bearer_token(self):
        os.environ['NOTION_TOOLS_SECRET'] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_notion_tools_auth(
                _FakeRequest(headers={'Authorization': 'Bearer wrong'})
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_wrong_query_token(self):
        os.environ['NOTION_TOOLS_SECRET'] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_notion_tools_auth(
                _FakeRequest(query_params={'notion_tools_token': 'wrong'})
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_non_bearer_scheme(self):
        os.environ['NOTION_TOOLS_SECRET'] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            auth.require_notion_tools_auth(
                _FakeRequest(headers={'Authorization': f'Basic {TEST_SECRET}'})
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_accepts_bearer_token(self):
        os.environ['NOTION_TOOLS_SECRET'] = TEST_SECRET
        self.assertIsNone(
            auth.require_notion_tools_auth(
                _FakeRequest(headers={'Authorization': f'Bearer {TEST_SECRET}'})
            )
        )

    def test_accepts_query_token(self):
        os.environ['NOTION_TOOLS_SECRET'] = TEST_SECRET
        self.assertIsNone(
            auth.require_notion_tools_auth(
                _FakeRequest(query_params={'notion_tools_token': TEST_SECRET})
            )
        )


class NotionRoutesAuthWiringTests(unittest.TestCase):
    """Every chat-tool route must carry the shared-secret dependency."""

    @classmethod
    def setUpClass(cls):
        import main  # noqa: F401  (registers the FastAPI app)

        cls.app = main.app

    def test_all_chat_tool_routes_require_shared_secret(self):
        protected = set()
        for route in self.app.routes:
            for dep in getattr(route, 'dependencies', None) or []:
                callable_ = getattr(dep, 'dependency', dep)
                if getattr(callable_, '__name__', '') == 'require_notion_tools_auth':
                    protected.add(route.path)
        self.assertEqual(protected, PROTECTED_PATHS)


try:
    from fastapi.testclient import TestClient

    class NotionToolsAuthIntegrationTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            import main  # noqa: F401

            cls.client = TestClient(main.app)

        def setUp(self):
            self._old = os.environ.get('NOTION_TOOLS_SECRET')

        def tearDown(self):
            if self._old is None:
                os.environ.pop('NOTION_TOOLS_SECRET', None)
            else:
                os.environ['NOTION_TOOLS_SECRET'] = self._old

        def test_unauthenticated_request_is_rejected(self):
            os.environ['NOTION_TOOLS_SECRET'] = TEST_SECRET
            response = self.client.post('/tools/search', json={'uid': 'victim'})
            self.assertEqual(response.status_code, 401)

        def test_unconfigured_fails_closed(self):
            os.environ.pop('NOTION_TOOLS_SECRET', None)
            response = self.client.post(
                '/tools/search',
                json={'uid': 'victim'},
                headers={'Authorization': f'Bearer {TEST_SECRET}'},
            )
            self.assertEqual(response.status_code, 503)

        def test_authenticated_request_passes_guard(self):
            os.environ['NOTION_TOOLS_SECRET'] = TEST_SECRET
            response = self.client.post(
                '/tools/search',
                json={'uid': 'victim'},
                headers={'Authorization': f'Bearer {TEST_SECRET}'},
            )
            # The guard passed; the handler then reports the account is not
            # connected, which it does as a 200 envelope, not an auth failure.
            self.assertNotIn(response.status_code, (401, 503))

except ImportError:
    pass


if __name__ == '__main__':
    unittest.main()