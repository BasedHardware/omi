"""Attach bounded attribution to SDK BulkWriter batches on first use."""

from __future__ import annotations

import functools
import logging
from contextvars import ContextVar
from threading import Lock
from typing import Any

from database.firestore_read_origin import current_read_origin
from database.firestore_write_probe import (
    WriteAttribution,
    UNATTRIBUTED_WRITE,
    bulk_write_attribution,
    write_caller,
    patch_write_probe,
)

logger = logging.getLogger(__name__)
_retry_attribution: ContextVar[WriteAttribution | None] = ContextVar('firestore_bulk_retry_attribution', default=None)
_install_lock = Lock()
_installed = False


def _wrap_bulk_enqueue(original: Any) -> Any:
    @functools.wraps(original)
    def enqueue(writer: Any) -> Any:
        # The SDK calls this just after appending a new operation and before
        # handing a full batch to its executor.
        try:
            writer._operations[-1]._omi_write_attribution = _retry_attribution.get() or (
                write_caller(),
                current_read_origin(),
            )
        except Exception:
            logger.warning('firestore write probe failed to capture bulk attribution')
        return original(writer)

    return enqueue


def _wrap_bulk_retry(original: Any) -> Any:
    @functools.wraps(original)
    def retry(retry_entry: Any, *args: Any, **kwargs: Any) -> Any:
        # The SDK constructs a new operation when re-queueing a failed one.
        token = _retry_attribution.set(getattr(retry_entry.operation, '_omi_write_attribution', UNATTRIBUTED_WRITE))
        try:
            return original(retry_entry, *args, **kwargs)
        finally:
            _retry_attribution.reset(token)

    return retry


def _wrap_bulk_dispatch(original: Any) -> Any:
    @functools.wraps(original)
    def dispatch(writer: Any, batch: Any, operations: Any) -> Any:
        # BulkWriter never puts two mutations for the same document in one batch.
        # Attach only bounded labels, keyed by paths already held by the batch.
        try:
            batch._omi_write_attribution = {
                tuple(operation.reference._path): getattr(operation, '_omi_write_attribution', UNATTRIBUTED_WRITE)
                for operation in operations
            }
        except Exception:
            logger.warning('firestore write probe failed to associate bulk attribution')
        # Serial sends run callbacks inline. A callback that queues its own
        # write must capture its own caller and origin.
        token = _retry_attribution.set(None)
        try:
            return original(writer, batch, operations)
        finally:
            _retry_attribution.reset(token)

    return dispatch


def _wrap_bulk_send(original: Any) -> Any:
    @functools.wraps(original)
    def send(writer: Any, batch: Any) -> Any:
        # This runs in the SDK worker when parallel sending is enabled.
        token = bulk_write_attribution.set(getattr(batch, '_omi_write_attribution', {}))
        try:
            return original(writer, batch)
        finally:
            bulk_write_attribution.reset(token)

    return send


def install_bulk_attribution() -> None:
    """Install once before the first writer is returned, including under concurrent construction."""
    global _installed
    if _installed:
        return
    from google.cloud.firestore_v1.bulk_writer import BulkWriter, OperationRetry

    with _install_lock:
        if _installed:
            return
        patch_write_probe(BulkWriter, '_maybe_enqueue_current_batch', _wrap_bulk_enqueue)
        patch_write_probe(BulkWriter, '_send_batch', _wrap_bulk_dispatch)
        patch_write_probe(BulkWriter, '_send', _wrap_bulk_send)
        patch_write_probe(OperationRetry, 'retry', _wrap_bulk_retry)
        _installed = True
