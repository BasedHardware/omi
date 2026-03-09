"""Tests for WebSocket auth handshake fix (#5447).

Verifies that:
1. WebSocket endpoints send proper close frames on auth failure (not HTTPException)
2. Per-UID rate limiting blocks retry storms
3. /v4/web/listen is NOT affected (uses accept-first pattern)
"""

import asyncio
import unittest
from unittest.mock import patch, MagicMock

from fastapi import FastAPI, WebSocket, Depends
from fastapi.testclient import TestClient
from firebase_admin.auth import InvalidIdTokenError
from starlette.websockets import WebSocketDisconnect

from utils.other.endpoints import get_current_user_uid_ws, get_current_user_uid


class TestWebSocketAuthDependency(unittest.TestCase):
    """Test that get_current_user_uid_ws raises WebSocketException instead of HTTPException."""

    def setUp(self):
        self.app = FastAPI()

        @self.app.websocket("/ws-new")
        async def ws_new(websocket: WebSocket, uid: str = Depends(get_current_user_uid_ws)):
            await websocket.accept()
            await websocket.send_json({"uid": uid})
            await websocket.close()

        @self.app.websocket("/ws-old")
        async def ws_old(websocket: WebSocket, uid: str = Depends(get_current_user_uid)):
            await websocket.accept()
            await websocket.send_json({"uid": uid})
            await websocket.close()

        self.client = TestClient(self.app)

    def test_ws_new_no_auth_header_sends_close_1008(self):
        """No auth header -> WebSocketDisconnect with code 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-new"):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.verify_token', side_effect=InvalidIdTokenError('Token expired'))
    def test_ws_new_invalid_token_sends_close_1008(self, mock_verify):
        """Invalid token -> WebSocketDisconnect with code 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-new", headers={"Authorization": "Bearer invalid_token"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 1008)

    def test_ws_new_malformed_auth_header_sends_close_1008(self):
        """Malformed auth header -> WebSocketDisconnect with code 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-new", headers={"Authorization": "malformed"}):
                self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.try_acquire_listen_lock', return_value=True)
    @patch('utils.other.endpoints.verify_token', return_value='test-uid-123')
    def test_ws_new_valid_token_connects(self, mock_verify, mock_lock):
        """Valid token + rate limit available -> successful connection."""
        with self.client.websocket_connect("/ws-new", headers={"Authorization": "Bearer valid_token"}) as ws:
            data = ws.receive_json()
            self.assertEqual(data["uid"], "test-uid-123")
        mock_verify.assert_called_once_with("valid_token")
        mock_lock.assert_called_once_with("test-uid-123")

    @patch('utils.other.endpoints.try_acquire_listen_lock', return_value=False)
    @patch('utils.other.endpoints.verify_token', return_value='test-uid-456')
    def test_ws_new_rate_limited_sends_close_1008(self, mock_verify, mock_lock):
        """Valid token but rate limited -> WebSocketDisconnect with code 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-new", headers={"Authorization": "Bearer valid_token"}):
                self.fail("Expected WebSocket to be closed due to rate limit")
        self.assertEqual(ctx.exception.code, 1008)
        mock_verify.assert_called_once_with("valid_token")
        mock_lock.assert_called_once_with("test-uid-456")

    @patch('utils.other.endpoints.try_acquire_listen_lock', side_effect=ConnectionError('redis down'))
    @patch('utils.other.endpoints.verify_token', return_value='test-uid-789')
    def test_ws_new_redis_failure_fails_open(self, mock_verify, mock_lock):
        """Redis failure in rate limiter -> fail-open, connection proceeds."""
        with self.client.websocket_connect("/ws-new", headers={"Authorization": "Bearer valid_token"}) as ws:
            data = ws.receive_json()
            self.assertEqual(data["uid"], "test-uid-789")

    @patch('utils.other.endpoints.try_acquire_listen_lock')
    def test_ws_new_no_auth_does_not_call_rate_limiter(self, mock_lock):
        """Missing auth header should short-circuit before rate limiter is called."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-new"):
                pass
        self.assertEqual(ctx.exception.code, 1008)
        mock_lock.assert_not_called()

    @patch('utils.other.endpoints.try_acquire_listen_lock')
    @patch('utils.other.endpoints.verify_token', side_effect=InvalidIdTokenError('expired'))
    def test_ws_new_invalid_token_does_not_call_rate_limiter(self, mock_verify, mock_lock):
        """Invalid token should short-circuit before rate limiter is called."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-new", headers={"Authorization": "Bearer bad"}):
                pass
        self.assertEqual(ctx.exception.code, 1008)
        mock_lock.assert_not_called()

    def test_ws_new_empty_bearer_token_sends_close_1008(self):
        """Authorization: 'Bearer ' (empty token) -> close with 1008."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-new", headers={"Authorization": "Bearer "}):
                pass
        self.assertEqual(ctx.exception.code, 1008)

    @patch('utils.other.endpoints.verify_token', side_effect=RuntimeError('unexpected error'))
    def test_ws_new_unexpected_verify_error_sends_close_1008(self, mock_verify):
        """Unexpected error from verify_token -> close with 1008, not handshake crash."""
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws-new", headers={"Authorization": "Bearer token"}):
                self.fail("Expected connection to fail")
        self.assertEqual(ctx.exception.code, 1008)


class TestWebSocketCloseFrameBehavior(unittest.TestCase):
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


class TestListenEndpointNotAffectWebListen(unittest.TestCase):
    """Verify /v4/listen uses WS auth and /v4/web/listen is unchanged (source-level check)."""

    def _read_transcribe_source(self):
        import os

        path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'transcribe.py')
        with open(path) as f:
            return f.read()

    def test_listen_handler_uses_http_auth_dependency(self):
        """listen_handler should use get_current_user_uid (HTTP variant) — mobile app sends Authorization header."""
        source = self._read_transcribe_source()
        import re

        listen_match = re.search(
            r'@router\.websocket\("/v4/listen"\)\s*\nasync def listen_handler\([^)]+\)',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(listen_match, "Could not find /v4/listen handler")
        handler_sig = listen_match.group()
        self.assertIn('get_current_user_uid)', handler_sig, "/v4/listen must use get_current_user_uid")
        self.assertNotIn(
            'get_current_user_uid_ws', handler_sig, "/v4/listen must NOT use get_current_user_uid_ws"
        )

    def test_web_listen_has_no_uid_dependency(self):
        """web_listen_handler should NOT have uid Depends — uses first-message auth."""
        source = self._read_transcribe_source()
        import re

        web_match = re.search(
            r'@router\.websocket\("/v4/web/listen"\)\s*\nasync def web_listen_handler\([^)]+\)',
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
