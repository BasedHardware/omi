"""
Global cache instances for in-memory caching.

Uses lazy initialization - caches are created on first access.
Cleanup is handled automatically via atexit.
"""

import atexit
from typing import Optional
from database.cache_manager import InMemoryCacheManager
from database.redis_pubsub import RedisPubSubManager
from database.redis_db import r

# Global cache instances (lazily initialized)
_memory_cache: Optional[InMemoryCacheManager] = None
_pubsub_manager: Optional[RedisPubSubManager] = None
_initialized: bool = False


def _ensure_initialized():
    """Initialize caches on first access."""
    global _memory_cache, _pubsub_manager, _initialized

    if _initialized:
        return

    _memory_cache = InMemoryCacheManager(max_memory_mb=100)
    _pubsub_manager = RedisPubSubManager(r)

    # Register callbacks: when invalidation message received, clear memory cache
    _pubsub_manager.register_callback(
        'get_public_approved_apps_data*',
        lambda keys: [_memory_cache.delete(k) for k in keys]
    )
    _pubsub_manager.register_callback(
        'get_popular_apps_data',
        lambda keys: [_memory_cache.delete(k) for k in keys]
    )

    # Start pub/sub subscription
    _pubsub_manager.start()
    _initialized = True


def get_memory_cache() -> InMemoryCacheManager:
    """Get the global memory cache instance (lazy init)."""
    _ensure_initialized()
    return _memory_cache


def get_pubsub_manager() -> RedisPubSubManager:
    """Get the global pub/sub manager instance (lazy init)."""
    _ensure_initialized()
    return _pubsub_manager


def _shutdown():
    """Cleanup on process exit."""
    global _pubsub_manager
    if _pubsub_manager:
        _pubsub_manager.stop()


# Register cleanup handler
atexit.register(_shutdown)
