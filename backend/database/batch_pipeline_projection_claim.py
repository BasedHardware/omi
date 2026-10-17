"""Advisory owner coalescing; Firestore receipts remain the write authority."""

from contextlib import contextmanager
from functools import lru_cache
import logging
from uuid import uuid4

from database import redis_db

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300
REDIS_TIMEOUT_SECONDS = 1.0
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@lru_cache(maxsize=1)
def _redis_client():
    # The general Redis client has unbounded socket I/O. This advisory lease
    # must fail open promptly instead of holding the durable drain indefinitely.
    return redis_db.create_bounded_redis_client(REDIS_TIMEOUT_SECONDS)


@contextmanager
def projection_claim(namespace: str, hashed_owner: str):
    # Namespace isolates stages; owner coalescing also avoids two different
    # segments competing on the same projection watermark/assignment index.
    key = f'batch_projection:{namespace}:{hashed_owner}'
    token = uuid4().hex
    acquired = False
    try:
        client = _redis_client()
        acquired = bool(client.set(key, token, nx=True, ex=LEASE_SECONDS))
    except Exception as error:
        # This is a contention optimization, never a mutation fence. Preserve
        # Redis fail-open behavior; bounded transaction retries remain active.
        logger.warning(
            'event=batch_projection action=claim outcome=unavailable exception_type=%s', type(error).__name__
        )
        yield True
        return
    try:
        yield acquired
    finally:
        if acquired:
            try:
                client.eval(_RELEASE_LUA, 1, key, token)
            except Exception as error:
                logger.warning(
                    'event=batch_projection action=release outcome=unavailable exception_type=%s', type(error).__name__
                )
