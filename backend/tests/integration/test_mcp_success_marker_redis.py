"""Local Redis independence of per-success markers; never uses configured remote Redis or PostHog."""

import shutil
import subprocess
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import redis

from utils import mcp_analytics as analytics

pytestmark = pytest.mark.integration


@pytest.fixture
def local_redis():
    binary = shutil.which('redis-server')
    if binary is None:
        pytest.skip('local redis-server is required')
    temporary = tempfile.TemporaryDirectory(prefix='omi-mcp-', dir='/tmp')
    socket = temporary.name + '/redis.sock'
    process = subprocess.Popen(
        [binary, '--port', '0', '--unixsocket', socket, '--save', '', '--appendonly', 'no'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = redis.Redis(unix_socket_path=socket, socket_timeout=1)
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                if client.ping():
                    break
            except redis.ConnectionError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.02)
        yield client
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=5)
        temporary.cleanup()


def test_success_stream_ignores_redis_while_transport_presence_still_dedupes(local_redis, monkeypatch):
    monkeypatch.setattr(analytics.redis_db, 'r', local_redis)
    capture = Mock(return_value=True)
    monkeypatch.setattr(analytics, 'emit_product_event', capture)
    at = datetime(2026, 10, 15, 23, 59, 59, tzinfo=timezone.utc)

    def emit(timestamp=at):
        analytics.emit_mcp_tool_use_succeeded(
            uid='local-test', tool_name='get_memories', client_name='codex', initiator='unknown', occurred_at=timestamp
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: emit(), range(32)))
    emit(at + timedelta(seconds=1))
    assert capture.call_count == 33
    assert not list(local_redis.scan_iter('mcp:tool-success:*'))
    # Only the unchanged presence diagnostic uses the daily Redis claim.
    assert analytics._claim_daily_active_marker('local-test', now=at) is True
    assert analytics._claim_daily_active_marker('local-test', now=at) is False
    local_redis.close()
    monkeypatch.setattr(analytics.redis_db, 'r', Mock(set=Mock(side_effect=ConnectionError('offline'))))
    emit()
    assert capture.call_count == 34
