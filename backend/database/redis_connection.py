"""Redis connection construction without product database or business imports."""

import os
from typing import Any, cast

import redis


def redis_connection_kwargs(*, health_check_interval: int = 30, env_prefix: str = 'REDIS_DB_') -> dict[str, Any]:
    port_env = os.getenv(f'{env_prefix}PORT')
    return {
        'host': cast(str, os.getenv(f'{env_prefix}HOST')),
        'port': int(port_env) if port_env is not None else 6379,
        'username': 'default',
        'password': os.getenv(f'{env_prefix}PASSWORD'),
        'health_check_interval': health_check_interval,
    }


def create_bounded_redis_client(timeout_seconds: float, *, env_prefix: str = 'REDIS_DB_') -> Any:
    kwargs = redis_connection_kwargs(env_prefix=env_prefix)
    kwargs['socket_connect_timeout'] = timeout_seconds
    kwargs['socket_timeout'] = timeout_seconds
    return redis.Redis(**kwargs)
