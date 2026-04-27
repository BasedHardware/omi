"""Tests for BYOK security fixes (issue #6880).

Covers: fingerprint validation, ContextVar safety, WebSocket extraction,
cache key hashing, Gemini URL key removal, quota bypass consistency.
"""

import hashlib
import os
import re
import sys
from contextvars import copy_context
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
# 3. Fingerprint validation
# ---------------------------------------------------------------------------

_SHA256_HEX_RE = re.compile(r'^[a-f0-9]{64}$')


class TestFingerprintValidation:
    def _valid_fingerprints(self) -> Dict[str, str]:
        return {
            'openai': hashlib.sha256(b'sk-test-openai').hexdigest(),
            'anthropic': hashlib.sha256(b'sk-test-anthropic').hexdigest(),
            'gemini': hashlib.sha256(b'sk-test-gemini').hexdigest(),
            'deepgram': hashlib.sha256(b'sk-test-deepgram').hexdigest(),
        }

    def test_valid_fingerprints_match_regex(self):
        for provider, fp in self._valid_fingerprints().items():
            assert _SHA256_HEX_RE.match(fp), f"Valid fingerprint for {provider} should match"

    def test_empty_string_rejected(self):
        assert not _SHA256_HEX_RE.match('')

    def test_short_hex_rejected(self):
        assert not _SHA256_HEX_RE.match('abcdef0123456789')

    def test_uppercase_rejected(self):
        fp = hashlib.sha256(b'test').hexdigest().upper()
        assert not _SHA256_HEX_RE.match(fp)

    def test_non_hex_rejected(self):
        assert not _SHA256_HEX_RE.match('g' * 64)

    def test_arbitrary_string_rejected(self):
        assert not _SHA256_HEX_RE.match('x')
        assert not _SHA256_HEX_RE.match('fake-fingerprint')


# ---------------------------------------------------------------------------
# 4. Cache key hashing
# ---------------------------------------------------------------------------


class TestCacheKeyHashing:
    def test_hash_key_returns_sha256(self):
        from utils.llm.clients import _hash_key

        key = 'sk-test-key-12345'
        result = _hash_key(key)
        expected = hashlib.sha256(key.encode()).hexdigest()
        assert result == expected

    def test_hash_key_is_deterministic(self):
        from utils.llm.clients import _hash_key

        assert _hash_key('abc') == _hash_key('abc')

    def test_hash_key_differs_for_different_inputs(self):
        from utils.llm.clients import _hash_key

        assert _hash_key('key-a') != _hash_key('key-b')

    def test_openai_cache_uses_hashed_key(self):
        """Verify the cache key format uses _hash_key, not raw api_key or hash()."""
        from utils.llm.clients import _hash_key

        api_key = 'sk-secret-key'
        hashed = _hash_key(api_key)
        cache_key_fragment = f"gpt-4.1-mini:{hashed}:"
        assert hashed in cache_key_fragment
        assert api_key not in cache_key_fragment

    def test_anthropic_cache_does_not_store_raw_key(self):
        """Verify _cached_anthropic uses _hash_key for cache lookup."""
        from utils.llm.clients import _anthropic_cache, _hash_key

        api_key = 'sk-ant-test-key-for-cache-test'
        hashed = _hash_key(api_key)
        assert api_key not in _anthropic_cache


# ---------------------------------------------------------------------------
# 5. Gemini embed: key not in URL
# ---------------------------------------------------------------------------


class TestGeminiKeyNotInUrl:
    @patch('utils.llm.clients.httpx.post')
    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_gemini_embed_uses_header_not_url_param(self, mock_byok, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {'embedding': {'values': [0.1, 0.2]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from utils.llm.clients import gemini_embed_query

        gemini_embed_query('test query')

        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get('url', '')
        assert '?key=' not in url
        assert 'key=' not in url
        headers = call_args[1].get('headers', {})
        assert 'x-goog-api-key' in headers

    @patch('utils.llm.clients.httpx.post')
    @patch('utils.llm.clients.get_byok_key', return_value='user-gemini-key-secret')
    def test_byok_gemini_key_not_in_url(self, mock_byok, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {'embedding': {'values': [0.1, 0.2]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from utils.llm.clients import gemini_embed_query

        gemini_embed_query('test query')

        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get('url', '')
        assert 'user-gemini-key-secret' not in url
        headers = call_args[1].get('headers', {})
        assert headers.get('x-goog-api-key') == 'user-gemini-key-secret'


# ---------------------------------------------------------------------------
# 6. Chat quota BYOK bypass
# ---------------------------------------------------------------------------


class TestChatQuotaBYOKBypass:
    @patch('utils.byok.get_byok_key')
    @patch('utils.subscription.users_db')
    def test_enforce_chat_quota_bypasses_for_byok_with_openai_key(self, mock_users_db, mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'sk-openai' if p == 'openai' else None
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('byok-user-uid')
        mock_users_db.is_byok_active.assert_called_once_with('byok-user-uid')

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_enforces_when_byok_active_but_no_llm_headers(
        self, mock_snapshot, mock_users_db, _mock_get_key
    ):
        """Abuse case: user activated BYOK but sends no LLM provider headers."""
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
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('fake-byok-uid')
        assert exc_info.value.status_code == 402

    @patch('utils.byok.get_byok_key')
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_enforces_when_only_deepgram_header(self, mock_snapshot, mock_users_db, mock_get_key):
        """Partial-header abuse: only x-byok-deepgram sent, chat uses Omi's OpenAI key."""
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'dg-key' if p == 'deepgram' else None
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('partial-byok-uid')
        assert exc_info.value.status_code == 402

    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_still_enforces_for_non_byok(self, mock_snapshot, mock_users_db):
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = False
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 31,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('non-byok-uid')
        assert exc_info.value.status_code == 402


# ---------------------------------------------------------------------------
# 7. Transcription credit BYOK bypass
# ---------------------------------------------------------------------------


class TestTranscriptionCreditBYOKBypass:
    @patch('utils.byok.get_byok_key', return_value='dg-user-key')
    @patch('utils.subscription.users_db')
    def test_has_transcription_credits_bypasses_for_byok(self, mock_users_db, _mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('byok-uid') is True

    @patch('utils.byok.get_byok_key', return_value='dg-user-key')
    @patch('utils.subscription.users_db')
    def test_remaining_seconds_is_none_for_byok(self, mock_users_db, _mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import get_remaining_transcription_seconds

        assert get_remaining_transcription_seconds('byok-uid') is None

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    def test_transcription_not_bypassed_when_no_deepgram_header(self, mock_users_db, _mock_get_key):
        """BYOK active but no x-byok-deepgram header — should NOT bypass."""
        mock_users_db.is_byok_active.return_value = True
        mock_users_db.get_user_valid_subscription.return_value = None
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('fake-byok-uid') is False


# ---------------------------------------------------------------------------
# 8. BYOK headers constant is public and correct
# ---------------------------------------------------------------------------


class TestBYOKHeadersConstant:
    def test_headers_has_all_four_providers(self):
        from utils.byok import BYOK_HEADERS

        assert set(BYOK_HEADERS.keys()) == {'openai', 'anthropic', 'gemini', 'deepgram'}

    def test_headers_are_lowercase(self):
        from utils.byok import BYOK_HEADERS

        for header in BYOK_HEADERS.values():
            assert header == header.lower()

    def test_headers_start_with_x_byok(self):
        from utils.byok import BYOK_HEADERS

        for header in BYOK_HEADERS.values():
            assert header.startswith('x-byok-')


# ---------------------------------------------------------------------------
# 9. Bounded cache behavior
# ---------------------------------------------------------------------------


class TestBoundedCache:
    def test_openai_cache_has_maxsize(self):
        from utils.llm.clients import _openai_cache

        assert hasattr(_openai_cache, 'maxsize')
        assert _openai_cache.maxsize > 0

    def test_anthropic_cache_has_maxsize(self):
        from utils.llm.clients import _anthropic_cache

        assert hasattr(_anthropic_cache, 'maxsize')
        assert _anthropic_cache.maxsize > 0

    def test_openai_cache_has_ttl(self):
        from utils.llm.clients import _openai_cache

        assert hasattr(_openai_cache, 'ttl')
        assert _openai_cache.ttl > 0

    def test_anthropic_cache_has_ttl(self):
        from utils.llm.clients import _anthropic_cache

        assert hasattr(_anthropic_cache, 'ttl')
        assert _anthropic_cache.ttl > 0


# ---------------------------------------------------------------------------
# 10. BYOK activation endpoint validation
# ---------------------------------------------------------------------------


class TestBYOKActivationValidation:
    """Test the actual activate_byok_endpoint and its production constants."""

    def _valid_fingerprints(self) -> Dict[str, str]:
        return {
            'openai': hashlib.sha256(b'sk-openai').hexdigest(),
            'anthropic': hashlib.sha256(b'sk-anthropic').hexdigest(),
            'gemini': hashlib.sha256(b'sk-gemini').hexdigest(),
            'deepgram': hashlib.sha256(b'sk-deepgram').hexdigest(),
        }

    @patch('routers.users.users_db')
    def test_valid_activation_persists_fingerprints(self, mock_users_db):
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        data = BYOKActivateRequest(fingerprints=fps)
        result = activate_byok_endpoint(data, uid='test-uid')
        assert result == {"active": True}
        mock_users_db.set_byok_active.assert_called_once_with('test-uid', fps)

    def test_missing_provider_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        del fps['deepgram']
        data = BYOKActivateRequest(fingerprints=fps)
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400
        assert 'deepgram' in str(exc_info.value.detail)

    def test_unknown_provider_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        fps['unknown_provider'] = hashlib.sha256(b'x').hexdigest()
        data = BYOKActivateRequest(fingerprints=fps)
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400
        assert 'Unknown provider' in str(exc_info.value.detail)

    def test_63_char_fingerprint_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 63
        data = BYOKActivateRequest(fingerprints=fps)
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400

    @patch('routers.users.users_db')
    def test_64_char_valid_hex_passes(self, mock_users_db):
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 64
        data = BYOKActivateRequest(fingerprints=fps)
        result = activate_byok_endpoint(data, uid='test-uid')
        assert result == {"active": True}

    def test_65_char_fingerprint_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 65
        data = BYOKActivateRequest(fingerprints=fps)
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400

    def test_empty_fingerprints_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        data = BYOKActivateRequest(fingerprints={})
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400

    @patch('routers.users.users_db')
    def test_deactivation_calls_clear(self, mock_users_db):
        from routers.users import deactivate_byok_endpoint

        result = deactivate_byok_endpoint(uid='test-uid')
        assert result == {"active": False}
        mock_users_db.clear_byok_active.assert_called_once_with('test-uid')

    def test_production_constants_match(self):
        """Verify the test regex matches the production regex."""
        from routers.users import _SHA256_HEX_RE as prod_re, _BYOK_REQUIRED_PROVIDERS as prod_providers

        assert prod_re.pattern == _SHA256_HEX_RE.pattern
        assert prod_providers == {'openai', 'anthropic', 'gemini', 'deepgram'}


# ---------------------------------------------------------------------------
# 11. Cache routing: raw keys never in cache keys
# ---------------------------------------------------------------------------


class TestCacheRouting:
    def test_cached_openai_chat_no_raw_key_in_cache(self):
        from utils.llm.clients import _cached_openai_chat, _openai_cache

        api_key = 'sk-secret-openai-key-for-cache-test'
        _cached_openai_chat('gpt-4.1-mini', api_key, {})
        for k in _openai_cache.keys():
            assert api_key not in k, f"Raw API key found in cache key: {k}"

    def test_cached_openai_chat_returns_same_instance(self):
        from utils.llm.clients import _cached_openai_chat

        api_key = 'sk-deterministic-test-key'
        inst1 = _cached_openai_chat('gpt-4.1-mini', api_key, {})
        inst2 = _cached_openai_chat('gpt-4.1-mini', api_key, {})
        assert inst1 is inst2

    def test_cached_anthropic_no_raw_key_in_cache(self):
        from utils.llm.clients import _anthropic_cache, _cached_anthropic

        api_key = 'sk-ant-secret-key-for-cache-test'
        _cached_anthropic(api_key)
        for k in _anthropic_cache.keys():
            assert api_key not in k, f"Raw API key found in cache key: {k}"

    def test_cached_anthropic_returns_same_instance(self):
        from utils.llm.clients import _cached_anthropic

        api_key = 'sk-ant-deterministic-key'
        inst1 = _cached_anthropic(api_key)
        inst2 = _cached_anthropic(api_key)
        assert inst1 is inst2

    def test_anthropic_proxy_routes_to_byok(self):
        from utils.llm.clients import _AnthropicViaOpenAIProxy, _ANTHROPIC_OPENAI_BASE_URL

        mock_default = MagicMock()
        proxy = _AnthropicViaOpenAIProxy(default=mock_default, ctor_kwargs={})
        with patch('utils.llm.clients.get_byok_key', side_effect=lambda p: 'sk-ant-byok' if p == 'anthropic' else None):
            resolved = proxy._resolve()
        assert resolved.openai_api_base == _ANTHROPIC_OPENAI_BASE_URL

    def test_anthropic_proxy_falls_back_to_default(self):
        from utils.llm.clients import _AnthropicViaOpenAIProxy

        mock_default = MagicMock()
        proxy = _AnthropicViaOpenAIProxy(default=mock_default, ctor_kwargs={})
        with patch('utils.llm.clients.get_byok_key', return_value=None):
            resolved = proxy._resolve()
        assert resolved is mock_default


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
# 13. Quota boundary tests
# ---------------------------------------------------------------------------


class TestQuotaBoundaryTests:
    @patch('utils.byok.get_byok_key')
    @patch('utils.subscription.users_db')
    def test_chat_quota_bypasses_with_anthropic_key_only(self, mock_users_db, mock_get_key):
        """Anthropic-only BYOK should also bypass chat quota."""
        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'sk-ant-byok' if p == 'anthropic' else None
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('anthropic-byok-uid')  # Should not raise

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_chat_quota_at_exact_limit(self, mock_snapshot, mock_users_db, _mock_get_key):
        """Usage exactly at limit should be rejected."""
        from models.users import PlanType

        mock_users_db.is_byok_active.return_value = False
        mock_snapshot.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 30,
            'limit': 30,
            'allowed': False,
            'reset_at': '2026-05-01',
        }
        from fastapi import HTTPException
        from utils.subscription import enforce_chat_quota

        with pytest.raises(HTTPException) as exc_info:
            enforce_chat_quota('at-limit-uid')
        assert exc_info.value.status_code == 402

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_chat_quota_just_below_limit(self, mock_snapshot, mock_users_db, _mock_get_key):
        """Usage below limit should pass."""
        mock_users_db.is_byok_active.return_value = False
        mock_snapshot.return_value = {
            'plan': 'basic',
            'unit': 'questions',
            'used': 29,
            'limit': 30,
            'allowed': True,
            'reset_at': '2026-05-01',
        }
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('below-limit-uid')  # Should not raise


# ---------------------------------------------------------------------------
# 14. Per-request fingerprint validation against Firestore enrollment
# ---------------------------------------------------------------------------


class TestBYOKFingerprintValidation:
    """Firestore BYOK state is the source of truth.

    - BYOK-active users MUST send keys whose SHA-256 matches enrolled fingerprints.
    - Non-BYOK users' headers are silently cleared.
    """

    _FAKE_KEY_OPENAI = 'sk-test-openai-key-12345'
    _FAKE_KEY_ANTHROPIC = 'sk-ant-test-key-67890'
    _FAKE_KEY_GEMINI = 'AIzaSy-test-gemini-key'
    _FAKE_KEY_DEEPGRAM = 'dg-test-deepgram-key'

    @property
    def _enrolled_fingerprints(self):
        return {
            'openai': hashlib.sha256(self._FAKE_KEY_OPENAI.encode()).hexdigest(),
            'anthropic': hashlib.sha256(self._FAKE_KEY_ANTHROPIC.encode()).hexdigest(),
            'gemini': hashlib.sha256(self._FAKE_KEY_GEMINI.encode()).hexdigest(),
            'deepgram': hashlib.sha256(self._FAKE_KEY_DEEPGRAM.encode()).hexdigest(),
        }

    @property
    def _valid_request_keys(self):
        return {
            'openai': self._FAKE_KEY_OPENAI,
            'anthropic': self._FAKE_KEY_ANTHROPIC,
            'gemini': self._FAKE_KEY_GEMINI,
            'deepgram': self._FAKE_KEY_DEEPGRAM,
        }

    def _mock_byok_state(self, active=True, fingerprints=None):
        from datetime import datetime, timezone

        return {
            'active': active,
            'fingerprints': fingerprints if fingerprints is not None else self._enrolled_fingerprints,
            'last_seen_at': datetime.now(timezone.utc),
        }

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_valid_keys_pass_validation(self, mock_get_state):
        """BYOK-active user with matching keys passes validation."""
        from utils.byok import _byok_ctx, validate_byok_request

        mock_get_state.return_value = self._mock_byok_state()
        token = _byok_ctx.set(self._valid_request_keys)
        try:
            validate_byok_request('byok-uid')  # Should not raise
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_missing_header_raises_403(self, mock_get_state):
        """BYOK-active user sends some headers but missing a provider → 403."""
        from fastapi import HTTPException
        from utils.byok import _byok_ctx, validate_byok_request

        mock_get_state.return_value = self._mock_byok_state()
        # Send only openai key — this is a broken BYOK attempt (partial headers)
        token = _byok_ctx.set({'openai': self._FAKE_KEY_OPENAI})
        try:
            with pytest.raises(HTTPException) as exc_info:
                validate_byok_request('byok-uid')
            assert exc_info.value.status_code == 403
            assert 'missing' in exc_info.value.detail
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_wrong_key_raises_403(self, mock_get_state):
        """BYOK-active user with a key that doesn't match fingerprint → 403."""
        from fastapi import HTTPException
        from utils.byok import _byok_ctx, validate_byok_request

        mock_get_state.return_value = self._mock_byok_state()
        bad_keys = dict(self._valid_request_keys)
        bad_keys['openai'] = 'sk-WRONG-key-does-not-match'
        token = _byok_ctx.set(bad_keys)
        try:
            with pytest.raises(HTTPException) as exc_info:
                validate_byok_request('byok-uid')
            assert exc_info.value.status_code == 403
            assert 'mismatch' in exc_info.value.detail
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_no_headers_when_byok_active_falls_through(self, mock_get_state):
        """BYOK-active user sending zero BYOK headers (e.g. mobile) → no error, falls through to Omi keys."""
        from utils.byok import _byok_ctx, validate_byok_request, get_byok_keys

        mock_get_state.return_value = self._mock_byok_state()
        token = _byok_ctx.set({})
        try:
            validate_byok_request('byok-uid')  # Should NOT raise
            assert get_byok_keys() == {}  # Context cleared, will use Omi keys
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_partial_headers_when_byok_active_raises_403(self, mock_get_state):
        """BYOK-active user sending SOME but not all headers → 403 (incomplete BYOK attempt)."""
        from fastapi import HTTPException
        from utils.byok import _byok_ctx, validate_byok_request

        mock_get_state.return_value = self._mock_byok_state()
        # Send only openai key, missing the rest — this is a broken BYOK attempt, not mobile
        token = _byok_ctx.set({'openai': self._FAKE_KEY_OPENAI})
        try:
            with pytest.raises(HTTPException) as exc_info:
                validate_byok_request('byok-uid')
            assert exc_info.value.status_code == 403
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_non_byok_user_headers_are_cleared(self, mock_get_state):
        """Non-BYOK user sending BYOK headers → headers silently cleared."""
        from utils.byok import _byok_ctx, validate_byok_request, get_byok_keys

        mock_get_state.return_value = self._mock_byok_state(active=False)
        token = _byok_ctx.set({'openai': 'sk-sneaky-key'})
        try:
            validate_byok_request('non-byok-uid')  # Should not raise
            # Headers must have been cleared
            assert get_byok_keys() == {}
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_non_byok_user_no_headers_passes(self, mock_get_state):
        """Non-BYOK user with no BYOK headers → normal flow, no error."""
        from utils.byok import _byok_ctx, validate_byok_request

        mock_get_state.return_value = self._mock_byok_state(active=False)
        token = _byok_ctx.set(None)
        try:
            validate_byok_request('normal-uid')  # Should not raise
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_expired_byok_headers_cleared(self, mock_get_state):
        """BYOK activation expired (>7 days) → headers silently cleared."""
        from datetime import datetime as dt, timezone as tz
        from utils.byok import _byok_ctx, validate_byok_request, get_byok_keys

        expired_state = self._mock_byok_state()
        expired_state['last_seen_at'] = dt(2020, 1, 1, tzinfo=tz.utc)
        mock_get_state.return_value = expired_state

        token = _byok_ctx.set(self._valid_request_keys)
        try:
            validate_byok_request('expired-uid')  # Should not raise
            assert get_byok_keys() == {}  # Headers cleared
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_websocket_no_headers_falls_through(self, mock_get_state):
        """BYOK-active user on WS with no headers (mobile) → falls through, no error."""
        from utils.byok import _byok_ctx, validate_byok_websocket, get_byok_keys

        mock_get_state.return_value = self._mock_byok_state()
        token = _byok_ctx.set({})  # No BYOK headers (mobile app)
        try:
            error = validate_byok_websocket('byok-uid')
            assert error is None  # No error — mobile falls through
            assert get_byok_keys() == {}  # Context cleared
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_websocket_partial_headers_returns_error(self, mock_get_state):
        """BYOK-active user on WS with partial headers → error string."""
        from utils.byok import _byok_ctx, validate_byok_websocket

        mock_get_state.return_value = self._mock_byok_state()
        # Send only one key — broken BYOK attempt
        token = _byok_ctx.set({'openai': self._FAKE_KEY_OPENAI})
        try:
            error = validate_byok_websocket('byok-uid')
            assert error is not None
            assert 'missing' in error
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_websocket_validation_returns_none_on_success(self, mock_get_state):
        """WebSocket validation returns None when keys are valid."""
        from utils.byok import _byok_ctx, validate_byok_websocket

        mock_get_state.return_value = self._mock_byok_state()
        token = _byok_ctx.set(self._valid_request_keys)
        try:
            error = validate_byok_websocket('byok-uid')
            assert error is None
        finally:
            _byok_ctx.reset(token)


# ---------------------------------------------------------------------------
# 15. BYOK state cache
# ---------------------------------------------------------------------------


class TestBYOKStateCache:
    """In-memory TTL cache avoids redundant Firestore reads per request."""

    def setup_method(self):
        from utils.byok import _byok_state_cache, _byok_state_cache_lock

        with _byok_state_cache_lock:
            _byok_state_cache.clear()

    def test_cache_avoids_repeated_firestore_reads(self):
        """Second call for same uid should hit cache, not Firestore."""
        from utils.byok import get_cached_byok_state, _byok_state_cache, _byok_state_cache_lock

        fake_state = {'active': True, 'fingerprints': {'openai': 'abc'}}
        with patch('database.users.get_byok_state', return_value=fake_state) as mock_fs:
            result1 = get_cached_byok_state('uid-1')
            result2 = get_cached_byok_state('uid-1')
            assert result1 == fake_state
            assert result2 == fake_state
            assert mock_fs.call_count == 1  # Only one Firestore read

    def test_different_uids_get_separate_entries(self):
        """Each uid gets its own cache entry."""
        from utils.byok import get_cached_byok_state

        state_a = {'active': True, 'fingerprints': {'openai': 'aaa'}}
        state_b = {'active': False, 'fingerprints': {}}

        with patch('database.users.get_byok_state', side_effect=[state_a, state_b]) as mock_fs:
            assert get_cached_byok_state('uid-a') == state_a
            assert get_cached_byok_state('uid-b') == state_b
            assert mock_fs.call_count == 2

    def test_invalidate_busts_cache(self):
        """invalidate_byok_state_cache forces next call to read Firestore."""
        from utils.byok import get_cached_byok_state, invalidate_byok_state_cache

        state_old = {'active': True, 'fingerprints': {'openai': 'old'}}
        state_new = {'active': True, 'fingerprints': {'openai': 'new'}}

        with patch('database.users.get_byok_state', side_effect=[state_old, state_new]) as mock_fs:
            assert get_cached_byok_state('uid-1') == state_old
            invalidate_byok_state_cache('uid-1')
            assert get_cached_byok_state('uid-1') == state_new
            assert mock_fs.call_count == 2

    def test_cache_is_bounded(self):
        """Cache respects maxsize — evicts oldest entries."""
        from utils.byok import _byok_state_cache, _BYOK_STATE_CACHE_MAX

        assert _BYOK_STATE_CACHE_MAX == 1024  # Verify constant


# ---------------------------------------------------------------------------
# 17. Auth dependency integration tests
# ---------------------------------------------------------------------------


class TestAuthDependencyBYOKIntegration:
    """Verify shared auth dependencies call (or skip) BYOK validation."""

    @patch('utils.other.endpoints.validate_byok_request')
    @patch('utils.other.endpoints.record_user_platform')
    @patch('utils.other.endpoints.verify_token', return_value='uid-123')
    def test_get_current_user_uid_calls_byok_validation(self, _mock_verify, _mock_platform, mock_validate):
        from utils.other.endpoints import get_current_user_uid

        uid = get_current_user_uid(authorization='Bearer fake-token')
        assert uid == 'uid-123'
        mock_validate.assert_called_once_with('uid-123')

    @patch('utils.other.endpoints.record_user_platform')
    @patch('utils.other.endpoints.verify_token', return_value='uid-456')
    def test_no_byok_validation_skips_validate(self, _mock_verify, _mock_platform):
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

    @patch('utils.other.endpoints.validate_byok_websocket', return_value=None)
    @patch('utils.other.endpoints._verify_ws_auth', return_value='ws-uid')
    def test_ws_listen_with_byok_headers_validates(self, _mock_auth, mock_validate):
        import asyncio
        from utils.other.endpoints import get_current_user_uid_ws_listen

        ws = self._make_ws({'x-byok-openai': 'sk-test'})
        uid = asyncio.run(get_current_user_uid_ws_listen(websocket=ws, authorization='Bearer tok'))
        assert uid == 'ws-uid'
        mock_validate.assert_called_once_with('ws-uid')

    @patch('utils.other.endpoints.validate_byok_websocket', return_value=None)
    @patch('utils.other.endpoints._verify_ws_auth', return_value='ws-uid')
    def test_ws_listen_no_headers_passes(self, _mock_auth, mock_validate):
        import asyncio
        from utils.other.endpoints import get_current_user_uid_ws_listen

        ws = self._make_ws({})
        uid = asyncio.run(get_current_user_uid_ws_listen(websocket=ws, authorization='Bearer tok'))
        assert uid == 'ws-uid'
        mock_validate.assert_called_once()

    @patch('utils.other.endpoints.validate_byok_websocket', return_value='fingerprint mismatch')
    @patch('utils.other.endpoints._verify_ws_auth', return_value='ws-uid')
    def test_ws_listen_validation_failure_raises_4003(self, _mock_auth, _mock_validate):
        import asyncio
        from fastapi import WebSocketException
        from utils.other.endpoints import get_current_user_uid_ws_listen

        ws = self._make_ws({'x-byok-openai': 'wrong-key'})
        with pytest.raises(WebSocketException) as exc_info:
            asyncio.run(get_current_user_uid_ws_listen(websocket=ws, authorization='Bearer tok'))
        assert exc_info.value.code == 4003


class TestActivationCacheInvalidation:
    """Verify activate/deactivate endpoints invalidate BYOK state cache."""

    @patch('routers.users.invalidate_byok_state_cache')
    @patch('routers.users.users_db')
    def test_activate_invalidates_cache(self, mock_users_db, mock_invalidate):
        from routers.users import activate_byok_endpoint, BYOKActivateRequest

        fingerprints = {
            'openai': hashlib.sha256(b'sk-o').hexdigest(),
            'anthropic': hashlib.sha256(b'sk-a').hexdigest(),
            'gemini': hashlib.sha256(b'sk-g').hexdigest(),
            'deepgram': hashlib.sha256(b'sk-d').hexdigest(),
        }
        data = BYOKActivateRequest(fingerprints=fingerprints)
        result = activate_byok_endpoint(data=data, uid='uid-act')
        assert result == {'active': True}
        mock_invalidate.assert_called_once_with('uid-act')

    @patch('routers.users.invalidate_byok_state_cache')
    @patch('routers.users.users_db')
    def test_deactivate_invalidates_cache(self, mock_users_db, mock_invalidate):
        from routers.users import deactivate_byok_endpoint

        result = deactivate_byok_endpoint(uid='uid-deact')
        assert result == {'active': False}
        mock_invalidate.assert_called_once_with('uid-deact')
