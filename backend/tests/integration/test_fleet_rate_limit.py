"""Opt-in real Redis/Lua fleet admission; run only against an owned local server."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import redis

from database.redis_db import reserve_rate_limit

pytestmark = pytest.mark.integration


def test_distributed_fleet_budget_and_denied_attempts():
    port = os.environ.get('FLEET_TEST_REDIS_PORT')
    if not port:
        pytest.skip('requires an owned loopback Redis via FLEET_TEST_REDIS_PORT')
    client = redis.Redis(host='127.0.0.1', port=int(port), socket_connect_timeout=1, socket_timeout=1)
    subject = 'fleet-integration-' + uuid4().hex
    key = 'rl:telemetry:fleet:' + subject
    try:
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(
                pool.map(
                    lambda _: reserve_rate_limit(subject, 'telemetry:fleet', 12, 3600, redis_client=client), range(32)
                )
            )
        assert sum(result[0] for result in results) == 12
        assert int(client.get(key)) == 12
        assert 3590 <= client.ttl(key) <= 3600
        for _ in range(10):
            allowed, remaining, reset = reserve_rate_limit(subject, 'telemetry:fleet', 12, 3600, redis_client=client)
            assert not allowed and remaining == 0 and 0 < reset <= 3600
        assert int(client.get(key)) == 12
    finally:
        client.delete(key)
        client.close()
