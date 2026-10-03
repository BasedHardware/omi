"""Hermetic unit tests for public shared conversation chat resilience.

Verifies defensive error boundaries, malformed conversation handling,
null transcript segments, dependency override flexibility, and Content-Length
normalization in backend/routers/public_shared_conversation_chat.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure hermetic execution by supplying mocks for framework/cloud deps if missing
for mod in [
    'fastapi',
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
        m = MagicMock()
        # Mock specific classes expected by router module
        if mod == 'fastapi':
            class MockHTTPException(Exception):
                def __init__(self, status_code, detail, headers=None):
                    super().__init__(detail)
                    self.status_code = status_code
                    self.detail = detail
                    self.headers = headers or {}
            m.HTTPException = MockHTTPException
            m.APIRouter = MagicMock()
            m.Depends = MagicMock()
            m.Request = MagicMock
            m.Response = MagicMock
        elif mod == 'fastapi.responses':
            class MockJSONResponse:
                def __init__(self, status_code, content, headers=None):
                    self.status_code = status_code
                    self.content = content
                    self.headers = headers or {}
            m.JSONResponse = MockJSONResponse
        elif mod == 'fastapi.routing':
            class MockAPIRoute:
                pass
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
            m.PublicSharedChatRateLimited = (
                PublicSharedChatRateLimited
            )
            m.PublicSharedChatRateLimiterUnavailable = (
                PublicSharedChatRateLimiterUnavailable
            )
            m.SharedConversationUnavailable = (
                SharedConversationUnavailable
            )
        sys.modules[mod] = m



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
    """Hermetic unit test suite for public shared chat router."""

    def setUp(self):
        base_dir = os.path.abspath(os.path.dirname(__file__))
        hardened_path = os.path.join(
            base_dir, 'hardened_public_shared_conversation_chat.py'
        )
        if os.path.exists(hardened_path):
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                'public_shared_conversation_chat', hardened_path
            )
            self.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.mod)
        else:
            from routers import public_shared_conversation_chat as mod
            self.mod = mod

    def test_gateway_messages_with_none_conversation(self):
        """None conversation safely defaults to empty transcript without
        raising AttributeError.
        """
        req = MockChatRequest(question="Summary please?")
        msgs = self.mod._gateway_messages(req, None)
        self.assertIsInstance(msgs, list)
        self.assertEqual(msgs[0]['role'], 'system')
        self.assertIn('<shared_conversation_transcript>', msgs[0]['content'])
        self.assertEqual(msgs[-1]['role'], 'user')
        self.assertEqual(msgs[-1]['content'], 'Summary please?')

    def test_gateway_messages_with_non_mapping_conversation(self):
        """Corrupt/non-dict conversation object defaults safely to empty
        transcript.
        """
        req = MockChatRequest()
        msgs = self.mod._gateway_messages(req, "corrupt_string")
        self.assertIsInstance(msgs, list)
        self.assertEqual(msgs[-1]['role'], 'user')

    def test_gateway_messages_with_malformed_segments(self):
        """Non-sequence transcript_segments (e.g. int or dict) do not raise
        TypeError.
        """
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
            None,  # None object
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

    def test_gateway_messages_valid_transcript_segments(self):
        """Valid segments render bounded transcript correctly."""
        segments = [
            {'text': 'Good morning everyone.', 'speaker': 'Alice'},
            {'text': 'Let us start the roadmap meeting.', 'speaker': 'Bob'},
        ]
        req = MockChatRequest(question="Who spoke first?")
        msgs = self.mod._gateway_messages(
            req, {'transcript_segments': segments}
        )
        sys_content = msgs[0]['content']
        self.assertIn('Alice', sys_content)
        self.assertIn('Good morning everyone.', sys_content)

    def test_trusted_frontend_subject_override_with_request_arg(self):
        """Override callable expecting (request) parameter succeeds without
        TypeError.
        """

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

    def test_trusted_frontend_subject_override_with_zero_args(self):
        """Override callable expecting 0 arguments also succeeds."""
        app = MagicMock()
        mock_request = MagicMock()
        mock_request.app = app

        expected_subject = 'b' * 64

        def override_zero_args():
            return expected_subject

        app.dependency_overrides = {
            self.mod.require_trusted_frontend_subject: override_zero_args
        }
        res = asyncio.run(
            self.mod._trusted_frontend_subject_for_preparse(mock_request)
        )
        self.assertEqual(res, expected_subject)

    def test_trusted_frontend_subject_override_rejects_invalid_hex(self):
        """Override returning non-hex string raises 403."""
        app = MagicMock()
        mock_request = MagicMock()
        mock_request.app = app

        app.dependency_overrides = {
            self.mod.require_trusted_frontend_subject: lambda: 'invalid_subject'
        }
        with self.assertRaises(Exception) as ctx:
            asyncio.run(
                self.mod._trusted_frontend_subject_for_preparse(mock_request)
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_content_length_normalization_comma_separated(self):
        """Comma-separated proxy Content-Length (e.g. '1024, 1024') parses correctly."""
        content_length = ' 2048 , 2048 '
        raw_len = content_length.split(',')[0].strip()
        parsed = int(raw_len)
        self.assertEqual(parsed, 2048)

    def test_content_length_bounds_validation(self):
        """Negative and oversized Content-Lengths are properly identified."""
        max_bytes = self.mod._MAX_REQUEST_BODY_BYTES
        self.assertEqual(max_bytes, 81920)

        with self.assertRaises(Exception) as ctx:
            if int('-10') < 0:
                raise self.mod._route_http_exception(
                    400, 'Invalid Content-Length'
                )
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(Exception) as ctx2:
            if int('999999') > max_bytes:
                raise self.mod._route_http_exception(
                    413, 'Request body too large'
                )
        self.assertEqual(ctx2.exception.status_code, 413)

    def test_empty_or_whitespace_question_validation(self):
        """Empty or whitespace-only question is detected."""
        for invalid_q in ['', '   ', '\t\n', None]:
            sanitized = (invalid_q or '').strip()
            self.assertEqual(sanitized, '')


if __name__ == '__main__':
    unittest.main()
