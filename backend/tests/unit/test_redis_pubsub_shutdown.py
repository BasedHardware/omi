import threading
from unittest.mock import MagicMock, patch

from database.redis_pubsub import RedisPubSubManager
import database.cache as cache_module


class _FakePubSub:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self.subscribed_channels: list[str] = []
        self.closed = False

    def subscribe(self, channel: str) -> None:
        self.subscribed_channels.append(channel)

    def unsubscribe(self, channel: str) -> None:
        if channel in self.subscribed_channels:
            self.subscribed_channels.remove(channel)
        self._stop_event.set()

    def get_message(self, timeout: float = 1.0):
        self._stop_event.wait(timeout=min(float(timeout), 0.05))
        return None

    def close(self) -> None:
        self.closed = True
        self._stop_event.set()


class _FakeRedis:
    def __init__(self) -> None:
        self.last_pubsub: _FakePubSub | None = None

    def pubsub(self) -> _FakePubSub:
        self.last_pubsub = _FakePubSub()
        return self.last_pubsub


def test_redis_pubsub_stop_cleanly():
    """Verify RedisPubSubManager cleanly stops and terminates subscriber thread within timeout."""
    fake_client = _FakeRedis()
    manager = RedisPubSubManager(fake_client)
    manager.start()

    assert manager.running is True
    assert manager.subscriber_thread is not None
    assert manager.subscriber_thread.is_alive() is True

    manager.stop(timeout=1.0)

    assert manager.running is False
    assert manager.subscriber_thread.is_alive() is False
    assert fake_client.last_pubsub is not None
    assert fake_client.last_pubsub.closed is True


def test_redis_pubsub_stop_suppresses_closed_stream_logging_error():
    """Verify stop() does not raise ValueError when Python stream handlers are closed during atexit."""
    fake_client = _FakeRedis()
    manager = RedisPubSubManager(fake_client)
    manager.start()

    with patch("database.redis_pubsub.logger.info", side_effect=ValueError("I/O operation on closed file.")), patch(
        "database.redis_pubsub.logger.error", side_effect=ValueError("I/O operation on closed file.")
    ):
        manager.stop(timeout=1.0)

    assert manager.running is False


def test_cache_shutdown_calls_stop_with_bounded_timeout():
    """Verify cache._shutdown() passes bounded timeout to prevent blocking interpreter exit."""
    mock_manager = MagicMock()
    with patch.object(cache_module, "_pubsub_manager", mock_manager):
        cache_module._shutdown()
        mock_manager.stop.assert_called_once_with(timeout=0.2)


def test_cache_shutdown_suppresses_exceptions():
    """Verify cache._shutdown() suppresses any errors during interpreter exit."""
    mock_manager = MagicMock()
    mock_manager.stop.side_effect = RuntimeError("Fatal connection blip")
    with patch.object(cache_module, "_pubsub_manager", mock_manager):
        cache_module._shutdown()
