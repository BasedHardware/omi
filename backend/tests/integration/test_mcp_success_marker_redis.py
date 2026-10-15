"""Local Redis atomic marker contract; never uses configured remote Redis or PostHog."""

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


def test_real_redis_cross_worker_claim_settlement_and_failed_capture_retry(local_redis, monkeypatch):
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
    assert capture.call_count == 1
    keys = list(local_redis.scan_iter('mcp:tool-success:*'))
    assert len(keys) == 1
    assert local_redis.get(keys[0]) == b'done'
    assert 172790 <= local_redis.ttl(keys[0]) <= 172800
    # A lost/stale worker cannot release another worker's settled claim.
    assert local_redis.eval(analytics._MCP_SUCCESS_SETTLE, 1, keys[0], 'stale-owner', 'release', 172800) == 0
    capture.return_value = False
    emit(at + timedelta(seconds=1))
    assert len(list(local_redis.scan_iter('mcp:tool-success:*'))) == 1
    capture.return_value = True
    emit(at + timedelta(seconds=1))
    emit(at + timedelta(seconds=1))
    assert capture.call_count == 3
    assert capture.call_args_list[1].kwargs['event_uuid'] == capture.call_args_list[2].kwargs['event_uuid']
