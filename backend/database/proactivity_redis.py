"""Lazy v2 Redis connection, independent of legacy cache/reservation evidence."""

import os
from functools import lru_cache
from typing import Any

import redis

from database import redis_db


@lru_cache(maxsize=1)
def _client(host: str, port: int, password: str | None) -> Any:
    return redis.Redis(
        host=host,
        port=port,
        password=password,
        username='default',
        health_check_interval=30,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )


def get_client() -> Any:
    """Use v2 bindings when present; otherwise reuse the host's normal Redis.

    Explicit v2 hosts never inherit the normal store's password or port. Reading
    settings at the call boundary keeps imports free of new clients or I/O.
    """
    host = os.getenv('PROACTIVITY_REDIS_HOST', '').strip()
    if not host:
        return redis_db.r
    return _client(host, int(os.getenv('PROACTIVITY_REDIS_PORT', '6379')), os.getenv('PROACTIVITY_REDIS_PASSWORD'))


def set_mentor_sent_at(uid: str, *, app_id: str, ts: int, ttl: int) -> None:
    get_client().set(f'{uid}:{app_id}:proactive_noti_sent_at', ts, ex=ttl)
