from __future__ import annotations

import logging

from utils.redis_memory_health import (
    HEALTH_LOG_MARKER,
    REDIS_CLOUD_MAXMEMORY_BYTES,
    THRESHOLD_RATIO,
    run_scheduled_check,
    used_memory_ratio,
)


class _FakeRedis:
    def __init__(self, used: int | None = None, error: Exception | None = None):
        self._used = used
        self._error = error

    def info(self, section: str) -> dict[str, int]:
        assert section == 'memory'
        if self._error is not None:
            raise self._error
        assert self._used is not None
        return {'used_memory': self._used}


def test_ratio_uses_12gib_sku_ceiling() -> None:
    assert REDIS_CLOUD_MAXMEMORY_BYTES == 12 * 1024**3
    assert used_memory_ratio(REDIS_CLOUD_MAXMEMORY_BYTES) == 1.0
    assert used_memory_ratio(int(REDIS_CLOUD_MAXMEMORY_BYTES * 0.64)) < THRESHOLD_RATIO


def test_logs_only_when_at_or_above_90_percent(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger='utils.redis_memory_health'):
        run_scheduled_check(redis_client=_FakeRedis(used=REDIS_CLOUD_MAXMEMORY_BYTES))
        assert f'{HEALTH_LOG_MARKER} threshold=90' in caplog.text
        caplog.clear()
        run_scheduled_check(redis_client=_FakeRedis(used=int(REDIS_CLOUD_MAXMEMORY_BYTES * 0.64)))
        assert HEALTH_LOG_MARKER not in caplog.text


def test_fail_open_on_redis_error(caplog) -> None:
    with caplog.at_level(logging.ERROR, logger='utils.redis_memory_health'):
        run_scheduled_check(redis_client=_FakeRedis(error=RuntimeError('down')))
        assert 'redis_memory_health failed' in caplog.text
