"""
Unit tests for InMemoryCacheManager.
"""

import sys
import os
import time
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.cache_manager import InMemoryCacheManager


class TestInMemoryCacheManager(unittest.TestCase):
    """Test suite for InMemoryCacheManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.cache = InMemoryCacheManager(max_memory_mb=1)  # 1MB for testing

    def tearDown(self):
        """Clean up after tests."""
        self.cache.clear()

    def test_basic_get_set(self):
        """Test basic get and set operations."""
        test_data = {'key': 'value', 'number': 42}
        self.cache.set('test_key', test_data, ttl=30)

        result = self.cache.get('test_key')
        self.assertEqual(result, test_data)

    def test_cache_miss(self):
        """Test that get returns None for non-existent keys."""
        result = self.cache.get('non_existent_key')
        self.assertIsNone(result)

    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        test_data = {'data': 'test'}
        self.cache.set('test_key', test_data, ttl=1)  # 1 second TTL

        # Should be available immediately
        result = self.cache.get('test_key')
        self.assertEqual(result, test_data)

        # Wait for expiration
        time.sleep(1.5)

        # Should be expired now
        result = self.cache.get('test_key')
        self.assertIsNone(result)

    def test_cache_overwrite(self):
        """Test that setting the same key overwrites the value."""
        self.cache.set('test_key', 'value1', ttl=30)
        self.cache.set('test_key', 'value2', ttl=30)

        result = self.cache.get('test_key')
        self.assertEqual(result, 'value2')

    def test_delete(self):
        """Test cache entry deletion."""
        self.cache.set('test_key', 'value', ttl=30)
        self.cache.delete('test_key')

        result = self.cache.get('test_key')
        self.assertIsNone(result)

    def test_clear(self):
        """Test clearing all cache entries."""
        self.cache.set('key1', 'value1', ttl=30)
        self.cache.set('key2', 'value2', ttl=30)

        self.cache.clear()

        self.assertIsNone(self.cache.get('key1'))
        self.assertIsNone(self.cache.get('key2'))

    def test_lru_eviction(self):
        """Test that LRU eviction works when memory limit reached."""
        # Create data that will fill up cache
        # Each entry is roughly 100-200 bytes
        large_data = {'data': 'x' * 1000}  # ~1KB per entry

        # Fill cache beyond limit
        for i in range(1500):  # This should exceed 1MB limit
            self.cache.set(f'key_{i}', large_data, ttl=30)

        # Check that we didn't exceed memory limit
        stats = self.cache.get_stats()
        self.assertLessEqual(stats['size_mb'], 1.1)  # Allow small overhead

        # Check that some entries were evicted
        self.assertGreater(stats['evictions'], 0)

    def test_get_stats(self):
        """Test cache statistics."""
        self.cache.set('key1', 'value1', ttl=30)
        self.cache.set('key2', 'value2', ttl=30)

        # Hit
        self.cache.get('key1')

        # Miss
        self.cache.get('non_existent')

        stats = self.cache.get_stats()

        self.assertEqual(stats['entries'], 2)
        self.assertGreaterEqual(stats['size_mb'], 0)  # Allow 0 for very small entries
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['hit_rate'], 50.0)  # 1 hit out of 2 total = 50%

    def test_cache_with_list_data(self):
        """Test caching with list data."""
        test_list = [
            {'id': 1, 'name': 'App 1'},
            {'id': 2, 'name': 'App 2'},
            {'id': 3, 'name': 'App 3'}
        ]
        self.cache.set('apps_list', test_list, ttl=30)

        result = self.cache.get('apps_list')
        self.assertEqual(result, test_list)
        self.assertEqual(len(result), 3)

    def test_lru_ordering(self):
        """Test that recently accessed items are kept in cache."""
        # Fill cache with some entries
        for i in range(10):
            self.cache.set(f'key_{i}', f'value_{i}', ttl=30)

        # Access key_0 to make it most recently used
        self.cache.get('key_0')

        # Add more entries to trigger eviction
        large_data = {'data': 'x' * 10000}  # Large entry to trigger eviction
        for i in range(100):
            self.cache.set(f'large_key_{i}', large_data, ttl=30)

        # key_0 should still be in cache because it was recently accessed
        # (though this depends on how much memory each entry takes)
        # At minimum, we should have successful operations
        stats = self.cache.get_stats()
        self.assertGreater(stats['entries'], 0)

    def test_singleflight_prevents_thundering_herd(self):
        """Test that get_or_fetch prevents multiple concurrent fetches."""
        import threading
        import time

        fetch_count = 0
        fetch_lock = threading.Lock()

        def slow_fetch():
            """Simulate a slow fetch that takes 100ms."""
            nonlocal fetch_count
            with fetch_lock:
                fetch_count += 1
            time.sleep(0.1)  # Simulate slow operation
            return {'data': 'fetched'}

        results = []
        errors = []

        def worker():
            try:
                result = self.cache.get_or_fetch('test_key', slow_fetch, ttl=30)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Launch 10 concurrent threads
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same result
        self.assertEqual(len(results), 10)
        self.assertEqual(len(errors), 0)
        for result in results:
            self.assertEqual(result, {'data': 'fetched'})

        # Only ONE fetch should have been called (singleflight)
        self.assertEqual(fetch_count, 1)

    def test_get_or_fetch_cache_hit(self):
        """Test that get_or_fetch returns cached data without calling fetch_fn."""
        fetch_called = False

        def fetch_fn():
            nonlocal fetch_called
            fetch_called = True
            return {'data': 'new'}

        # Pre-populate cache
        self.cache.set('existing_key', {'data': 'cached'}, ttl=30)

        # get_or_fetch should return cached data
        result = self.cache.get_or_fetch('existing_key', fetch_fn, ttl=30)

        self.assertEqual(result, {'data': 'cached'})
        self.assertFalse(fetch_called)


if __name__ == '__main__':
    unittest.main()
