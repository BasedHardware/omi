"""Execute the production scripts against an isolated local Redis when installed.

The clock-controlled fleet tests are always hermetic. These extra checks catch
Lua syntax/return-value mistakes that the fake client's dispatch cannot detect.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time

import pytest
import redis

from utils.other import fsr_leader_lease as leases


@pytest.fixture
def local_redis():
    binary = shutil.which('redis-server')
    if binary is None:
        pytest.skip('optional production-Lua check needs a local redis-server binary')
    with tempfile.TemporaryDirectory(prefix='fsr-wq1-', dir='/tmp') as directory:
        socket = f'{directory}/redis.sock'
        process = subprocess.Popen(
            [binary, '--port', '0', '--unixsocket', socket, '--save', '', '--appendonly', 'no'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        client = redis.Redis(unix_socket_path=socket, socket_timeout=0.25)
        try:
            deadline = time.monotonic() + 2
            while True:
                try:
                    client.ping()
                    break
                except redis.ConnectionError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        pytest.fail('isolated Redis did not start')
                    time.sleep(0.01)
            yield client
        finally:
            client.close()
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def test_actual_lua_stale_tick_takeover_cas_fencing_and_retry_deadline(local_redis):
    client = local_redis
    keys = leases.LeaderLease('lua_recovery').keys
    first = client.eval(leases._ADMIT, 3, *keys, '', 'owner', 900000, 300000, 0)
    assert first[:3] == [1, 1, 0]
    denied = client.eval(leases._ADMIT, 3, *keys, '', 'next', 900000, 300000, 0)
    assert denied[:3] == [0, 0, 0]
    assert 299000 < denied[3] <= 300000  # Wake at tick expiry, not 900s ownership TTL.
    client.delete(keys[2])  # Model Redis's tick expiry, while ownership is live.
    second = client.eval(leases._ADMIT, 3, *keys, '', 'next', 900000, 300000, 0)
    assert second[:3] == [2, 1, 0]
    assert client.eval(leases._RENEW, 1, keys[0], 'owner', 900000) == 0
    assert client.eval(leases._RELEASE, 2, keys[0], keys[2], 'owner', 1) == 0
    assert client.get(keys[2]) == b'2'
    assert client.eval(leases._RELEASE, 2, keys[0], keys[2], 'next', 1) == 1
    assert client.get(keys[0]) is None and client.get(keys[2]) is None
    assert client.eval(leases._ADMIT, 3, *keys, '', 'replacement', 900000, 300000, 0)[:3] == [3, 1, 0]


def test_actual_lua_persistent_tick_cannot_block_recovery_forever(local_redis):
    client = local_redis
    keys = leases.LeaderLease('lua_bad_tick').keys
    client.set(keys[0], 'dead-owner', px=900000)
    client.set(keys[2], 'invalid-no-expiration')
    result = client.eval(leases._ADMIT, 3, *keys, '', 'replacement', 600000, 300000, 0)
    assert result[:3] == [1, 1, 0]
    assert 299000 < client.pttl(keys[2]) <= 300000


def test_actual_lua_queue_keeps_live_owner_even_without_tick(local_redis):
    client = local_redis
    keys = leases.LeaderLease(leases.QUEUE_AGE_LOOP).keys
    assert client.eval(leases._ADMIT, 3, *keys, '', 'publisher', 120000, 300000, 1)[:3] == [1, 1, 0]
    client.delete(keys[2])
    result = client.eval(leases._ADMIT, 3, *keys, '', 'follower', 120000, 300000, 1)
    assert result[:3] == [0, 0, 0]
    assert client.get(keys[0]) == b'publisher'
