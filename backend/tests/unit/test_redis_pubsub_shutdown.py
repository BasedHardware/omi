from unittest.mock import MagicMock, patch
import fakeredis

from database.redis_pubsub import RedisPubSubManager
import database.cache as cache_module


def test_redis_pubsub_stop_cleanly():
    """Verify RedisPubSubManager cleanly stops and terminates subscriber thread within timeout."""
    fake_client = fakeredis.FakeRedis()
    manager = RedisPubSubManager(fake_client)
    manager.start()

    assert manager.running is True
    assert manager.subscriber_thread is not None
    assert manager.subscriber_thread.is_alive() is True

    manager.stop(timeout=1.0)

    assert manager.running is False
    assert manager.subscriber_thread.is_alive() is False


def test_redis_pubsub_stop_suppresses_closed_stream_logging_error():
    """Verify stop() does not raise ValueError when Python stream handlers are closed during atexit."""
    fake_client = fakeredis.FakeRedis()
    manager = RedisPubSubManager(fake_client)
    manager.start()

    with patch("database.redis_pubsub.logger.info", side_effect=ValueError("I/O operation on closed file.")), patch(
        "database.redis_pubsub.logger.error", side_effect=ValueError("I/O operation on closed file.")
    ):
        # Should not raise any exception despite logging failures
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
        # Should not raise
        cache_module._shutdown()
