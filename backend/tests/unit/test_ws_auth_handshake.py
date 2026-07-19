"""Tests for WebSocket auth handshake fix (#5447).

Verifies that:
1. get_current_user_uid_ws_listen sends proper close frames on auth failure (no rate limiter)
2. get_current_user_uid_ws adds per-UID rate limiting on top of auth
3. /v4/web/listen is NOT affected (uses accept-first pattern)

Isolation: ``utils.other.endpoints`` transitively imports ``firebase_admin.auth`` and
several ``database.*`` modules that construct clients / require a Firebase app at
import time. The module-scoped autouse fixture below installs ``firebase_admin`` and
``database`` stubs via the sanctioned ``stub_modules`` reserve helper, exec's
``utils.other.endpoints`` against them, and tears everything down on exit so nothing
leaks to later test files. See ``backend/docs/test_isolation.md`` and DECISIONS D2.
"""

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, WebSocket, WebSocketException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from testing.import_isolation import stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


# Firebase auth exception classes. Defined at module scope so they are available to
# ``@patch(..., side_effect=InvalidIdTokenError(...))`` decorators evaluated at class
# definition time. The module-scoped autouse fixture below installs these *same*
# class objects onto the ``firebase_admin.auth`` stub, so when
# ``utils.other.endpoints`` is exec'd against the stub it binds identical class
# objects -- preserving ``isinstance`` identity for the close-code logic under test.
class CertificateFetchError(Exception):
    pass


class ExpiredIdTokenError(Exception):
    pass


class InvalidIdTokenError(Exception):
    pass


class RevokedIdTokenError(Exception):
    pass


# Populated by the ``_ws_auth_isolation`` module fixture. Tests resolve these module
# globals at call time (after the fixture has run).
get_current_user_uid_ws_listen = None
get_current_user_uid_ws = None
get_current_user_uid = None
database_users_stub = None


def _build_fakes():
    """Build the namespace-package + firebase/database stub mapping for ``stub_modules``."""
    # Namespace packages pointing at the real source dirs so unstubbed submodules
    # (utils.client_device, utils.executors, redis, ...) resolve to the real files.
    database_pkg = types.ModuleType("database")
    database_pkg.__path__ = [str(BACKEND_DIR / "database")]
    utils_pkg = types.ModuleType("utils")
    utils_pkg.__path__ = [str(BACKEND_DIR / "utils")]
    utils_other_pkg = types.ModuleType("utils.other")
    utils_other_pkg.__path__ = [str(BACKEND_DIR / "utils" / "other")]

    # firebase_admin stubs -- must be active before utils.other.endpoints imports.
    firebase_admin_stub = types.ModuleType("firebase_admin")
    firebase_auth_stub = types.ModuleType("firebase_admin.auth")
    firebase_admin_stub.auth = firebase_auth_stub
    for err_cls in (CertificateFetchError, ExpiredIdTokenError, InvalidIdTokenError, RevokedIdTokenError):
        setattr(firebase_auth_stub, err_cls.__name__, err_cls)
    firebase_auth_stub.verify_id_token = MagicMock(side_effect=InvalidIdTokenError("Invalid token"))
    firebase_auth_stub.get_user = MagicMock()

    # database stubs -- must be active before utils.other.endpoints imports.
    database_client_stub = types.ModuleType("database._client")
    database_client_stub.db = MagicMock()
    database_client_stub.document_id_from_seed = MagicMock(return_value="doc-id")

    database_redis_stub = types.ModuleType("database.redis_db")
    database_redis_stub.check_rate_limit = MagicMock(return_value=True)
    database_redis_stub.try_acquire_listen_lock = MagicMock(return_value=True)
    database_redis_stub.try_acquire_user_platform_write_lock = MagicMock(return_value=True)

    users_stub = types.ModuleType("database.users")
    users_stub.record_user_platform = MagicMock()
    users_stub.record_client_device = MagicMock()

    fakes = {
        "database": database_pkg,
        "utils": utils_pkg,
        "utils.other": utils_other_pkg,
        "firebase_admin": firebase_admin_stub,
        "firebase_admin.auth": firebase_auth_stub,
        "database._client": database_client_stub,
        "database.redis_db": database_redis_stub,
        "database.users": users_stub,
        # ``utils.executors`` may already be a polluted stub in sys.modules when a
        # dirty sibling test file was collected earlier in the same process. Pop it
        # so endpoints re-imports the REAL module (run_blocking / critical_executor
        # must be awaitable callables, not MagicMocks). stub_modules restores the
        # prior entry on teardown, so this adds no new pollution.
        "utils.executors": None,
        # Force utils.other.endpoints to re-exec against the fakes even if a prior
        # test file left a cached copy; stub_modules restores/purges it on teardown.
        "utils.other.endpoints": None,
    }
    return fakes, users_stub


@pytest.fixture(scope="module", autouse=True)
def _ws_auth_isolation():
    """Install firebase/database stubs and exec ``utils.other.endpoints`` against them.

    The fakes (and every module pulled in transitively, including
    ``utils.other.endpoints`` itself) are scoped to this module's tests via
    ``stub_modules``: on teardown the fakes are restored and any module key freshly
    loaded during the block is evicted, so no stub-fed module leaks to later files.
    """
    fakes, users_stub = _build_fakes()
    with stub_modules(fakes):
        endpoints = importlib.import_module("utils.other.endpoints")
        endpoints.record_user_platform = users_stub.record_user_platform
        mod = sys.modules[__name__]
        mod.get_current_user_uid_ws_listen = endpoints.get_current_user_uid_ws_listen
        mod.get_current_user_uid_ws = endpoints.get_current_user_uid_ws
        mod.get_current_user_uid = endpoints.get_current_user_uid
        mod.database_users_stub = users_stub
        yield


class WebSocketAuthTestCase(unittest.TestCase):
    def setUp(self):
        database_users_stub.record_user_platform.reset_mock()


class TestWebSocketAuthListen(WebSocketAuthTestCase):
    """Test get_current_user_uid_ws_listen — auth-only, no rate limiter (used by /v4/listen)."""

    def setUp(self):
        super().setUp()
        self.app = FastAPI()

        @self.app.websocket("/ws-listen")
        async def ws_listen(websocket: WebSocket, uid: str = Depends(get_current_user_uid_ws_listen)):
            await websocket.accept()
            await websocket.send_json({"uid": uid})
            await websocket.close()

        self.client = TestClient(self.app)

    def test_no_auth_header_sends_close_1008(self):
        """No auth header -> WebSocketDisconnect with code 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen"):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.verify_token', side_effect=InvalidIdTokenError('bad token'))
    def test_invalid_token_sends_close_1008(self, mock_verify):
        """Invalid token -> WebSocketDisconnect with code 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer invalid_token"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.verify_token', side_effect=InvalidIdTokenError('Token expired'))
    def test_expired_token_sends_close_4001(self, mock_verify):
        """Expired token -> WebSocketDisconnect with code 4001 so clients can refresh."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer expired_token"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4001)

    @patch('utils.other.endpoints.verify_token', side_effect=InvalidIdTokenError('Certificate key not found'))
    def test_certificate_key_error_sends_close_4001(self, mock_verify):
        """Certificate/key failures -> 4001 so clients can force-refresh the token."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer stale_key_token"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4001)

    @patch(
        'utils.other.endpoints.verify_token',
        side_effect=CertificateFetchError('Certificate fetch failed', RuntimeError('network unavailable')),
    )
    def test_certificate_fetch_error_sends_close_4001(self, mock_verify):
        """Real Firebase cert fetch failures -> 4001 so clients can refresh their token."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer cert_fetch_token"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4001)

    @patch('utils.other.endpoints.verify_token', side_effect=InvalidIdTokenError('API key invalid'))
    def test_non_certificate_key_error_sends_close_1008(self, mock_verify):
        """Generic key errors should not be treated as token-refresh certificate failures."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer invalid_key_token"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.verify_token', side_effect=InvalidIdTokenError('Token revoked'))
    def test_revoked_token_sends_close_4004(self, mock_verify):
        """Revoked token -> WebSocketDisconnect with code 4004 so clients can re-login."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer revoked_token"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4004)

    def test_malformed_auth_header_sends_close_1008(self):
        """Malformed auth header -> WebSocketDisconnect with code 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "malformed"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.verify_token', return_value='test-uid-123')
    def test_valid_token_connects(self, mock_verify):
        """Valid token -> successful connection (no rate limiter involved)."""
        with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid_token"}) as ws:
            data = ws.receive_json()
            self.assertEqual(data["uid"], "test-uid-123")
        mock_verify.assert_called_once_with("valid_token")

    def test_empty_bearer_token_sends_close_1008(self):
        """Authorization: 'Bearer ' (empty token) -> close with 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer "}):
                pass
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.verify_token', side_effect=RuntimeError('unexpected error'))
    def test_unexpected_verify_error_sends_close_1008(self, mock_verify):
        """Unexpected error from verify_token -> close with 1008, not handshake crash."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer token"}):
                self.fail("Expected connection to fail")
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.try_acquire_listen_lock')
    @patch('utils.other.endpoints.verify_token', return_value='test-uid-123')
    def test_no_rate_limiter_called(self, mock_verify, mock_lock):
        """get_current_user_uid_ws_listen must NOT call the rate limiter."""
        with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid_token"}) as ws:
            data = ws.receive_json()
            self.assertEqual(data["uid"], "test-uid-123")
        mock_lock.assert_not_called()


class TestWebSocketAuthWithRateLimit(WebSocketAuthTestCase):
    """Test get_current_user_uid_ws — auth + rate limiting."""

    def setUp(self):
        super().setUp()
        self.app = FastAPI()

        @self.app.websocket("/ws-ratelimited")
        async def ws_ratelimited(websocket: WebSocket, uid: str = Depends(get_current_user_uid_ws)):
            await websocket.accept()
            await websocket.send_json({"uid": uid})
            await websocket.close()

        self.client = TestClient(self.app)

    @patch('utils.other.endpoints.try_acquire_listen_lock', return_value=True)
    @patch('utils.other.endpoints.verify_token', return_value='test-uid-123')
    def test_valid_token_and_lock_connects(self, mock_verify, mock_lock):
        """Valid token + rate limit available -> successful connection."""
        with self.client.websocket_connect("/ws-ratelimited", headers={"Authorization": "Bearer valid_token"}) as ws:
            data = ws.receive_json()
            self.assertEqual(data["uid"], "test-uid-123")
        mock_verify.assert_called_once_with("valid_token")
        mock_lock.assert_called_once_with("test-uid-123")

    @patch('utils.other.endpoints.try_acquire_listen_lock', return_value=False)
    @patch('utils.other.endpoints.verify_token', return_value='test-uid-456')
    def test_rate_limited_sends_close_1008(self, mock_verify, mock_lock):
        """Valid token but rate limited -> WebSocketDisconnect with code 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-ratelimited", headers={"Authorization": "Bearer valid_token"}):
                self.fail("Expected WebSocket to be closed due to rate limit")
        self.assertEqual(ctx.exception.code, 1008)
        mock_verify.assert_called_once_with("valid_token")
        mock_lock.assert_called_once_with("test-uid-456")

    @patch('utils.other.endpoints.try_acquire_listen_lock', side_effect=ConnectionError('redis down'))
    @patch('utils.other.endpoints.verify_token', return_value='test-uid-789')
    def test_redis_failure_fails_open(self, mock_verify, mock_lock):
        """Redis failure in rate limiter -> fail-open, connection proceeds."""
        with self.client.websocket_connect("/ws-ratelimited", headers={"Authorization": "Bearer valid_token"}) as ws:
            data = ws.receive_json()
            self.assertEqual(data["uid"], "test-uid-789")

    def test_malformed_auth_header_sends_close_1008(self):
        """Malformed auth header -> WebSocketDisconnect with code 1008 (via shared _verify_ws_auth)."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-ratelimited", headers={"Authorization": "malformed"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 1008)

    @patch(
        'utils.other.endpoints.try_acquire_listen_lock', side_effect=WebSocketException(code=1008, reason='lock ws exc')
    )
    @patch('utils.other.endpoints.verify_token', return_value='test-uid-reraise')
    def test_ws_exception_from_lock_is_reraised(self, mock_verify, mock_lock):
        """WebSocketException from rate limiter is re-raised, not swallowed by fail-open handler."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-ratelimited", headers={"Authorization": "Bearer valid_token"}):
                self.fail("Expected WebSocket to be closed")
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.try_acquire_listen_lock')
    def test_no_auth_does_not_call_rate_limiter(self, mock_lock):
        """Missing auth header should short-circuit before rate limiter is called."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-ratelimited"):
                pass
        self.assertEqual(ctx.exception.code, 1008)
        mock_lock.assert_not_called()

    @patch('utils.other.endpoints.try_acquire_listen_lock')
    @patch('utils.other.endpoints.verify_token', side_effect=InvalidIdTokenError('expired'))
    def test_expired_token_does_not_call_rate_limiter(self, mock_verify, mock_lock):
        """Expired token should short-circuit before rate limiter is called."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-ratelimited", headers={"Authorization": "Bearer bad"}):
                pass
        self.assertEqual(ctx.exception.code, 4001)
        mock_lock.assert_not_called()


class TestWebSocketCloseFrameBehavior(WebSocketAuthTestCase):
    """Test that WebSocketException actually sends ASGI close message (vs HTTPException which doesn't)."""

    def test_ws_exception_sends_close_message(self):
        """Verify WebSocketException sends websocket.close ASGI message."""
        from fastapi import WebSocketException

        app = FastAPI()

        def dep_ws():
            raise WebSocketException(code=1008, reason="test rejection")

        @app.websocket("/test")
        async def handler(ws: WebSocket, _: str = Depends(dep_ws)):
            await ws.accept()

        sent_messages = []

        async def run():
            scope = {
                'type': 'websocket',
                'asgi': {'version': '3.0', 'spec_version': '2.3'},
                'http_version': '1.1',
                'scheme': 'ws',
                'method': 'GET',
                'path': '/test',
                'raw_path': b'/test',
                'query_string': b'',
                'root_path': '',
                'headers': [],
                'client': ('127.0.0.1', 12345),
                'server': ('testserver', 80),
                'subprotocols': [],
                'state': {},
            }
            recv_events = [{'type': 'websocket.connect'}]

            async def receive():
                if recv_events:
                    return recv_events.pop(0)
                await asyncio.sleep(3600)

            async def send(msg):
                sent_messages.append(msg)

            await app(scope, receive, send)

        asyncio.run(run())

        # WebSocketException should produce a websocket.close message
        close_messages = [m for m in sent_messages if m.get('type') == 'websocket.close']
        self.assertEqual(
            len(close_messages), 1, f"Expected 1 close message, got {len(close_messages)}: {sent_messages}"
        )
        self.assertEqual(close_messages[0]['code'], 1008)

    def test_http_exception_sends_no_close_message(self):
        """Verify HTTPException does NOT send any ASGI message (causes LB 5xx)."""
        from fastapi import HTTPException

        app = FastAPI()

        def dep_http():
            raise HTTPException(status_code=401, detail="unauthorized")

        @app.websocket("/test")
        async def handler(ws: WebSocket, _: str = Depends(dep_http)):
            await ws.accept()

        sent_messages = []

        async def run():
            scope = {
                'type': 'websocket',
                'asgi': {'version': '3.0', 'spec_version': '2.3'},
                'http_version': '1.1',
                'scheme': 'ws',
                'method': 'GET',
                'path': '/test',
                'raw_path': b'/test',
                'query_string': b'',
                'root_path': '',
                'headers': [],
                'client': ('127.0.0.1', 12345),
                'server': ('testserver', 80),
                'subprotocols': [],
                'state': {},
            }
            recv_events = [{'type': 'websocket.connect'}]

            async def receive():
                if recv_events:
                    return recv_events.pop(0)
                await asyncio.sleep(3600)

            async def send(msg):
                sent_messages.append(msg)

            await app(scope, receive, send)

        asyncio.run(run())

        # HTTPException should produce NO websocket.close message — this is the bug
        close_messages = [m for m in sent_messages if m.get('type') == 'websocket.close']
        self.assertEqual(len(close_messages), 0, f"HTTPException should not send close frame, got: {sent_messages}")


class TestListenEndpointNotAffectWebListen(WebSocketAuthTestCase):
    """Verify /v4/listen uses WS auth (no rate limiter) and /v4/web/listen is unchanged (source-level check)."""

    def _read_transcribe_source(self):
        import os

        path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'transcribe.py')
        with open(path, encoding='utf-8') as f:
            return f.read()

    def test_listen_handler_uses_ws_listen_auth(self):
        """listen_handler should use get_current_user_uid_ws_listen (WS auth, no rate limiter)."""
        source = self._read_transcribe_source()
        import re

        listen_match = re.search(
            r"@router\.websocket\(['\"]/v4/listen['\"]\)\s*\nasync def listen_handler\([^)]+\)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(listen_match, "Could not find /v4/listen handler")
        handler_sig = listen_match.group()
        self.assertIn(
            'get_current_user_uid_ws_listen', handler_sig, "/v4/listen must use get_current_user_uid_ws_listen"
        )

    def test_web_listen_has_no_uid_dependency(self):
        """web_listen_handler should NOT have uid Depends — uses first-message auth."""
        source = self._read_transcribe_source()
        import re

        web_match = re.search(
            r"@router\.websocket\(['\"]/v4/web/listen['\"]\)\s*\nasync def web_listen_handler\([^)]+\)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(web_match, "Could not find /v4/web/listen handler")
        handler_sig = web_match.group()
        self.assertNotIn(
            'get_current_user_uid',
            handler_sig,
            "/v4/web/listen must NOT have auth dependency — uses accept-first pattern",
        )


if __name__ == '__main__':
    unittest.main()
