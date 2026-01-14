"""
Global cache instances for in-memory caching.

This module provides singleton access to cache managers.
Instances are initialized during application startup in main.py.
"""

from typing import Optional
from utils.cache_manager import InMemoryCacheManager
from utils.redis_pubsub import RedisPubSubManager

# Global cache instances (initialized in main.py via init_cache())
memory_cache: Optional[InMemoryCacheManager] = None
pubsub_manager: Optional[RedisPubSubManager] = None


def get_memory_cache() -> InMemoryCacheManager:
    """
    Get the global memory cache instance.

    Returns:
        The initialized memory cache instance

    Raises:
        RuntimeError: If cache not initialized
    """
    if memory_cache is None:
        raise RuntimeError("Memory cache not initialized. Call init_cache() first.")
    return memory_cache


def get_pubsub_manager() -> RedisPubSubManager:
    """
    Get the global pub/sub manager instance.

    Returns:
        The initialized pub/sub manager instance

    Raises:
        RuntimeError: If pub/sub manager not initialized
    """
    if pubsub_manager is None:
        raise RuntimeError("Pub/sub manager not initialized. Call init_cache() first.")
    return pubsub_manager


def init_cache(max_memory_mb: int = 100):
    """
    Initialize global cache instances.

    Should be called once during application startup in main.py.

    Args:
        max_memory_mb: Maximum memory in MB for in-memory cache (default: 100MB)
    """
    global memory_cache, pubsub_manager

    from database.redis_db import r

    memory_cache = InMemoryCacheManager(max_memory_mb=max_memory_mb)
    pubsub_manager = RedisPubSubManager(r)

    # Register callback: when invalidation message received, clear memory cache
    pubsub_manager.register_callback(
        'get_public_approved_apps_data*',
        lambda keys: [memory_cache.delete(k) for k in keys]
    )

    # Start pub/sub subscription
    pubsub_manager.start()


def shutdown_cache():
    """Shutdown cache managers gracefully."""
    if pubsub_manager:
        pubsub_manager.stop()
