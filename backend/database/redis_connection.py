"""Redis connection construction without product database or business imports."""

import os
from typing import Any, cast

import redis


def redis_connection_kwargs(*, health_check_interval: int = 30) -> dict[str, Any]:
    port_env = os.getenv('REDIS_DB_PORT')
    return {
        'host': cast(str, os.getenv('REDIS_DB_HOST')),
        'port': int(port_env) if port_env is not None else 6379,
        'username': 'default',
        'password': os.getenv('REDIS_DB_PASSWORD'),
        'health_check_interval': health_check_interval,
    }


def create_bounded_redis_client(timeout_seconds: float) -> Any:
    kwargs = redis_connection_kwargs()
    kwargs['socket_connect_timeout'] = timeout_seconds
    kwargs['socket_timeout'] = timeout_seconds
    return redis.Redis(**kwargs)
