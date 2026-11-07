"""
Redis Pub/Sub manager for distributed cache invalidation.

This module provides a pub/sub system for synchronizing cache invalidation
across multiple backend instances in a distributed system.
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, cast

import redis

logger = logging.getLogger(__name__)

# redis.Redis is untyped under strict Pyright; treat the client/pubsub objects
# as Any at this SDK boundary.
RedisClientT = Any


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

    def __init__(self, redis_client: RedisClientT) -> None:
        """
        Initialize pub/sub manager.

        Args:
            redis_client: Redis client instance
        """
        self.redis_client: RedisClientT = redis_client
        self.pubsub: Optional[Any] = None
        self.subscriber_thread: Optional[threading.Thread] = None
        self.running = False
        self._stop_event = threading.Event()
        self.callbacks: Dict[str, List[Callable[[List[str]], None]]] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _safe_log(log_fn: Callable[[str], None], message: str) -> None:
        """Log without raising if stdio streams are already closed during interpreter shutdown."""
        try:
            log_fn(message)
        except Exception:
            pass

    @staticmethod
    def _run_bounded(action: Callable[[], None], deadline: float) -> bool:
        """Run a potentially blocking teardown action on a daemon thread up to deadline."""
        remaining = max(0.0, deadline - time.monotonic())
        worker = threading.Thread(target=action, daemon=True, name='redis-pubsub-teardown')
        worker.start()
        worker.join(timeout=remaining)
        return not worker.is_alive()

    def start(self) -> None:
        """Start the pub/sub subscription thread."""
        if self.running:
            logger.warning("PubSub manager already running")
            return

        self._stop_event.clear()
        self.running = True

        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe(self.CHANNEL)
            self.pubsub = pubsub

            self.subscriber_thread = threading.Thread(
                target=self._subscribe_loop, daemon=True, name='redis-pubsub-subscriber'
            )
            self.subscriber_thread.start()
            logger.info(f"Started Redis pub/sub subscription on channel: {self.CHANNEL}")
        except Exception as e:
            logger.error(f"Failed to start Redis pub/sub: {e}")
            self.running = False
            self._stop_event.set()
            raise

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the subscription and clean up within a bounded deadline."""
        self.running = False
        self._stop_event.set()
        stop_timeout = (
            max(0.0, float(timeout))
            if isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
            else 5.0
        )
        deadline = time.monotonic() + stop_timeout
        pubsub = self.pubsub

        if pubsub:
            def _unsubscribe() -> None:
                try:
                    pubsub.unsubscribe(self.CHANNEL)
                except Exception as e:
                    self._safe_log(logger.error, f"Error closing pub/sub connection: {e}")

            self._run_bounded(_unsubscribe, deadline)

        if (
            self.subscriber_thread
            and self.subscriber_thread.is_alive()
            and self.subscriber_thread is not threading.current_thread()
        ):
            try:
                self.subscriber_thread.join(timeout=max(0.0, deadline - time.monotonic()))
            except Exception:
                pass

        if pubsub:
            def _close() -> None:
                try:
                    pubsub.close()
                except Exception as e:
                    self._safe_log(logger.error, f"Error closing pub/sub connection: {e}")

            if time.monotonic() < deadline or stop_timeout == 0.0:
                self._run_bounded(_close, deadline)

        self._safe_log(logger.info, "Stopped Redis pub/sub manager")

    def register_callback(self, key_pattern: str, callback: Callable[[List[str]], None]) -> None:
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

    def publish_invalidation(self, keys: List[str]) -> None:
        """
        Publish cache invalidation event.

        Args:
            keys: List of cache keys to invalidate
        """
        message = {'event': 'invalidate', 'keys': keys, 'timestamp': time.time()}

        try:
            self.redis_client.publish(self.CHANNEL, json.dumps(message))
            logger.debug(f"Published invalidation for keys: {keys}")
        except Exception as e:
            logger.error(f"Failed to publish invalidation: {e}")

    def _subscribe_loop(self) -> None:
        """Background loop for receiving pub/sub messages."""
        while self.running:
            try:
                if self.pubsub is None:
                    if self._stop_event.wait(timeout=self.RECONNECT_DELAY):
                        break
                    continue
                message: Optional[Dict[str, Any]] = self.pubsub.get_message(timeout=1.0)
                if message and message.get('type') == 'message':
                    self._handle_message(message.get('data'))
            except redis.ConnectionError as e:
                if not self.running:
                    break
                self._safe_log(logger.error, f"Redis connection error in pub/sub: {e}")
                self._reconnect()
            except Exception as e:
                if not self.running:
                    break
                self._safe_log(logger.error, f"Error in pub/sub loop: {e}")
                if self._stop_event.wait(timeout=self.RECONNECT_DELAY):
                    break

    def _reconnect(self) -> None:
        """Attempt to reconnect to Redis pub/sub."""
        if not self.running:
            return
        self._safe_log(logger.info, "Attempting to reconnect to Redis pub/sub...")
        if self._stop_event.wait(timeout=self.RECONNECT_DELAY) or not self.running:
            return

        pubsub: Optional[Any] = None
        try:
            if self.pubsub:
                self.pubsub.close()
            if not self.running:
                return
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe(self.CHANNEL)
            if not self.running:
                try:
                    pubsub.unsubscribe(self.CHANNEL)
                except Exception:
                    pass
                try:
                    pubsub.close()
                except Exception:
                    pass
                return
            self.pubsub = pubsub
            self._safe_log(logger.info, "Successfully reconnected to Redis pub/sub")
        except Exception as e:
            if pubsub is not None and not self.running:
                try:
                    pubsub.close()
                except Exception:
                    pass
            if self.running:
                self._safe_log(logger.error, f"Failed to reconnect: {e}")

    def _handle_message(self, data: Any) -> None:
        """
        Handle incoming pub/sub message.

        Args:
            data: Raw message data
        """
        try:
            if isinstance(data, bytes):
                payload = data.decode('utf-8')
            elif isinstance(data, str):
                payload = data
            else:
                return
            message = json.loads(payload)
            event = message.get('event')
            keys_raw = message.get('keys', [])
            keys: List[str] = [str(k) for k in cast(List[Any], keys_raw)] if isinstance(keys_raw, list) else []

            if event == 'invalidate':
                logger.debug(f"Received invalidation for keys: {keys}")
                self._trigger_callbacks(keys)
        except Exception as e:
            logger.error(f"Error handling pub/sub message: {e}")

    def _trigger_callbacks(self, keys: List[str]) -> None:
        """
        Trigger registered callbacks for invalidated keys.

        Args:
            keys: List of invalidated keys
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
