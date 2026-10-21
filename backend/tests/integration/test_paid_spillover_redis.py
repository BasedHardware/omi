"""Local disposable Redis verifies the actual fleet admission Lua contract."""

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest
import redis.asyncio as aioredis

from utils.stt.paid_admission import ADMIT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_atomic_paid_spillover_budget_across_clients_and_minutes():
    executable = shutil.which('redis-server')
    if executable is None:
        pytest.skip('Local qualification requires redis-server')
    with tempfile.TemporaryDirectory(prefix='omi-stt-budget-') as directory:
        socket = str(Path(directory) / 'redis.sock')
        process = subprocess.Popen(
            [executable, '--port', '0', '--unixsocket', socket, '--save', '', '--appendonly', 'no'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        owned = Path(os.getenv('OMI_OWNED_PID_FILE', str(Path(directory) / 'owned-pids.txt')))
        with owned.open('a') as output:
            output.write(f'{process.pid}\n')
        clients = [aioredis.Redis(unix_socket_path=socket) for _ in range(4)]
        try:
            for _ in range(100):
                try:
                    await clients[0].ping()
                    break
                except aioredis.ConnectionError:
                    await asyncio.sleep(0.01)
            outcomes = await asyncio.gather(
                *(clients[index % 4].eval(ADMIT, 1, 'synthetic:modulate', 30) for index in range(200))
            )
            assert sum(outcomes) == 30
            assert await clients[0].eval(ADMIT, 1, 'synthetic:soniox', 30) == 1
            # Simulate a prior Redis-owned minute, without client time skew.
            await clients[0].hset('synthetic:modulate', 'minute', -1)
            assert await clients[1].eval(ADMIT, 1, 'synthetic:modulate', 30) == 1
            assert await clients[1].hget('synthetic:modulate', 'count') == b'1'
            assert await clients[0].eval(ADMIT, 1, 'synthetic:zero', 0) == 0
            assert 0 < await clients[0].ttl('synthetic:zero') <= 120
        finally:
            await asyncio.gather(*(client.aclose() for client in clients))
            process.terminate()
            process.wait(timeout=5)
