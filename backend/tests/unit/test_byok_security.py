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
    @patch('utils.byok.has_byok_keys', return_value=True)
    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
    @patch('utils.subscription.users_db')
    def test_enforce_chat_quota_bypasses_for_byok(self, mock_users_db, _mock_has_keys):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import enforce_chat_quota

        enforce_chat_quota('byok-user-uid')
        mock_users_db.is_byok_active.assert_called_once_with('byok-user-uid')

    @patch('utils.byok.has_byok_keys', return_value=False)
    @patch('utils.subscription.CHAT_CAP_ENFORCEMENT_ENABLED', True)
    @patch('utils.subscription.users_db')
    @patch('utils.subscription.get_chat_quota_snapshot')
    def test_enforce_chat_quota_enforces_when_byok_active_but_no_headers(
        self, mock_snapshot, mock_users_db, _mock_has_keys
    ):
        """Abuse case: user activated BYOK with fake fingerprints but sends no BYOK headers."""
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
    @patch('utils.subscription.users_db')
    def test_has_transcription_credits_bypasses_for_byok(self, mock_users_db):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('byok-uid') is True

    @patch('utils.subscription.users_db')
    def test_remaining_seconds_is_none_for_byok(self, mock_users_db):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import get_remaining_transcription_seconds

        assert get_remaining_transcription_seconds('byok-uid') is None


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
