"""
Redis Pub/Sub manager for distributed cache invalidation.

This module provides a pub/sub system for synchronizing cache invalidation
across multiple backend instances in a distributed system.
"""

import json
import logging
import threading
import time
from typing import Callable, Dict, List

import redis

logger = logging.getLogger(__name__)


class RedisPubSubManager:
    """
    Manages Redis pub/sub for distributed cache invalidation.

    Features:
    - Background subscription thread
    - Automatic reconnection on failure
    - Event-based callback system
    - Graceful shutdown

    Example:
        pubsub = RedisPubSubManager(redis_client)
        pubsub.register_callback('cache_key*', lambda keys: print(f"Invalidate {keys}"))
        pubsub.start()
        pubsub.publish_invalidation(['cache_key_1', 'cache_key_2'])
        pubsub.stop()
    """

    CHANNEL = 'cache_invalidation'
    RECONNECT_DELAY = 5  # seconds

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize pub/sub manager.

        Args:
            redis_client: Redis client instance
        """
        self.redis_client = redis_client
        self.pubsub = None
        self.subscriber_thread = None
        self.running = False
        self.callbacks: Dict[str, List[Callable]] = {}
        self.lock = threading.Lock()

    def start(self):
        """Start the pub/sub subscription thread."""
        if self.running:
            logger.warning("PubSub manager already running")
            return

        self.running = True

        try:
            self.pubsub = self.redis_client.pubsub()
            self.pubsub.subscribe(self.CHANNEL)

            self.subscriber_thread = threading.Thread(
                target=self._subscribe_loop,
                daemon=True,
                name='redis-pubsub-subscriber'
            )
            self.subscriber_thread.start()
            logger.info(f"Started Redis pub/sub subscription on channel: {self.CHANNEL}")
        except Exception as e:
            logger.error(f"Failed to start Redis pub/sub: {e}")
            self.running = False
            raise

    def stop(self):
        """Stop the subscription and clean up."""
        self.running = False

        if self.pubsub:
            try:
                self.pubsub.unsubscribe(self.CHANNEL)
                self.pubsub.close()
            except Exception as e:
                logger.error(f"Error closing pub/sub connection: {e}")

        if self.subscriber_thread:
            self.subscriber_thread.join(timeout=5)

        logger.info("Stopped Redis pub/sub manager")

    def register_callback(self, key_pattern: str, callback: Callable[[List[str]], None]):
        """
        Register a callback for cache invalidation events.

        Args:
            key_pattern: Pattern to match cache keys (supports '*' wildcard at end)
            callback: Function to call with list of invalidated keys
        """
        with self.lock:
            if key_pattern not in self.callbacks:
                self.callbacks[key_pattern] = []
            self.callbacks[key_pattern].append(callback)
            logger.debug(f"Registered callback for pattern: {key_pattern}")

    def publish_invalidation(self, keys: List[str]):
        """
        Publish cache invalidation event.

        Args:
            keys: List of cache keys to invalidate
        """
        message = {
            'event': 'invalidate',
            'keys': keys,
            'timestamp': time.time()
        }

        try:
            self.redis_client.publish(self.CHANNEL, json.dumps(message))
            logger.debug(f"Published invalidation for keys: {keys}")
        except Exception as e:
            logger.error(f"Failed to publish invalidation: {e}")

    def _subscribe_loop(self):
        """Background loop for receiving pub/sub messages."""
        while self.running:
            try:
                message = self.pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    self._handle_message(message['data'])
            except redis.ConnectionError as e:
                logger.error(f"Redis connection error in pub/sub: {e}")
                self._reconnect()
            except Exception as e:
                logger.error(f"Error in pub/sub loop: {e}")
                time.sleep(self.RECONNECT_DELAY)

    def _reconnect(self):
        """Attempt to reconnect to Redis pub/sub."""
        logger.info("Attempting to reconnect to Redis pub/sub...")
        time.sleep(self.RECONNECT_DELAY)

        try:
            if self.pubsub:
                self.pubsub.close()
            self.pubsub = self.redis_client.pubsub()
            self.pubsub.subscribe(self.CHANNEL)
            logger.info("Successfully reconnected to Redis pub/sub")
        except Exception as e:
            logger.error(f"Failed to reconnect: {e}")

    def _handle_message(self, data: bytes):
        """
        Handle incoming pub/sub message.

        Args:
            data: Raw message data
        """
        try:
            message = json.loads(data.decode('utf-8'))
            event = message.get('event')
            keys = message.get('keys', [])

            if event == 'invalidate':
                logger.debug(f"Received invalidation for keys: {keys}")
                self._trigger_callbacks(keys)
        except Exception as e:
            logger.error(f"Error handling pub/sub message: {e}")

    def _trigger_callbacks(self, keys: List[str]):
        """
        Trigger registered callbacks for invalidated keys.

        Args:
            keys: List of invalidated cache keys
        """
        with self.lock:
            for key in keys:
                # Match exact keys
                if key in self.callbacks:
                    for callback in self.callbacks[key]:
                        try:
                            callback([key])
                        except Exception as e:
                            logger.error(f"Error in callback for key {key}: {e}")

                # Match wildcard patterns
                for pattern, callbacks in self.callbacks.items():
                    if pattern.endswith('*') and key.startswith(pattern[:-1]):
                        for callback in callbacks:
                            try:
                                callback([key])
                            except Exception as e:
                                logger.error(f"Error in callback for pattern {pattern}: {e}")
