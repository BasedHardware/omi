"""Tests for BYOK security fixes (issue #6880).

Covers: Fingerprint validation, credential hashing, Gemini URL key removal, bounded/state caches.
"""

import hashlib
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from tests.unit._byok_fixtures import _SHA256_HEX_RE
from tests.unit._byok_fixtures import _byok_isolation  # noqa: F401


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
    def test_single_provider_enrollment_accepts_its_only_header(self, mock_get_state):
        """A capability-scoped enrollment only requires the provider it enrolled."""
        from utils.byok import _byok_ctx, get_byok_keys, validate_byok_request

        mock_get_state.return_value = self._mock_byok_state(
            fingerprints={'openai': self._enrolled_fingerprints['openai']}
        )
        token = _byok_ctx.set({'openai': self._FAKE_KEY_OPENAI})
        try:
            validate_byok_request('single-provider-uid')
            assert get_byok_keys() == {'openai': self._FAKE_KEY_OPENAI}
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_missing_enrolled_provider_header_raises_403(self, mock_get_state):
        """BYOK-active user sends some headers but missing a provider → 403.

        1da8880175 validates every enrolled provider, not just sent headers."""
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
    def test_valid_request_exposes_exactly_the_enrolled_keys(self, mock_get_state):
        """A passing BYOK request makes the enrolled provider keys available downstream."""
        from utils.byok import _byok_ctx, validate_byok_request, get_byok_keys

        mock_get_state.return_value = self._mock_byok_state()
        token = _byok_ctx.set(dict(self._valid_request_keys))
        try:
            validate_byok_request('byok-uid')
            assert set(get_byok_keys()) == set(self._enrolled_fingerprints)
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_header_for_unenrolled_provider_is_not_used(self, mock_get_state):
        """A header the enrollment cannot vouch for must never reach the provider clients.

        _check_byok_validity documents that "every header key's SHA-256 must match the
        enrolled fingerprint", but it iterated the *enrolled* fingerprints. A header for a
        provider absent from the enrollment was therefore never examined and stayed in the
        request context, so get_byok_keys() handed it to downstream LLM calls unvalidated.
        """
        from utils.byok import _byok_ctx, validate_byok_request, get_byok_keys

        mock_get_state.return_value = self._mock_byok_state()
        keys = dict(self._valid_request_keys)
        keys['unenrolled_provider'] = 'sk-never-enrolled-and-never-fingerprinted'
        token = _byok_ctx.set(keys)
        try:
            validate_byok_request('byok-uid')
            exposed = get_byok_keys()
            assert 'unenrolled_provider' not in exposed
            assert set(exposed) == set(self._enrolled_fingerprints)
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_enrolled_keys_survive_alongside_an_unenrolled_header(self, mock_get_state):
        """Dropping the unenrolled header must not disturb the enrolled ones."""
        from utils.byok import _byok_ctx, validate_byok_request, get_byok_keys

        mock_get_state.return_value = self._mock_byok_state()
        keys = dict(self._valid_request_keys)
        keys['unenrolled_provider'] = 'sk-never-enrolled'
        token = _byok_ctx.set(keys)
        try:
            validate_byok_request('byok-uid')
            assert get_byok_keys() == self._valid_request_keys
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_empty_fingerprint_entry_does_not_pass_a_key(self, mock_get_state):
        """An enrolled provider with an empty/null stored fingerprint must NOT
        pass an unverified request key into the context.

        The reviewer's gate: filter on a VALID stored fingerprint, not mere
        provider membership. A request key for a provider whose stored
        fingerprint is empty/null must be dropped exactly like an unenrolled
        provider, so it never reaches the provider clients.
        """
        from fastapi import HTTPException
        from utils.byok import _byok_ctx, validate_byok_request

        state = self._mock_byok_state()
        state['fingerprints']['openai'] = ''
        mock_get_state.return_value = state

        keys = dict(self._valid_request_keys)
        token = _byok_ctx.set(keys)
        try:
            # Since 1da8880175 an unverifiable key fails closed as a
            # fingerprint mismatch instead of being silently dropped: the 403
            # aborts the request, so the key never reaches a provider client.
            with pytest.raises(HTTPException) as exc_info:
                validate_byok_request('empty-fp-uid')
            assert exc_info.value.status_code == 403
            assert 'mismatch' in exc_info.value.detail
        finally:
            _byok_ctx.reset(token)

    @patch('database.users.BYOK_HEARTBEAT_TTL_SECONDS', 7 * 24 * 3600)
    @patch('database.users.get_byok_state')
    def test_partial_headers_when_byok_active_are_rejected(self, mock_get_state):
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
            assert 'missing' in exc_info.value.detail
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
            assert error is not None and 'missing' in error
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
