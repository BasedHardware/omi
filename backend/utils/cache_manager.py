"""
In-memory LRU cache manager for reducing Redis egress costs.

This module provides a thread-safe in-memory cache with:
- LRU eviction when memory limit reached
- Per-entry TTL support
- Memory usage tracking
- Thread-safe operations
"""

import json
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheEntry:
    """Represents a cache entry with metadata."""
    data: Any
    timestamp: float
    size_bytes: int
    ttl: int


class InMemoryCacheManager:
    """
    Thread-safe LRU in-memory cache with size-based eviction.

    Features:
    - LRU eviction when memory limit reached
    - Per-entry TTL support
    - Memory usage tracking
    - Thread-safe operations

    Example:
        cache = InMemoryCacheManager(max_memory_mb=100)
        cache.set('key', {'data': 'value'}, ttl=30)
        data = cache.get('key')  # Returns {'data': 'value'} if not expired
    """

    def __init__(self, max_memory_mb: int = 100):
        """
        Initialize cache manager.

        Args:
            max_memory_mb: Maximum memory in MB for cache (default: 100MB)
        """
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
        self.current_size = 0

        # Stats
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Get cache entry if exists and not expired.

        Args:
            key: Cache key

        Returns:
            Cached data if exists and not expired, None otherwise
        """
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None

            entry = self.cache[key]

            # Check TTL
            if time.time() - entry.timestamp > entry.ttl:
                self._delete_locked(key)
                self.misses += 1
                return None

            # Move to end (LRU)
            self.cache.move_to_end(key)
            self.hits += 1
            return entry.data

    def set(self, key: str, data: Any, ttl: int = 30):
        """
        Set cache entry with automatic eviction if needed.

        Args:
            key: Cache key
            data: Data to cache
            ttl: Time to live in seconds (default: 30)
        """
        with self.lock:
            # Calculate size
            size_bytes = self._calculate_size(data)

            # Remove old entry if exists
            if key in self.cache:
                self._delete_locked(key)

            # Evict if needed
            self._evict_if_needed(size_bytes)

            # Add new entry
            entry = CacheEntry(
                data=data,
                timestamp=time.time(),
                size_bytes=size_bytes,
                ttl=ttl
            )
            self.cache[key] = entry
            self.current_size += size_bytes

    def delete(self, key: str):
        """
        Delete cache entry.

        Args:
            key: Cache key
        """
        with self.lock:
            self._delete_locked(key)

    def clear(self):
        """Clear all cache entries."""
        with self.lock:
            self.cache.clear()
            self.current_size = 0
            self.hits = 0
            self.misses = 0
            self.evictions = 0

    def _delete_locked(self, key: str):
        """
        Internal delete (assumes lock is held).

        Args:
            key: Cache key
        """
        if key in self.cache:
            entry = self.cache.pop(key)
            self.current_size -= entry.size_bytes

    def _evict_if_needed(self, required_bytes: int):
        """
        Evict LRU entries until space available.

        Args:
            required_bytes: Bytes needed for new entry
        """
        while (self.current_size + required_bytes > self.max_memory_bytes
               and len(self.cache) > 0):
            # Remove oldest (first item in OrderedDict)
            key, entry = self.cache.popitem(last=False)
            self.current_size -= entry.size_bytes
            self.evictions += 1

    def _calculate_size(self, obj: Any) -> int:
        """
        Estimate object size in bytes.

        Args:
            obj: Object to measure

        Returns:
            Estimated size in bytes
        """
        if isinstance(obj, (list, dict)):
            # Serialize to JSON and measure
            json_str = json.dumps(obj, default=str)
            return sys.getsizeof(json_str)
        return sys.getsizeof(obj)

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

            return {
                'entries': len(self.cache),
                'size_mb': round(self.current_size / (1024 * 1024), 2),
                'max_size_mb': round(self.max_memory_bytes / (1024 * 1024), 2),
                'utilization': round(self.current_size / self.max_memory_bytes * 100, 2),
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': round(hit_rate, 2),
                'evictions': self.evictions
            }
