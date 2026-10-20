"""Install task write fences on the real Firestore SDK commit surfaces."""

import functools
import inspect
from typing import Any

from google.cloud.firestore_v1.batch import WriteBatch
from google.cloud.firestore_v1.transaction import Transaction
from google.cloud.firestore_v1.async_batch import AsyncWriteBatch
from google.cloud.firestore_v1.async_transaction import AsyncTransaction
from google.cloud.firestore_v1.bulk_batch import BulkWriteBatch
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.async_document import AsyncDocumentReference

from database import action_item_versions as versions
from utils.executors import db_executor, run_blocking


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
                    tickets.append((uid, await run_blocking(db_executor, versions.begin, uid)))
                return await original(batch, *args, **kwargs)
            finally:
                for uid, ticket in tickets:
                    await run_blocking(db_executor, versions.finish, uid, ticket)

        wrapped = async_commit
    else:

        @functools.wraps(original)
        def sync_commit(batch: Any, *args: Any, **kwargs: Any) -> Any:
            tickets = [(uid, versions.begin(uid)) for uid in sorted(_owners(batch))]
            try:
                return original(batch, *args, **kwargs)
            finally:
                # Invalidate even on partial/ambiguous commit or transaction retry.
                for uid, ticket in tickets:
                    versions.finish(uid, ticket)

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
