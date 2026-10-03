"""Hermetic unit tests for public shared conversation chat resilience.

Verifies defensive error boundaries, malformed conversation handling,
null transcript segments, dependency override flexibility, arity detection,
Content-Length conflict validation, and validation error mapping in
backend/routers/public_shared_conversation_chat.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Save sys.modules snapshot for clean import isolation
_INITIAL_SYS_MODULES = dict(sys.modules)


class MockSegment:
    def __init__(self, text: str, speaker: str = 'SPEAKER_0'):
        self.text = text
        self.speaker = speaker


class MockHistoryMessage:
    def __init__(self, role: str, content: str):
        self._role = role
        self._content = content

    def model_dump(self):
        return {'role': self._role, 'content': self._content}


class MockChatRequest:
    def __init__(self, question: str = 'What was discussed?', history=None):
        self.conversation_id = 'test-conv-123'
        self.question = question
        self.history = history if history is not None else []


class TestPublicSharedChatResilience(unittest.TestCase):
    """Hermetic unit test suite exercising public shared chat routes."""

    @classmethod
    def setUpClass(cls):
        # Install mocks only for missing dependencies
        cls.stubs_installed = []
        for mod in [
            'fastapi',
            'fastapi.exceptions',
            'fastapi.routing',
            'fastapi.responses',
            'starlette',
            'starlette.datastructures',
            'starlette.types',
            'firebase_admin',
            'firebase_admin.auth',
            'prometheus_client',
            'google',
            'google.auth',
            'google.auth.transport',
            'google.auth.transport.requests',
            'google.oauth2',
            'google.oauth2.id_token',
            'database',
            'database.users',
            'models',
            'models.conversation',
            'utils',
            'utils.conversations',
            'utils.conversations.shared_chat',
            'utils.executors',
            'utils.llm',
            'utils.llm.gateway_client',
        ]:
            if mod not in sys.modules:
                cls.stubs_installed.append(mod)
                m = MagicMock()
                if mod == 'fastapi':
                    class MockHTTPException(Exception):
                        def __init__(self, status_code, detail, headers=None):
                            super().__init__(detail)
                            self.status_code = status_code
                            self.detail = detail
                            self.headers = headers or {}
                    m.HTTPException = MockHTTPException
                    m.APIRouter = MagicMock()
                    class MockRequest:
                        def __init__(self, scope=None, receive=None, send=None):
                            self.scope = scope or {}
                            self.receive = receive
                            self.send = send
                    m.Request = MockRequest
                    m.Response = MagicMock
                elif mod == 'fastapi.exceptions':
                    class MockRequestValidationError(Exception):
                        def __init__(self, errors=None):
                            super().__init__('Validation Error')
                            self._errors = errors or [
                                {'msg': 'value must not be blank'}
                            ]
                        def errors(self):
                            return self._errors
                    m.RequestValidationError = MockRequestValidationError
                elif mod == 'fastapi.responses':
                    class MockJSONResponse:
                        def __init__(self, status_code, content, headers=None):
                            self.status_code = status_code
                            self.content = content
                            self.headers = headers or {}
                    m.JSONResponse = MockJSONResponse
                elif mod == 'fastapi.routing':
                    class MockAPIRoute:
                        def __init__(self, *args, **kwargs):
                            pass

                        def get_route_handler(self):
                            async def default_handler(req):
                                return MagicMock()
                            return default_handler
                    m.APIRoute = MockAPIRoute
                elif mod == 'utils.conversations.shared_chat':
                    def build_bounded_transcript(segments, *, max_chars=24000):
                        lines = []
                        for s in segments:
                            if isinstance(s, Mapping):
                                spk = s.get('speaker', 'SPEAKER_0')
                                txt = s.get('text', '')
                                lines.append(f"{spk}: {txt}")
                        joined = "\n".join(lines)
                        return joined[:max_chars]
                    m.build_bounded_transcript = build_bounded_transcript
                    class PublicSharedChatRateLimited(Exception):
                        def __init__(self, retry_after=60, reason='subject_minute'):
                            self.retry_after = retry_after
                            self.reason = reason
                    class PublicSharedChatRateLimiterUnavailable(Exception):
                        pass
                    class SharedConversationUnavailable(Exception):
                        pass
                    m.PublicSharedChatRateLimited = PublicSharedChatRateLimited
                    m.PublicSharedChatRateLimiterUnavailable = (
                        PublicSharedChatRateLimiterUnavailable
                    )
                    m.SharedConversationUnavailable = SharedConversationUnavailable
                elif mod == 'utils.executors':
                    async def mock_run_blocking(executor, func, *args, **kwargs):
                        return None
                    m.run_blocking = mock_run_blocking
                    m.critical_executor = MagicMock()
                    m.db_executor = MagicMock()
                sys.modules[mod] = m

        base_dir = os.path.abspath(os.path.dirname(__file__))
        hardened_path = os.path.join(
            base_dir, 'hardened_public_shared_conversation_chat.py'
        )
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'public_shared_conversation_chat', hardened_path
        )
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        # Strict import isolation: remove all installed stubs to prevent test leakage
        for mod in cls.stubs_installed:
            sys.modules.pop(mod, None)

    def test_gateway_messages_with_none_conversation(self):
        """None conversation safely defaults to empty transcript."""
        req = MockChatRequest(question="Summary please?")
        msgs = self.mod._gateway_messages(req, None)
        self.assertIsInstance(msgs, list)
        self.assertEqual(msgs[0]['role'], 'system')
        self.assertIn('<shared_conversation_transcript>', msgs[0]['content'])
        self.assertEqual(msgs[-1]['role'], 'user')
        self.assertEqual(msgs[-1]['content'], 'Summary please?')

    def test_gateway_messages_with_non_mapping_conversation(self):
        """Corrupt/non-dict conversation object defaults safely to empty transcript."""
        req = MockChatRequest()
        msgs = self.mod._gateway_messages(req, "corrupt_string")
        self.assertIsInstance(msgs, list)
        self.assertEqual(msgs[-1]['role'], 'user')

    def test_gateway_messages_with_malformed_segments(self):
        """Non-sequence transcript_segments do not raise TypeError."""
        req = MockChatRequest()
        for invalid in [12345, {'bad': 'shape'}, True]:
            msgs = self.mod._gateway_messages(
                req, {'transcript_segments': invalid}
            )
            self.assertIsInstance(msgs, list)

    def test_gateway_messages_history_normalization(self):
        """Malformed or empty history turns are safely sanitized."""
        history = [
            MockHistoryMessage('user', 'Hello'),
            MockHistoryMessage('assistant', ''),  # empty content
            {'role': 'assistant', 'content': 'Valid dict turn'},
            None,
            'invalid string turn',
        ]
        req = MockChatRequest(history=history)
        msgs = self.mod._gateway_messages(req, {})
        roles = [m['role'] for m in msgs]
        contents = [m['content'] for m in msgs]
        self.assertEqual(roles[0], 'system')
        self.assertIn('Hello', contents)
        self.assertIn('Valid dict turn', contents)
        self.assertNotIn('', contents[1:-1])

    def test_trusted_frontend_subject_override_with_request_arg(self):
        """Override expecting request parameter succeeds without TypeError."""
        app = MagicMock()
        mock_request = MagicMock()
        mock_request.app = app

        expected_subject = 'a' * 64

        def override_with_arg(req):
            self.assertEqual(req, mock_request)
            return expected_subject

        app.dependency_overrides = {
            self.mod.require_trusted_frontend_subject: override_with_arg
        }
        res = asyncio.run(
            self.mod._trusted_frontend_subject_for_preparse(mock_request)
        )
        self.assertEqual(res, expected_subject)

    def test_trusted_frontend_subject_override_internal_type_error_not_masked(self):
        """Internal TypeError in request-aware override is not mistaken for 0-arg."""
        app = MagicMock()
        mock_request = MagicMock()
        mock_request.app = app
        call_count = 0

        def buggy_override(req):
            nonlocal call_count
            call_count += 1
            raise TypeError("internal bug inside override")

        app.dependency_overrides = {
            self.mod.require_trusted_frontend_subject: buggy_override
        }
        with self.assertRaises(TypeError) as ctx:
            asyncio.run(
                self.mod._trusted_frontend_subject_for_preparse(mock_request)
            )
        self.assertIn("internal bug inside override", str(ctx.exception))
        # Ensure it was called exactly once and not retried as 0-arg
        self.assertEqual(call_count, 1)

    def test_content_length_normalization_comma_separated_production_route(self):
        """Production bounded_route_handler parses matching comma-separated lengths."""
        route = self.mod._BoundedSharedChatRoute(
            path='/v1/conversations/shared/chat',
            endpoint=MagicMock(),
        )
        handler = route.get_route_handler()

        mock_request = MagicMock()
        mock_request.app = MagicMock()
        mock_request.app.dependency_overrides = {
            self.mod.require_trusted_frontend_subject: lambda: 'c' * 64
        }
        mock_request.headers = {
            'content-length': ' 2048 , 2048 ',
            'x-omi-public-chat-subject': 'c' * 64,
        }
        mock_request.state = MagicMock()
        mock_request.receive = AsyncMock(
            return_value={'type': 'http.request', 'body': b'test'}
        )

        res = asyncio.run(handler(mock_request))
        self.assertIsNotNone(res)

    def test_content_length_conflicting_values_rejected(self):
        """Production route handler rejects conflicting Content-Lengths with 400."""
        route = self.mod._BoundedSharedChatRoute(
            path='/v1/conversations/shared/chat',
            endpoint=MagicMock(),
        )
        handler = route.get_route_handler()

        mock_request = MagicMock()
        mock_request.app = MagicMock()
        mock_request.app.dependency_overrides = {
            self.mod.require_trusted_frontend_subject: lambda: 'd' * 64
        }
        mock_request.headers = {
            'content-length': '1024, 2048',
            'x-omi-public-chat-subject': 'd' * 64,
        }
        mock_request.state = MagicMock()

        with self.assertRaises(Exception) as ctx:
            asyncio.run(handler(mock_request))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Conflicting Content-Length values", str(ctx.exception.detail))

    def test_content_length_oversized_rejected(self):
        """Production bounded_route_handler rejects oversized payload with 413."""
        route = self.mod._BoundedSharedChatRoute(
            path='/v1/conversations/shared/chat',
            endpoint=MagicMock(),
        )
        handler = route.get_route_handler()

        mock_request = MagicMock()
        mock_request.app = MagicMock()
        mock_request.app.dependency_overrides = {
            self.mod.require_trusted_frontend_subject: lambda: 'e' * 64
        }
        mock_request.headers = {
            'content-length': '999999',
            'x-omi-public-chat-subject': 'e' * 64,
        }
        mock_request.state = MagicMock()

        with self.assertRaises(Exception) as ctx:
            asyncio.run(handler(mock_request))
        self.assertEqual(ctx.exception.status_code, 413)

    def test_validation_error_mapped_to_400(self):
        """FastAPI RequestValidationError is caught and mapped to 400."""
        route = self.mod._BoundedSharedChatRoute(
            path='/v1/conversations/shared/chat',
            endpoint=MagicMock(),
        )

        from fastapi.exceptions import RequestValidationError
        async def failing_handler(req):
            raise RequestValidationError([{'msg': 'value must not be blank'}])

        with patch.object(
            self.mod.APIRoute, 'get_route_handler', return_value=failing_handler
        ):
            fresh_handler = route.get_route_handler()
            mock_request = MagicMock()
            mock_request.app = MagicMock()
            mock_request.app.dependency_overrides = {
                self.mod.require_trusted_frontend_subject: lambda: 'f' * 64
            }
            mock_request.headers = {'x-omi-public-chat-subject': 'f' * 64}
            mock_request.state = MagicMock()

            with self.assertRaises(Exception) as ctx:
                asyncio.run(fresh_handler(mock_request))
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("value must not be blank", str(ctx.exception.detail))


if __name__ == '__main__':
    unittest.main()
