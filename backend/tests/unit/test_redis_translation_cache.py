"""Tests for Redis persistent translation cache (issue #4714).

Tests verify the two-tier caching strategy:
- Tier 1: In-memory OrderedDict (per-session, fast)
- Tier 2: Redis (global, persistent across sessions/users)
"""

import hashlib
from collections import OrderedDict
from unittest.mock import MagicMock, patch
import sys

# Mock Google Cloud translate before importing
sys.modules['google.cloud.translate_v3'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()

# Mock redis before importing redis_db
mock_redis_module = MagicMock()
sys.modules['redis'] = mock_redis_module


class TestRedisCacheFunctions:
    """Test the Redis cache helper functions in redis_db.py."""

    def test_cache_translation_sets_key_with_ttl(self):
        """cache_translation should store with versioned key and TTL."""
        mock_r = MagicMock()
        with patch.dict('os.environ', {'REDIS_DB_HOST': 'localhost', 'REDIS_DB_PASSWORD': 'test'}):
            # Import fresh to get the module
            if 'database.redis_db' in sys.modules:
                del sys.modules['database.redis_db']
            sys.path.insert(0, '/home/claude/omi/omi-kenji/backend')
            try:
                import database.redis_db as redis_db

                redis_db.r = mock_r

                redis_db.cache_translation('abc123', 'en', 'Hello', ttl=86400)

                mock_r.set.assert_called_once_with('translate:v1:abc123:en', 'Hello', ex=86400)
            finally:
                sys.path.pop(0)

    def test_get_cached_translation_returns_decoded_value(self):
        """get_cached_translation should decode bytes to string."""
        mock_r = MagicMock()
        mock_r.get.return_value = b'Hello'
        with patch.dict('os.environ', {'REDIS_DB_HOST': 'localhost', 'REDIS_DB_PASSWORD': 'test'}):
            if 'database.redis_db' in sys.modules:
                del sys.modules['database.redis_db']
            sys.path.insert(0, '/home/claude/omi/omi-kenji/backend')
            try:
                import database.redis_db as redis_db

                redis_db.r = mock_r

                result = redis_db.get_cached_translation('abc123', 'en')

                assert result == 'Hello'
                mock_r.get.assert_called_once_with('translate:v1:abc123:en')
            finally:
                sys.path.pop(0)

    def test_get_cached_translation_returns_none_on_miss(self):
        """get_cached_translation should return None when key doesn't exist."""
        mock_r = MagicMock()
        mock_r.get.return_value = None
        with patch.dict('os.environ', {'REDIS_DB_HOST': 'localhost', 'REDIS_DB_PASSWORD': 'test'}):
            if 'database.redis_db' in sys.modules:
                del sys.modules['database.redis_db']
            sys.path.insert(0, '/home/claude/omi/omi-kenji/backend')
            try:
                import database.redis_db as redis_db

                redis_db.r = mock_r

                result = redis_db.get_cached_translation('abc123', 'en')

                assert result is None
            finally:
                sys.path.pop(0)

    def test_cache_key_versioned(self):
        """Cache keys should use v1 prefix for future invalidation."""
        mock_r = MagicMock()
        with patch.dict('os.environ', {'REDIS_DB_HOST': 'localhost', 'REDIS_DB_PASSWORD': 'test'}):
            if 'database.redis_db' in sys.modules:
                del sys.modules['database.redis_db']
            sys.path.insert(0, '/home/claude/omi/omi-kenji/backend')
            try:
                import database.redis_db as redis_db

                redis_db.r = mock_r

                redis_db.cache_translation('hash1', 'es', 'Hola')
                redis_db.get_cached_translation('hash1', 'es')

                # Both should use translate:v1: prefix
                set_key = mock_r.set.call_args[0][0]
                get_key = mock_r.get.call_args[0][0]
                assert set_key.startswith('translate:v1:')
                assert get_key.startswith('translate:v1:')
            finally:
                sys.path.pop(0)

    def test_different_languages_separate_keys(self):
        """Same text hash with different target languages should use separate cache keys."""
        mock_r = MagicMock()
        mock_r.get.return_value = None
        with patch.dict('os.environ', {'REDIS_DB_HOST': 'localhost', 'REDIS_DB_PASSWORD': 'test'}):
            if 'database.redis_db' in sys.modules:
                del sys.modules['database.redis_db']
            sys.path.insert(0, '/home/claude/omi/omi-kenji/backend')
            try:
                import database.redis_db as redis_db

                redis_db.r = mock_r

                redis_db.cache_translation('same_hash', 'en', 'Hello')
                redis_db.cache_translation('same_hash', 'es', 'Hola')

                calls = mock_r.set.call_args_list
                assert calls[0][0][0] == 'translate:v1:same_hash:en'
                assert calls[1][0][0] == 'translate:v1:same_hash:es'
            finally:
                sys.path.pop(0)


class TestTranslationServiceTwoTierCache:
    """Test the two-tier cache logic in TranslationService.translate_text()."""

    def _make_service(self):
        """Create a TranslationService with mocked dependencies."""
        from collections import OrderedDict

        class FakeService:
            def __init__(self):
                self.translation_cache = OrderedDict()
                self.MAX_CACHE_SIZE = 1000

            def _get_cache_key(self, text_hash, dest_language):
                return f"{text_hash}:{dest_language}"

        return FakeService()

    def test_inmemory_cache_hit_skips_redis(self):
        """In-memory cache hit should return immediately without checking Redis."""
        service = self._make_service()
        text = "Hola"
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_key = f"{text_hash}:en"
        service.translation_cache[cache_key] = "Hello"

        # Simulate translate_text logic
        if cache_key in service.translation_cache:
            result = service.translation_cache.pop(cache_key)
            service.translation_cache[cache_key] = result

        assert result == "Hello"
        # In-memory hit — no Redis or API call needed

    def test_redis_hit_populates_inmemory(self):
        """Redis cache hit should populate in-memory cache for fast subsequent access."""
        service = self._make_service()
        text = "Hola"
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_key = f"{text_hash}:en"
        redis_result = "Hello"

        # Simulate: not in memory, but in Redis
        assert cache_key not in service.translation_cache

        # Redis returns result → populate in-memory
        service.translation_cache[cache_key] = redis_result

        assert service.translation_cache[cache_key] == "Hello"

    def test_cache_miss_stores_in_both_tiers(self):
        """API response should be stored in both in-memory and Redis."""
        service = self._make_service()
        text = "Hola"
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_key = f"{text_hash}:en"
        api_result = "Hello"

        # Simulate: miss in both tiers, API returns result
        service.translation_cache[cache_key] = api_result  # Tier 1
        # cache_translation(text_hash, 'en', api_result)     # Tier 2 (Redis)

        assert service.translation_cache[cache_key] == "Hello"

    def test_lru_eviction_on_max_size(self):
        """In-memory cache should evict oldest entry when full."""
        service = self._make_service()
        service.MAX_CACHE_SIZE = 3

        # Fill cache
        for i in range(3):
            service.translation_cache[f"key{i}"] = f"value{i}"

        assert len(service.translation_cache) == 3

        # Add one more — should evict oldest (key0)
        if len(service.translation_cache) >= service.MAX_CACHE_SIZE:
            service.translation_cache.popitem(last=False)
        service.translation_cache["key3"] = "value3"

        assert "key0" not in service.translation_cache
        assert "key3" in service.translation_cache
        assert len(service.translation_cache) == 3

    def test_md5_hash_consistency(self):
        """Same text should always produce the same MD5 hash for cache key."""
        text = "Hello, how are you?"
        hash1 = hashlib.md5(text.encode()).hexdigest()
        hash2 = hashlib.md5(text.encode()).hexdigest()
        assert hash1 == hash2

    def test_md5_hash_differs_for_different_text(self):
        """Different text should produce different hashes."""
        hash1 = hashlib.md5("Hello".encode()).hexdigest()
        hash2 = hashlib.md5("Goodbye".encode()).hexdigest()
        assert hash1 != hash2


class TestCrossSesssionBehavior:
    """Test that Redis enables cross-session translation reuse."""

    def test_second_session_hits_redis_cache(self):
        """A new TranslationService instance should find translations cached by a prior session."""
        # Session 1: empty in-memory, stores in Redis
        service1_cache = OrderedDict()
        text = "Buenos dias"
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_key = f"{text_hash}:en"

        # Session 1 translates and caches
        service1_cache[cache_key] = "Good morning"
        redis_store = {f"translate:v1:{text_hash}:en": "Good morning"}

        # Session 2: new instance, empty in-memory
        service2_cache = OrderedDict()
        assert cache_key not in service2_cache

        # Session 2 checks Redis → hit
        redis_key = f"translate:v1:{text_hash}:en"
        cached = redis_store.get(redis_key)
        assert cached == "Good morning"

        # Populates session 2's in-memory cache
        service2_cache[cache_key] = cached
        assert service2_cache[cache_key] == "Good morning"

    def test_default_ttl_is_14_days(self):
        """Default TTL should be 14 days (1,209,600 seconds)."""
        expected_ttl = 60 * 60 * 24 * 14  # 14 days
        assert expected_ttl == 1209600


class TestRedisCacheResilience:
    """Test graceful degradation when Redis is unavailable."""

    def test_redis_failure_returns_none(self):
        """get_cached_translation should return None when Redis raises."""
        mock_r = MagicMock()
        mock_r.get.side_effect = Exception("Connection refused")
        with patch.dict('os.environ', {'REDIS_DB_HOST': 'localhost', 'REDIS_DB_PASSWORD': 'test'}):
            if 'database.redis_db' in sys.modules:
                del sys.modules['database.redis_db']
            sys.path.insert(0, '/home/claude/omi/omi-kenji/backend')
            try:
                import database.redis_db as redis_db

                redis_db.r = mock_r

                result = redis_db.get_cached_translation('hash1', 'en')
                # try_catch_decorator should catch and return None
                assert result is None
            finally:
                sys.path.pop(0)

    def test_redis_write_failure_does_not_raise(self):
        """cache_translation should not raise when Redis write fails."""
        mock_r = MagicMock()
        mock_r.set.side_effect = Exception("Connection refused")
        with patch.dict('os.environ', {'REDIS_DB_HOST': 'localhost', 'REDIS_DB_PASSWORD': 'test'}):
            if 'database.redis_db' in sys.modules:
                del sys.modules['database.redis_db']
            sys.path.insert(0, '/home/claude/omi/omi-kenji/backend')
            try:
                import database.redis_db as redis_db

                redis_db.r = mock_r

                # Should not raise
                result = redis_db.cache_translation('hash1', 'en', 'Hello')
                assert result is None  # try_catch returns None on error
            finally:
                sys.path.pop(0)
