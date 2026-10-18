"""Developer action-item cache fence at the SDK commit boundary.

Every document mutation, batch, transaction, async commit and BulkWriter batch
passes this boundary, including dynamic-collection undo and recursive deletion.
A random version cannot alias a cached page after expiry/eviction. Overlapping
writers keep the version busy until all have completed. Uncertain Redis replies
poison caching instead of publishing an unfenced version. Never stores task data.
"""

import functools
import hashlib
import inspect
import logging
from uuid import uuid4
from typing import Any

from google.cloud.firestore_v1.batch import WriteBatch
from google.cloud.firestore_v1.transaction import Transaction
from google.cloud.firestore_v1.async_batch import AsyncWriteBatch
from google.cloud.firestore_v1.async_transaction import AsyncTransaction
from google.cloud.firestore_v1.bulk_batch import BulkWriteBatch
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.async_document import AsyncDocumentReference

from database import redis_db
from utils.executors import db_executor, run_blocking
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
VERSION_TTL = 7 * 86400
BUSY = '!busy'
_READ = """
if redis.call('EXISTS', KEYS[2]) == 1 then return '!busy' end
local version = redis.call('GET', KEYS[1])
if not version then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return ARGV[1]
end
return version
"""
_BEGIN = """
redis.call('SET', KEYS[1], '!busy')
if redis.call('HGET', KEYS[2], 'poison') then return 0 end
redis.call('HSET', KEYS[2], ARGV[1], '1')
return 1
"""
_END = """
redis.call('SET', KEYS[1], '!busy')
if not redis.call('HGET', KEYS[2], ARGV[1]) or ARGV[2] ~= '1' then
    redis.call('HSET', KEYS[2], 'poison', '1')
end
redis.call('HDEL', KEYS[2], ARGV[1])
if redis.call('HLEN', KEYS[2]) == 0 then
    redis.call('SET', KEYS[1], ARGV[3], 'EX', ARGV[4])
end
"""


@functools.lru_cache(maxsize=1)
def _redis() -> Any:
    return redis_db.create_bounded_redis_client(0.1)


def _key(uid: str) -> str:
    return 'external-action-items:v1:{' + hashlib.sha256(uid.encode()).hexdigest() + '}'


def _unavailable() -> None:
    record_fallback(
        component='redis_cache',
        from_mode='write_version',
        to_mode='uncached',
        reason='unavailable',
        outcome='degraded',
        log=logger,
    )


def version(uid: str) -> str | None:
    try:
        key = _key(uid)
        value = _redis().eval(_READ, 2, key, key + ':writers', uuid4().hex, VERSION_TTL)
        value = value.decode() if isinstance(value, bytes) else value
        return value if isinstance(value, str) and value and value != BUSY else None
    except Exception:
        _unavailable()
        return None


def begin(uid: str) -> tuple[str, bool]:
    token = uuid4().hex
    try:
        key = _key(uid)
        return token, _redis().eval(_BEGIN, 2, key, key + ':writers', token) == 1
    except Exception:
        _unavailable()
        return token, False


def finish(uid: str, ticket: tuple[str, bool]) -> None:
    try:
        key = _key(uid)
        _redis().eval(_END, 2, key, key + ':writers', ticket[0], int(ticket[1]), uuid4().hex, VERSION_TTL)
    except Exception:
        _unavailable()


def _owners(batch: Any) -> set[str]:
    owners = set()
    # Inspect the actual pending Write protobufs before commit clears them.
    if hasattr(batch, '_write_pbs'):
        paths = [write.delete or write.update.name or write.transform.document for write in batch._write_pbs]
    else:
        # DocumentReference.delete bypasses WriteBatch and commits directly.
        paths = [batch._document_path]
    for path in paths:
        parts = path.split('/')
        if len(parts) == 9 and parts[4:6] == ['documents', 'users'] and parts[7] == 'action_items':
            owners.add(parts[6])
    return owners


def _wrap(original: Any) -> Any:
    if getattr(original, '_omi_action_item_fence', False):
        return original
    wrapped: Any
    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def async_commit(batch: Any, *args: Any, **kwargs: Any) -> Any:
            tickets = []
            try:
                for uid in sorted(_owners(batch)):
                    tickets.append((uid, await run_blocking(db_executor, begin, uid)))
                return await original(batch, *args, **kwargs)
            finally:
                for uid, ticket in tickets:
                    await run_blocking(db_executor, finish, uid, ticket)

        wrapped = async_commit
    else:

        @functools.wraps(original)
        def sync_commit(batch: Any, *args: Any, **kwargs: Any) -> Any:
            tickets = [(uid, begin(uid)) for uid in sorted(_owners(batch))]
            try:
                return original(batch, *args, **kwargs)
            finally:
                # Invalidate even on partial/ambiguous commit or transaction retry.
                for uid, ticket in tickets:
                    finish(uid, ticket)

        wrapped = sync_commit
    setattr(wrapped, '_omi_action_item_fence', True)
    return wrapped


def install_write_fences() -> None:
    for cls, method in (
        (WriteBatch, 'commit'),
        (Transaction, '_commit'),
        (AsyncWriteBatch, 'commit'),
        (AsyncTransaction, '_commit'),
        (BulkWriteBatch, 'commit'),
        (DocumentReference, 'delete'),
        (AsyncDocumentReference, 'delete'),
    ):
        setattr(cls, method, _wrap(getattr(cls, method)))
