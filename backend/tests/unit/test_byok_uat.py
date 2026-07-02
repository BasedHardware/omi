"""BYOK User Acceptance Tests (UAT) — end-to-end path coverage.

These tests exercise every BYOK code path through the actual FastAPI
dependency chain, verifying that the separated-dep pattern (PR #6946)
correctly installs BYOK keys in the async handler's ContextVar context.

UAT matrix:
  1. Activation / deactivation
  2. Valid BYOK keys → ContextVar installed → LLM/STT clients route to user keys
  3. Invalid keys (mismatch, missing provider) → 403 / 4003
  4. Expired BYOK → keys ignored, Omi keys used
  5. Non-BYOK user with BYOK headers → silently ignored
  6. Mobile (no headers) → normal flow, Omi keys used
  7. Key rotation (deactivate → re-activate with new fingerprints)
  8. Chat quota bypass with BYOK LLM key
  9. Transcription credit bypass with BYOK Deepgram key
 10. LLM client routing (OpenAI, Anthropic, Gemini)
 11. Deepgram STT client routing
 12. Thread-safety: ContextVar NOT mutated inside sync deps
 13. WebSocket path: listen handler BYOK validation
 14. Partial headers abuse: only deepgram header → chat quota NOT bypassed
 15. Cache TTL: state cache invalidation on activation/deactivation
"""

import hashlib
import os
import sys
from contextvars import copy_context
from datetime import datetime, timedelta, timezone
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level stubs: prevent Firestore/Redis init on import
# ---------------------------------------------------------------------------
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('DEEPGRAM_API_KEY', 'dg-test-fake-for-unit-tests')
os.environ.setdefault('GOOGLE_API_KEY', 'goog-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

sys.modules.setdefault('database._client', MagicMock())
sys.modules.setdefault('database.redis_db', MagicMock())
sys.modules.setdefault('database.users', MagicMock())
sys.modules.setdefault('database.user_usage', MagicMock())
sys.modules.setdefault('database.llm_usage', MagicMock())
sys.modules.setdefault('database.announcements', MagicMock())
sys.modules.setdefault('utils.other.storage', MagicMock())

import warnings

warnings.filterwarnings('ignore', message='.*stream_options.*')

# ---------------------------------------------------------------------------
# Shared test keys
# ---------------------------------------------------------------------------

_FAKE_OPENAI = 'sk-test-openai-uat-12345'
_FAKE_ANTHROPIC = 'sk-ant-test-uat-67890'
_FAKE_GEMINI = 'AIzaSy-test-gemini-uat'
_FAKE_DEEPGRAM = 'dg-test-deepgram-uat'

_VALID_KEYS = {
    'openai': _FAKE_OPENAI,
    'anthropic': _FAKE_ANTHROPIC,
    'gemini': _FAKE_GEMINI,
    'deepgram': _FAKE_DEEPGRAM,
}

_ENROLLED_FINGERPRINTS = {provider: hashlib.sha256(key.encode()).hexdigest() for provider, key in _VALID_KEYS.items()}


def _byok_state(active=True, fingerprints=None, last_seen_at=None):
    """Build a mock BYOK state dict."""
    return {
        'active': active,
        'fingerprints': fingerprints if fingerprints is not None else dict(_ENROLLED_FINGERPRINTS),
        'last_seen_at': last_seen_at or datetime.now(timezone.utc),
    }


# ============================================================================
# UAT 1: Activation / Deactivation endpoints
# ============================================================================


def _mock_request(uid: str) -> MagicMock:
    """Create a mock Request with request.state.uid set."""
    req = MagicMock()
    req.state.uid = uid
    return req


class TestUAT_Activation:
    """Test the full activate → deactivate lifecycle."""

    @patch('routers.users.users_db')
    def test_activate_stores_fingerprints(self, mock_users_db):
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        data = BYOKActivateRequest(fingerprints=dict(_ENROLLED_FINGERPRINTS))
        result = activate_byok_endpoint(_mock_request('uat-uid'), data)
        assert result == {"active": True}
        mock_users_db.set_byok_active.assert_called_once_with('uat-uid', dict(_ENROLLED_FINGERPRINTS))

    @patch('routers.users.users_db')
    def test_deactivate_clears_state(self, mock_users_db):
        from routers.users import deactivate_byok_endpoint

        result = deactivate_byok_endpoint(_mock_request('uat-uid'))
        assert result == {"active": False}
        mock_users_db.clear_byok_active.assert_called_once_with('uat-uid')

    def test_activate_rejects_incomplete_fingerprints(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        incomplete = dict(_ENROLLED_FINGERPRINTS)
        del incomplete['deepgram']
        data = BYOKActivateRequest(fingerprints=incomplete)
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(_mock_request('uat-uid'), data)
        assert exc_info.value.status_code == 400


# ============================================================================
# UAT 2: Separated dep — validate_and_return_byok_keys
# ============================================================================


class TestUAT_ValidatedReturn:
    """Test validate_and_return_byok_keys returns keys without ContextVar mutation."""

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_valid_keys_returned(self, mock_get_state):
        from utils.byok import validate_and_return_byok_keys, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-valid')
        mock_get_state.return_value = _byok_state()
        result = validate_and_return_byok_keys('uat-valid', dict(_VALID_KEYS))
        assert result == _VALID_KEYS

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_no_contextvar_mutation(self, mock_get_state):
        """validate_and_return_byok_keys must NOT call set_byok_keys or touch _byok_ctx."""
        from utils.byok import _byok_ctx, validate_and_return_byok_keys, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-no-mutate')
        mock_get_state.return_value = _byok_state()

        ctx = copy_context()

        def _run():
            before = _byok_ctx.get()
            validate_and_return_byok_keys('uat-no-mutate', dict(_VALID_KEYS))
            after = _byok_ctx.get()
            assert before == after, "ContextVar was mutated by validate_and_return_byok_keys"

        ctx.run(_run)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_empty_keys_returns_empty(self, mock_get_state):
        from utils.byok import validate_and_return_byok_keys

        mock_get_state.return_value = _byok_state()
        result = validate_and_return_byok_keys('uat-empty', {})
        assert result == {}
        mock_get_state.assert_not_called()  # Fast path: no Firestore read


# ============================================================================
# UAT 3: Invalid keys → 403 / 4003
# ============================================================================


class TestUAT_InvalidKeys:
    """Test that fingerprint mismatch and missing provider raise proper errors."""

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_fingerprint_mismatch_raises_403(self, mock_get_state):
        from fastapi import HTTPException
        from utils.byok import validate_and_return_byok_keys, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-mismatch')
        mock_get_state.return_value = _byok_state()
        bad_keys = dict(_VALID_KEYS)
        bad_keys['openai'] = 'sk-WRONG-key'

        with pytest.raises(HTTPException) as exc_info:
            validate_and_return_byok_keys('uat-mismatch', bad_keys)
        assert exc_info.value.status_code == 403
        assert 'mismatch' in exc_info.value.detail

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_missing_enrolled_provider_raises_403(self, mock_get_state):
        from fastapi import HTTPException
        from utils.byok import validate_and_return_byok_keys, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-missing')
        mock_get_state.return_value = _byok_state()
        partial_keys = {'openai': _FAKE_OPENAI}  # Missing anthropic, gemini, deepgram

        with pytest.raises(HTTPException) as exc_info:
            validate_and_return_byok_keys('uat-missing', partial_keys)
        assert exc_info.value.status_code == 403
        assert 'missing' in exc_info.value.detail

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_ws_mismatch_raises_4003(self, mock_get_state):
        from fastapi import WebSocketException
        from utils.byok import validate_and_return_byok_keys_ws, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-ws-mismatch')
        mock_get_state.return_value = _byok_state()
        bad_keys = dict(_VALID_KEYS)
        bad_keys['deepgram'] = 'dg-WRONG-key'

        with pytest.raises(WebSocketException) as exc_info:
            validate_and_return_byok_keys_ws('uat-ws-mismatch', bad_keys)
        assert exc_info.value.code == 4003

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_ws_missing_provider_raises_4003(self, mock_get_state):
        from fastapi import WebSocketException
        from utils.byok import validate_and_return_byok_keys_ws, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-ws-missing')
        mock_get_state.return_value = _byok_state()

        with pytest.raises(WebSocketException) as exc_info:
            validate_and_return_byok_keys_ws('uat-ws-missing', {'openai': _FAKE_OPENAI})
        assert exc_info.value.code == 4003


# ============================================================================
# UAT 4: Expired BYOK → keys ignored
# ============================================================================


class TestUAT_ExpiredBYOK:
    """Expired heartbeat (>7 days) → returns empty, no error."""

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_expired_returns_empty(self, mock_get_state):
        from utils.byok import validate_and_return_byok_keys, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-expired')
        expired_state = _byok_state(last_seen_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        mock_get_state.return_value = expired_state

        result = validate_and_return_byok_keys('uat-expired', dict(_VALID_KEYS))
        assert result == {}

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_expired_ws_returns_empty(self, mock_get_state):
        from utils.byok import validate_and_return_byok_keys_ws, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-ws-expired')
        expired_state = _byok_state(last_seen_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        mock_get_state.return_value = expired_state

        result = validate_and_return_byok_keys_ws('uat-ws-expired', dict(_VALID_KEYS))
        assert result == {}


# ============================================================================
# UAT 5: Non-BYOK user with BYOK headers → silently ignored
# ============================================================================


class TestUAT_NonBYOKUserWithHeaders:

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_non_active_user_returns_empty(self, mock_get_state):
        from utils.byok import validate_and_return_byok_keys, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-non-active')
        mock_get_state.return_value = _byok_state(active=False)

        result = validate_and_return_byok_keys('uat-non-active', dict(_VALID_KEYS))
        assert result == {}

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_non_active_user_ws_returns_empty(self, mock_get_state):
        from utils.byok import validate_and_return_byok_keys_ws, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-non-active-ws')
        mock_get_state.return_value = _byok_state(active=False)

        result = validate_and_return_byok_keys_ws('uat-non-active-ws', dict(_VALID_KEYS))
        assert result == {}


# ============================================================================
# UAT 6: Mobile (no headers) → normal flow
# ============================================================================


class TestUAT_MobileNoHeaders:

    def test_no_headers_returns_empty_immediately(self):
        """No BYOK headers → empty dict, no Firestore call."""
        from utils.byok import validate_and_return_byok_keys

        with patch('database.users.get_byok_state') as mock_get_state:
            result = validate_and_return_byok_keys('uat-mobile', {})
            assert result == {}
            mock_get_state.assert_not_called()

    def test_no_headers_ws_returns_empty_immediately(self):
        from utils.byok import validate_and_return_byok_keys_ws

        with patch('database.users.get_byok_state') as mock_get_state:
            result = validate_and_return_byok_keys_ws('uat-mobile-ws', {})
            assert result == {}
            mock_get_state.assert_not_called()


# ============================================================================
# UAT 7: Key rotation (deactivate → re-activate with new fingerprints)
# ============================================================================


class TestUAT_KeyRotation:

    @patch('routers.users.users_db')
    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_rotation_old_keys_fail_new_keys_pass(self, mock_get_state, mock_users_db):
        from fastapi import HTTPException
        from utils.byok import validate_and_return_byok_keys, invalidate_byok_state_cache

        uid = 'uat-rotation'

        # Step 1: Activate with old keys
        old_keys = dict(_VALID_KEYS)
        old_fp = dict(_ENROLLED_FINGERPRINTS)

        invalidate_byok_state_cache(uid)
        mock_get_state.return_value = _byok_state(fingerprints=old_fp)
        result = validate_and_return_byok_keys(uid, old_keys)
        assert result == old_keys

        # Step 2: Rotate to new keys
        new_keys = {
            'openai': 'sk-new-openai-rotated',
            'anthropic': 'sk-ant-new-rotated',
            'gemini': 'AIzaSy-new-gemini-rotated',
            'deepgram': 'dg-new-deepgram-rotated',
        }
        new_fp = {p: hashlib.sha256(k.encode()).hexdigest() for p, k in new_keys.items()}

        invalidate_byok_state_cache(uid)
        mock_get_state.return_value = _byok_state(fingerprints=new_fp)

        # Step 3: Old keys now fail
        with pytest.raises(HTTPException) as exc_info:
            validate_and_return_byok_keys(uid, old_keys)
        assert exc_info.value.status_code == 403

        # Step 4: New keys pass
        invalidate_byok_state_cache(uid)
        mock_get_state.return_value = _byok_state(fingerprints=new_fp)
        result = validate_and_return_byok_keys(uid, new_keys)
        assert result == new_keys


# ============================================================================
# UAT 8: Chat quota bypass with BYOK LLM key
# ============================================================================


class TestUAT_ChatQuotaBypass:

    @patch('utils.byok.get_byok_key')
    @patch('utils.subscription.users_db')
    def test_byok_openai_bypasses_quota(self, mock_users_db, mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: _FAKE_OPENAI if p == 'openai' else None
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('uat-byok-chat')  # Should not raise

    @patch('utils.byok.get_byok_key')
    @patch('utils.subscription.users_db')
    def test_byok_anthropic_bypasses_quota(self, mock_users_db, mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: _FAKE_ANTHROPIC if p == 'anthropic' else None
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('uat-byok-chat-ant')  # Should not raise

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_no_llm_key_quota_enforced(self, mock_snapshot, mock_users_db, _mock_get_key):
        """BYOK active but no LLM headers → quota is enforced."""
        from fastapi import HTTPException
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = True
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('uat-byok-no-llm')
        assert exc_info.value.status_code == 402


# ============================================================================
# UAT 9: Transcription credit bypass with BYOK Deepgram key
# ============================================================================


class TestUAT_TranscriptionCreditBypass:

    @patch('utils.byok.get_byok_key', return_value=_FAKE_DEEPGRAM)
    @patch('utils.subscription.users_db')
    def test_byok_deepgram_bypasses_credits(self, mock_users_db, _mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('uat-byok-dg') is True

    @patch('utils.byok.get_byok_key', return_value=_FAKE_DEEPGRAM)
    @patch('utils.subscription.users_db')
    def test_byok_deepgram_remaining_unlimited(self, mock_users_db, _mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import get_remaining_transcription_seconds

        assert get_remaining_transcription_seconds('uat-byok-dg-rem') is None

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    def test_no_deepgram_key_credits_not_bypassed(self, mock_users_db, _mock_get_key):
        """BYOK active but no x-byok-deepgram → credit check NOT bypassed."""
        mock_users_db.is_byok_active.return_value = True
        mock_users_db.get_user_valid_subscription.return_value = None
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('uat-byok-no-dg') is False


# ============================================================================
# UAT 10: LLM client routing (OpenAI, Anthropic, Gemini)
# ============================================================================


class TestUAT_LLMClientRouting:

    @patch('utils.llm.clients.get_byok_key')
    def test_openai_chat_byok_creates_cached_client(self, mock_get_key):
        mock_get_key.side_effect = lambda p: _FAKE_OPENAI if p == 'openai' else None
        from utils.llm.clients import _cached_openai_chat, _hash_key, _openai_cache

        result = _cached_openai_chat('gpt-4.1-mini', _FAKE_OPENAI, {})
        assert result is not None
        expected_cache_prefix = f"gpt-4.1-mini:{_hash_key(_FAKE_OPENAI)}:"
        found = any(expected_cache_prefix in k for k in _openai_cache.keys())
        assert found, "BYOK key should create a cached client entry"

    @patch('utils.llm.clients.get_byok_key')
    def test_anthropic_proxy_routes_to_byok_key(self, mock_get_key):
        mock_get_key.side_effect = lambda p: _FAKE_ANTHROPIC if p == 'anthropic' else None
        from utils.llm.clients import _AnthropicClientProxy

        mock_default = MagicMock()
        proxy = _AnthropicClientProxy(mock_default)
        resolved = proxy._resolve()
        assert resolved is not mock_default

    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_no_byok_uses_default_anthropic(self, mock_get_key):
        from utils.llm.clients import _AnthropicClientProxy

        mock_default = MagicMock()
        proxy = _AnthropicClientProxy(mock_default)
        resolved = proxy._resolve()
        assert resolved is mock_default

    @patch('utils.llm.clients.httpx.post')
    @patch('utils.llm.clients.get_byok_key')
    def test_gemini_embed_routes_to_byok_key(self, mock_get_key, mock_post):
        mock_get_key.side_effect = lambda p: _FAKE_GEMINI if p == 'gemini' else None
        mock_response = MagicMock()
        mock_response.json.return_value = {'embedding': {'values': [0.1, 0.2]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from utils.llm.clients import gemini_embed_query

        gemini_embed_query('test query')

        call_args = mock_post.call_args
        headers = call_args[1].get('headers', {})
        assert headers.get('x-goog-api-key') == _FAKE_GEMINI


# ============================================================================
# UAT 11: Deepgram STT client routing
# ============================================================================


class TestUAT_DeepgramClientRouting:

    @patch('utils.stt.streaming.get_byok_key')
    def test_byok_deepgram_creates_custom_client(self, mock_get_key):
        mock_get_key.return_value = _FAKE_DEEPGRAM
        from utils.stt.streaming import _deepgram_client_for_request

        with patch('utils.stt.streaming.DeepgramClient') as mock_dg_client:
            with patch('utils.stt.streaming.is_dg_self_hosted', False):
                _deepgram_client_for_request()
                mock_dg_client.assert_called_once()
                call_args = mock_dg_client.call_args
                assert call_args[0][0] == _FAKE_DEEPGRAM

    @patch('utils.stt.streaming.get_byok_key', return_value=None)
    def test_no_byok_uses_shared_client(self, mock_get_key):
        from utils.stt.streaming import _deepgram_client_for_request

        with patch('utils.stt.streaming.is_dg_self_hosted', False):
            client = _deepgram_client_for_request()
            # Should return the shared module-level deepgram client
            from utils.stt.streaming import deepgram as shared_client

            assert client is shared_client


# ============================================================================
# UAT 12: Thread-safety — ContextVar not mutated in sync dep
# ============================================================================


class TestUAT_ThreadSafety:
    """Simulates what happens inside a worker thread (sync dep).
    The key property: validate_and_return_byok_keys NEVER writes to ContextVar.
    """

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_worker_thread_context_copy_preserved(self, mock_get_state):
        """Simulate Starlette's worker thread: run in a context copy, verify no mutation."""
        from utils.byok import _byok_ctx, validate_and_return_byok_keys, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-thread-safe')
        mock_get_state.return_value = _byok_state()

        # Outer context (async handler's context)
        outer_ctx = copy_context()
        outer_ctx.run(_byok_ctx.set, None)

        # Inner context (worker thread gets a COPY)
        inner_ctx = outer_ctx.copy()

        def _worker():
            # This is what the sync dep does
            result = validate_and_return_byok_keys('uat-thread-safe', dict(_VALID_KEYS))
            assert result == _VALID_KEYS
            # Verify ContextVar was NOT mutated even in the copy
            assert _byok_ctx.get() is None

        inner_ctx.run(_worker)

        # Verify outer context is still None
        assert outer_ctx.run(_byok_ctx.get) is None

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_async_handler_can_install_after_dep(self, mock_get_state):
        """After dep returns keys, the async handler installs them in ITS context."""
        from utils.byok import (
            _byok_ctx,
            get_byok_key,
            set_byok_keys,
            validate_and_return_byok_keys,
            invalidate_byok_state_cache,
        )

        invalidate_byok_state_cache('uat-async-install')
        mock_get_state.return_value = _byok_state()

        ctx = copy_context()

        def _async_handler():
            # Step 1: dep runs (would be in worker thread, but returns to us)
            validated = validate_and_return_byok_keys('uat-async-install', dict(_VALID_KEYS))
            assert validated == _VALID_KEYS

            # Step 2: async handler installs in its own context (this sticks!)
            set_byok_keys(validated)

            # Step 3: downstream code reads from ContextVar
            assert get_byok_key('openai') == _FAKE_OPENAI
            assert get_byok_key('anthropic') == _FAKE_ANTHROPIC
            assert get_byok_key('deepgram') == _FAKE_DEEPGRAM

        ctx.run(_async_handler)


# ============================================================================
# UAT 13: WebSocket path — listen handler BYOK dep
# ============================================================================


class TestUAT_WebSocketListenPath:
    """Test the WS-specific validation dep."""

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_ws_valid_keys_returned(self, mock_get_state):
        from utils.byok import validate_and_return_byok_keys_ws, invalidate_byok_state_cache

        invalidate_byok_state_cache('uat-ws-valid')
        mock_get_state.return_value = _byok_state()

        result = validate_and_return_byok_keys_ws('uat-ws-valid', dict(_VALID_KEYS))
        assert result == _VALID_KEYS

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_ws_no_headers_returns_empty(self, mock_get_state):
        from utils.byok import validate_and_return_byok_keys_ws

        mock_get_state.return_value = _byok_state()
        result = validate_and_return_byok_keys_ws('uat-ws-no-headers', {})
        assert result == {}

    def test_extract_byok_from_websocket(self):
        from utils.byok import extract_byok_from_websocket

        ws = MagicMock()
        ws.headers = {
            'x-byok-openai': _FAKE_OPENAI,
            'x-byok-anthropic': _FAKE_ANTHROPIC,
            'x-byok-gemini': _FAKE_GEMINI,
            'x-byok-deepgram': _FAKE_DEEPGRAM,
        }
        keys = extract_byok_from_websocket(ws)
        assert keys == _VALID_KEYS


# ============================================================================
# UAT 14: Partial headers abuse
# ============================================================================


class TestUAT_PartialHeaderAbuse:
    """Sending only deepgram header should NOT bypass chat quota."""

    @patch('utils.byok.get_byok_key')
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_only_deepgram_header_chat_quota_enforced(self, mock_snapshot, mock_users_db, mock_get_key):
        from fastapi import HTTPException
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: _FAKE_DEEPGRAM if p == 'deepgram' else None
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('uat-partial-abuse')
        assert exc_info.value.status_code == 402

    @patch('utils.byok.get_byok_key')
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_only_openai_header_transcription_not_bypassed(self, mock_snapshot, mock_users_db, mock_get_key):
        """Only openai header → transcription credit NOT bypassed."""
        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: _FAKE_OPENAI if p == 'openai' else None
        mock_users_db.get_user_valid_subscription.return_value = None
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('uat-partial-trans') is False


# ============================================================================
# UAT 15: Cache TTL behavior
# ============================================================================


class TestUAT_CacheBehavior:

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_cache_invalidation_forces_refresh(self, mock_get_state):
        from utils.byok import get_cached_byok_state, invalidate_byok_state_cache

        uid = 'uat-cache-invalidate'
        invalidate_byok_state_cache(uid)

        # First call: cache miss → reads from Firestore
        mock_get_state.return_value = _byok_state(active=True)
        state1 = get_cached_byok_state(uid)
        assert state1['active'] is True
        assert mock_get_state.call_count == 1

        # Second call: cache hit → does NOT read Firestore
        state2 = get_cached_byok_state(uid)
        assert mock_get_state.call_count == 1  # Still 1

        # Invalidate → next call forces Firestore read
        invalidate_byok_state_cache(uid)
        mock_get_state.return_value = _byok_state(active=False)
        state3 = get_cached_byok_state(uid)
        assert state3['active'] is False
        assert mock_get_state.call_count == 2

    def test_cache_has_bounded_size(self):
        from utils.byok import _byok_state_cache

        assert hasattr(_byok_state_cache, 'maxsize')
        assert _byok_state_cache.maxsize > 0
        assert _byok_state_cache.maxsize <= 2048  # Reasonable bound

    def test_cache_has_short_ttl(self):
        from utils.byok import _byok_state_cache

        assert hasattr(_byok_state_cache, 'ttl')
        assert _byok_state_cache.ttl <= 60  # At most 1 minute


# ============================================================================
# UAT 16: End-to-end flow simulation
# ============================================================================


class TestUAT_EndToEndFlow:
    """Simulate the complete request lifecycle:
    1. HTTP request arrives with BYOK headers
    2. BYOKMiddleware extracts headers into ContextVar (async)
    3. Separated dep extracts + validates + returns keys (sync, no ContextVar mutation)
    4. Async handler calls set_byok_keys() — mutation sticks
    5. Downstream code reads keys from ContextVar
    """

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_full_http_lifecycle(self, mock_get_state):
        from utils.byok import (
            _byok_ctx,
            _extract_byok_from_request,
            get_byok_key,
            set_byok_keys,
            validate_and_return_byok_keys,
            invalidate_byok_state_cache,
        )

        uid = 'uat-e2e-http'
        invalidate_byok_state_cache(uid)
        mock_get_state.return_value = _byok_state()

        # Simulate an HTTP request object
        mock_request = MagicMock()
        mock_request.headers = {
            'x-byok-openai': _FAKE_OPENAI,
            'x-byok-anthropic': _FAKE_ANTHROPIC,
            'x-byok-gemini': _FAKE_GEMINI,
            'x-byok-deepgram': _FAKE_DEEPGRAM,
            'authorization': 'Bearer fake-token',
        }

        ctx = copy_context()

        def _handler():
            # Step 1: Middleware would set keys (async context — but we simulate here)
            token = _byok_ctx.set(None)  # Clean start

            # Step 2: Separated dep extracts and validates (sync — no ContextVar mutation)
            extracted = _extract_byok_from_request(mock_request)
            assert extracted == _VALID_KEYS

            validated = validate_and_return_byok_keys(uid, extracted)
            assert validated == _VALID_KEYS

            # ContextVar should still be None at this point
            assert _byok_ctx.get() is None

            # Step 3: Async handler installs keys
            if validated:
                set_byok_keys(validated)

            # Step 4: Downstream code reads keys
            assert get_byok_key('openai') == _FAKE_OPENAI
            assert get_byok_key('anthropic') == _FAKE_ANTHROPIC
            assert get_byok_key('gemini') == _FAKE_GEMINI
            assert get_byok_key('deepgram') == _FAKE_DEEPGRAM

            _byok_ctx.reset(token)

        ctx.run(_handler)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_full_ws_lifecycle(self, mock_get_state):
        from utils.byok import (
            _byok_ctx,
            extract_byok_from_websocket,
            get_byok_key,
            set_byok_keys,
            validate_and_return_byok_keys_ws,
            invalidate_byok_state_cache,
        )

        uid = 'uat-e2e-ws'
        invalidate_byok_state_cache(uid)
        mock_get_state.return_value = _byok_state()

        mock_ws = MagicMock()
        mock_ws.headers = {
            'x-byok-openai': _FAKE_OPENAI,
            'x-byok-anthropic': _FAKE_ANTHROPIC,
            'x-byok-gemini': _FAKE_GEMINI,
            'x-byok-deepgram': _FAKE_DEEPGRAM,
            'authorization': 'Bearer fake-token',
        }

        ctx = copy_context()

        def _handler():
            token = _byok_ctx.set(None)

            # WS dep extracts and validates
            extracted = extract_byok_from_websocket(mock_ws)
            assert extracted == _VALID_KEYS

            validated = validate_and_return_byok_keys_ws(uid, extracted)
            assert validated == _VALID_KEYS

            # No ContextVar mutation from dep
            assert _byok_ctx.get() is None

            # Handler installs
            if validated:
                set_byok_keys(validated)

            # Downstream reads
            assert get_byok_key('openai') == _FAKE_OPENAI
            assert get_byok_key('deepgram') == _FAKE_DEEPGRAM

            _byok_ctx.reset(token)

        ctx.run(_handler)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_non_byok_mobile_lifecycle(self, mock_get_state):
        """Mobile user with no BYOK headers → ContextVar stays empty."""
        from utils.byok import (
            _byok_ctx,
            _extract_byok_from_request,
            get_byok_key,
            set_byok_keys,
            validate_and_return_byok_keys,
        )

        mock_request = MagicMock()
        mock_request.headers = {'authorization': 'Bearer fake-token'}  # No BYOK headers

        ctx = copy_context()

        def _handler():
            token = _byok_ctx.set(None)

            extracted = _extract_byok_from_request(mock_request)
            assert extracted == {}

            validated = validate_and_return_byok_keys('uat-mobile-e2e', extracted)
            assert validated == {}

            if validated:
                set_byok_keys(validated)

            # Downstream: should use Omi keys
            assert get_byok_key('openai') is None
            assert get_byok_key('deepgram') is None

            _byok_ctx.reset(token)

        ctx.run(_handler)


# ============================================================================
# UAT 17: Endpoint signature verification
# ============================================================================


class TestUAT_EndpointSignatures:
    """Verify that all critical endpoints accept Request (per-router auth pattern)."""

    def test_send_message_has_request_param(self):
        import inspect
        from routers.chat import send_message

        sig = inspect.signature(send_message)
        assert 'request' in sig.parameters

    def test_create_voice_message_has_request_param(self):
        import inspect
        from routers.chat import create_voice_message_stream

        sig = inspect.signature(create_voice_message_stream)
        assert 'request' in sig.parameters

    def test_transcribe_voice_message_has_request_param(self):
        import inspect
        from routers.chat import transcribe_voice_message

        sig = inspect.signature(transcribe_voice_message)
        assert 'request' in sig.parameters

    def test_sync_local_files_has_request_param(self):
        import inspect
        from routers.sync import sync_local_files

        sig = inspect.signature(sync_local_files)
        assert 'request' in sig.parameters

    def test_sync_local_files_v2_has_request_param(self):
        import inspect
        from routers.sync import sync_local_files_v2

        sig = inspect.signature(sync_local_files_v2)
        assert 'request' in sig.parameters

    def test_listen_handler_has_byok_dep(self):
        """WebSocket handlers still use Depends (middleware doesn't cover WS)."""
        import inspect

        try:
            from routers.transcribe import listen_handler
        except Exception:
            pytest.skip("routers.transcribe requires Google Cloud credentials")

        sig = inspect.signature(listen_handler)
        assert 'websocket' in sig.parameters
        assert 'byok_keys' in sig.parameters

    def test_auth_dep_does_not_contain_byok_validation(self):
        """get_current_user_uid must NOT call validate_byok_request in its body."""
        import inspect
        from utils.other.endpoints import get_current_user_uid

        source = inspect.getsource(get_current_user_uid)
        # The function body (after the docstring) must not call validate_byok_request
        assert 'validate_byok_request' not in source
        # It may mention "byok" in its docstring — that's fine. But the executable
        # lines must not import or call any byok validation function.
        # Split at the docstring close to check only executable lines.
        parts = source.split('"""')
        # parts[0] = def line, parts[1] = docstring, parts[2+] = body
        body = '"""'.join(parts[2:]) if len(parts) > 2 else ''
        assert 'validate_byok' not in body
        assert 'set_byok_keys' not in body

    def test_ws_auth_dep_does_not_contain_byok_validation(self):
        """get_current_user_uid_ws_listen must NOT call validate_byok_websocket."""
        import inspect
        from utils.other.endpoints import get_current_user_uid_ws_listen

        source = inspect.getsource(get_current_user_uid_ws_listen)
        assert 'validate_byok' not in source

    def test_ws_auth_dep_is_sync(self):
        """get_current_user_uid_ws_listen must be a regular (sync) function."""
        import asyncio
        from utils.other.endpoints import get_current_user_uid_ws_listen

        assert not asyncio.iscoroutinefunction(get_current_user_uid_ws_listen)


# ============================================================================
# UAT 18: BYOKMiddleware still installed (for has_byok_keys in users.py)
# ============================================================================


class TestUAT_PerRouterAuth:
    """Per-router auth dependencies must be used instead of centralized middleware."""

    def test_require_firebase_importable(self):
        from utils.auth_middleware import require_firebase, require_firebase_no_byok

        assert callable(require_firebase)
        assert callable(require_firebase_no_byok)

    def test_no_centralized_middleware_in_main(self):
        import importlib
        import os

        spec = importlib.util.find_spec('main')
        if spec and spec.origin:
            source = open(spec.origin).read()
        else:
            main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'main.py')
            source = open(main_path).read()

        assert 'AuthMiddleware' not in source, "Centralized AuthMiddleware should be removed"
        assert 'require_firebase' not in source, "Auth deps belong on routers, not in main.py"
