"""Tests for BYOK security fixes (issue #6880).

Covers: ContextVar safety, WebSocket extraction, headers, middleware isolation, auth dependencies.
"""

from contextvars import copy_context
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from tests.unit._byok_fixtures import _byok_isolation  # noqa: F401

# ---------------------------------------------------------------------------
# 1. ContextVar safety: default is None, not a shared mutable dict
# ---------------------------------------------------------------------------


class TestContextVarSafety:
    def test_default_is_none(self):
        from utils.byok import _byok_ctx

        assert _byok_ctx.get() is None

    def test_get_byok_keys_returns_empty_dict_by_default(self):
        from utils.byok import get_byok_keys

        ctx = copy_context()
        result = ctx.run(get_byok_keys)
        assert result == {}

    def test_get_byok_key_returns_none_by_default(self):
        from utils.byok import get_byok_key

        ctx = copy_context()
        result = ctx.run(get_byok_key, 'openai')
        assert result is None

    def test_set_and_get_keys(self):
        from utils.byok import get_byok_keys, set_byok_keys

        ctx = copy_context()

        def _run():
            set_byok_keys({'openai': 'sk-test', 'deepgram': 'dg-test'})
            keys = get_byok_keys()
            assert keys == {'openai': 'sk-test', 'deepgram': 'dg-test'}

        ctx.run(_run)

    def test_set_filters_empty_values(self):
        from utils.byok import get_byok_keys, set_byok_keys

        ctx = copy_context()

        def _run():
            set_byok_keys({'openai': 'sk-test', 'anthropic': '', 'gemini': None})
            keys = get_byok_keys()
            assert 'openai' in keys
            assert 'anthropic' not in keys
            assert 'gemini' not in keys

        ctx.run(_run)

    def test_has_byok_keys(self):
        from utils.byok import has_byok_keys, set_byok_keys

        ctx = copy_context()

        def _run():
            assert not has_byok_keys()
            set_byok_keys({'openai': 'sk-test'})
            assert has_byok_keys()

        ctx.run(_run)


# ---------------------------------------------------------------------------
# 2. WebSocket BYOK extraction
# ---------------------------------------------------------------------------


class TestWebSocketExtraction:
    def _make_ws(self, headers: Dict[str, str]) -> MagicMock:
        ws = MagicMock()
        ws.headers = headers
        return ws

    def test_extracts_all_four_headers(self):
        from utils.byok import extract_byok_from_websocket

        ws = self._make_ws(
            {
                'x-byok-openai': 'sk-o',
                'x-byok-anthropic': 'sk-a',
                'x-byok-gemini': 'sk-g',
                'x-byok-deepgram': 'sk-d',
            }
        )
        keys = extract_byok_from_websocket(ws)
        assert keys == {'openai': 'sk-o', 'anthropic': 'sk-a', 'gemini': 'sk-g', 'deepgram': 'sk-d'}

    def test_returns_empty_when_no_headers(self):
        from utils.byok import extract_byok_from_websocket

        ws = self._make_ws({})
        keys = extract_byok_from_websocket(ws)
        assert keys == {}

    def test_partial_headers(self):
        from utils.byok import extract_byok_from_websocket

        ws = self._make_ws({'x-byok-deepgram': 'dg-key'})
        keys = extract_byok_from_websocket(ws)
        assert keys == {'deepgram': 'dg-key'}

    def test_ignores_unknown_headers(self):
        from utils.byok import extract_byok_from_websocket

        ws = self._make_ws({'x-byok-unknown': 'val', 'x-byok-openai': 'sk-o'})
        keys = extract_byok_from_websocket(ws)
        assert keys == {'openai': 'sk-o'}


# ---------------------------------------------------------------------------
# 8. BYOK headers constant is public and correct
# ---------------------------------------------------------------------------


class TestBYOKHeadersConstant:
    def test_headers_has_all_supported_providers(self):
        from utils.byok import BYOK_HEADERS

        assert set(BYOK_HEADERS.keys()) == {'openai', 'anthropic', 'gemini', 'openrouter', 'deepgram'}

    def test_headers_are_lowercase(self):
        from utils.byok import BYOK_HEADERS

        for header in BYOK_HEADERS.values():
            assert header == header.lower()

    def test_headers_start_with_x_byok(self):
        from utils.byok import BYOK_HEADERS

        for header in BYOK_HEADERS.values():
            assert header.startswith('x-byok-')


# ---------------------------------------------------------------------------
# 12. Middleware dispatch: context isolation between requests
# ---------------------------------------------------------------------------


class TestMiddlewareIsolation:
    def test_two_contexts_isolated(self):
        """Keys set in one context must not bleed into another."""
        from utils.byok import get_byok_keys, set_byok_keys

        ctx1 = copy_context()
        ctx2 = copy_context()

        ctx1.run(set_byok_keys, {'openai': 'key-a'})
        result2 = ctx2.run(get_byok_keys)
        assert result2 == {}, "Context 2 should not see keys from context 1"

    def test_context_reset_clears_keys(self):
        """After ContextVar.reset(), keys from previous set are gone."""
        from utils.byok import _byok_ctx, get_byok_keys

        ctx = copy_context()

        def _run():
            token = _byok_ctx.set({'openai': 'temp-key'})
            assert get_byok_keys() == {'openai': 'temp-key'}
            _byok_ctx.reset(token)
            assert get_byok_keys() == {}

        ctx.run(_run)


# ---------------------------------------------------------------------------
# 17. Auth dependency integration tests
# ---------------------------------------------------------------------------


class TestAuthDependencyBYOKIntegration:
    """Verify shared auth dependencies call (or skip) BYOK validation."""

    @patch('utils.other.endpoints.validate_byok_request')
    @patch('utils.other.endpoints.get_user_deletion_wipe_status', return_value=None)
    @patch('utils.other.endpoints.record_user_platform')
    @patch('utils.other.endpoints.verify_token', return_value='uid-123')
    def test_get_current_user_uid_calls_byok_validation(
        self, _mock_verify, _mock_platform, _mock_deletion, mock_validate
    ):
        from utils.other.endpoints import get_current_user_uid

        uid = get_current_user_uid(authorization='Bearer fake-token')
        assert uid == 'uid-123'
        mock_validate.assert_called_once_with('uid-123')

    @patch('utils.other.endpoints.get_user_deletion_wipe_status', return_value=None)
    @patch('utils.other.endpoints.record_user_platform')
    @patch('utils.other.endpoints.verify_token', return_value='uid-456')
    def test_no_byok_validation_skips_validate(self, _mock_verify, _mock_platform, _mock_deletion):
        """get_current_user_uid_no_byok_validation must NOT call validate_byok_request."""
        from utils.other.endpoints import get_current_user_uid_no_byok_validation

        with patch('utils.other.endpoints.validate_byok_request') as mock_validate:
            uid = get_current_user_uid_no_byok_validation(authorization='Bearer fake-token')
            assert uid == 'uid-456'
            mock_validate.assert_not_called()


class TestWSAuthDependencyBYOK:
    """Verify get_current_user_uid_ws_listen extracts BYOK and validates."""

    def _make_ws(self, headers: dict):
        ws = MagicMock()
        ws.headers = headers
        return ws

    @patch('utils.other.endpoints.get_user_deletion_wipe_status', return_value=None)
    @patch('utils.other.endpoints.validate_byok_websocket_keys', return_value=({'openai': 'sk-test'}, None))
    @patch('utils.other.endpoints._verify_ws_auth', return_value='ws-uid')
    def test_ws_listen_with_byok_headers_validates(self, _mock_auth, mock_validate, _mock_deletion):
        import asyncio
        from utils.other.endpoints import get_current_user_uid_ws_listen

        ws = self._make_ws({'x-byok-openai': 'sk-test'})
        uid = asyncio.run(get_current_user_uid_ws_listen(websocket=ws, authorization='Bearer tok'))
        assert uid == 'ws-uid'
        mock_validate.assert_called_once_with('ws-uid', {'openai': 'sk-test'})

    @patch('utils.other.endpoints.get_user_deletion_wipe_status', return_value=None)
    @patch('utils.other.endpoints.validate_byok_websocket_keys', return_value=({}, None))
    @patch('utils.other.endpoints._verify_ws_auth', return_value='ws-uid')
    def test_ws_listen_no_headers_passes(self, _mock_auth, mock_validate, _mock_deletion):
        import asyncio
        from utils.other.endpoints import get_current_user_uid_ws_listen

        ws = self._make_ws({})
        uid = asyncio.run(get_current_user_uid_ws_listen(websocket=ws, authorization='Bearer tok'))
        assert uid == 'ws-uid'
        mock_validate.assert_called_once_with('ws-uid', {})

    @patch('utils.other.endpoints.get_user_deletion_wipe_status', return_value=None)
    @patch('utils.other.endpoints.validate_byok_websocket_keys', return_value=({}, 'fingerprint mismatch'))
    @patch('utils.other.endpoints._verify_ws_auth', return_value='ws-uid')
    def test_ws_listen_validation_failure_raises_4003(self, _mock_auth, _mock_validate, _mock_deletion):
        import asyncio
        from fastapi import WebSocketException
        from utils.other.endpoints import get_current_user_uid_ws_listen

        ws = self._make_ws({'x-byok-openai': 'wrong-key'})
        with pytest.raises(WebSocketException) as exc_info:
            asyncio.run(get_current_user_uid_ws_listen(websocket=ws, authorization='Bearer tok'))
        assert exc_info.value.code == 4003

    @patch('utils.other.endpoints.get_user_deletion_wipe_status', return_value=None)
    @patch('utils.other.endpoints.validate_byok_websocket_keys', return_value=({'openai': 'sk-good'}, None))
    @patch('utils.other.endpoints._verify_ws_auth', return_value='ws-uid')
    def test_ws_listen_installs_only_validated_byok_keys(self, _mock_auth, _mock_validate, _mock_deletion):
        import asyncio
        from utils.byok import get_byok_keys, has_validated_byok_keys
        from utils.other.endpoints import get_current_user_uid_ws_listen

        ws = self._make_ws({'x-byok-openai': 'sk-good', 'x-byok-deepgram': 'rejected'})

        async def authenticate_and_assert_context():
            await get_current_user_uid_ws_listen(websocket=ws, authorization='Bearer tok')
            assert get_byok_keys() == {'openai': 'sk-good'}
            assert has_validated_byok_keys()

        asyncio.run(authenticate_and_assert_context())
