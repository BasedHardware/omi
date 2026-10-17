"""Advisory owner coalescing; Firestore receipts remain the write authority."""

from contextlib import contextmanager
import logging
from uuid import uuid4

from database import redis_db

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300


@contextmanager
def projection_claim(namespace: str, hashed_owner: str):
    # Namespace isolates stages; owner coalescing also avoids two different
    # segments competing on the same projection watermark/assignment index.
    key = f'batch_projection:{namespace}:{hashed_owner}'
    token = uuid4().hex
    acquired = False
    try:
        acquired = bool(redis_db.r.set(key, token, nx=True, ex=LEASE_SECONDS))
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
                redis_db.release_token_lock(key, token)
            except Exception as error:
                logger.warning(
                    'event=batch_projection action=release outcome=unavailable exception_type=%s', type(error).__name__
                )
