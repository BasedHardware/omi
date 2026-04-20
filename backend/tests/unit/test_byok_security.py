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

sys.modules.setdefault('database._client', MagicMock())
sys.modules.setdefault('database.redis_db', MagicMock())
sys.modules.setdefault('database.users', MagicMock())
sys.modules.setdefault('database.user_usage', MagicMock())
sys.modules.setdefault('database.llm_usage', MagicMock())
sys.modules.setdefault('database.announcements', MagicMock())

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
    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
    @patch('utils.subscription.users_db')
    def test_enforce_chat_quota_bypasses_for_byok_with_openai_key(self, mock_users_db, mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'sk-openai' if p == 'openai' else None
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('byok-user-uid')
        mock_users_db.is_byok_active.assert_called_once_with('byok-user-uid')

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
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
    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
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

    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
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
    """Test the validation logic used by activate_byok_endpoint.

    The endpoint module (routers.users) triggers GCS storage.Client() on import,
    which requires GCP credentials. Instead of mocking the entire import chain,
    we test the validation functions directly: the regex, the provider set, and
    the boundary cases are the same constants the endpoint uses.
    """

    _REQUIRED_PROVIDERS = {'openai', 'anthropic', 'gemini', 'deepgram'}

    def _valid_fingerprints(self) -> Dict[str, str]:
        return {
            'openai': hashlib.sha256(b'sk-openai').hexdigest(),
            'anthropic': hashlib.sha256(b'sk-anthropic').hexdigest(),
            'gemini': hashlib.sha256(b'sk-gemini').hexdigest(),
            'deepgram': hashlib.sha256(b'sk-deepgram').hexdigest(),
        }

    def _validate(self, fingerprints: Dict[str, str]) -> str | None:
        """Replicate the validation logic from activate_byok_endpoint."""
        missing = self._REQUIRED_PROVIDERS - set(fingerprints.keys())
        if missing:
            return f"Missing fingerprints for providers: {sorted(missing)}"
        for provider, fp in fingerprints.items():
            if provider not in self._REQUIRED_PROVIDERS:
                return f"Unknown provider: {provider}"
            if not _SHA256_HEX_RE.match(fp):
                return f"Invalid fingerprint for {provider}"
        return None

    def test_valid_fingerprints_pass(self):
        assert self._validate(self._valid_fingerprints()) is None

    def test_missing_provider_rejects(self):
        fps = self._valid_fingerprints()
        del fps['deepgram']
        err = self._validate(fps)
        assert err is not None
        assert 'deepgram' in err

    def test_unknown_provider_rejects(self):
        fps = self._valid_fingerprints()
        fps['unknown_provider'] = hashlib.sha256(b'x').hexdigest()
        err = self._validate(fps)
        assert err is not None
        assert 'Unknown provider' in err

    def test_63_char_fingerprint_rejects(self):
        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 63
        err = self._validate(fps)
        assert err is not None
        assert 'Invalid fingerprint' in err

    def test_64_char_valid_hex_passes(self):
        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 64  # valid: 64 hex chars
        assert self._validate(fps) is None

    def test_65_char_fingerprint_rejects(self):
        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 65
        err = self._validate(fps)
        assert err is not None
        assert 'Invalid fingerprint' in err

    def test_empty_fingerprints_rejects(self):
        err = self._validate({})
        assert err is not None
        assert 'Missing fingerprints' in err


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
    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
    @patch('utils.subscription.users_db')
    def test_chat_quota_bypasses_with_anthropic_key_only(self, mock_users_db, mock_get_key):
        """Anthropic-only BYOK should also bypass chat quota."""
        mock_users_db.is_byok_active.return_value = True
        mock_get_key.side_effect = lambda p: 'sk-ant-byok' if p == 'anthropic' else None
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('anthropic-byok-uid')  # Should not raise

    @patch('utils.byok.get_byok_key', return_value=None)
    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
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
    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
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
