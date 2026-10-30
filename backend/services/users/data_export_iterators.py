from __future__ import annotations

from typing import IO, Any, Iterator, Mapping

from database import _client as database_client
from utils.other.portability_read import PortabilityReadContext, iter_portability_guarded, portability_read_scope


class SpooledExportIterator:
    """Read chunks out of a finished export spool, closing it exactly once.

    Unlike a suspended generator, ``close()`` releases the spool even when the
    iterator was never started — the response layer may tear down before the
    first chunk is sent.
    """

    def __init__(self, export_spool: IO[str]) -> None:
        self._spool = export_spool
        self._closed = False

    def __iter__(self) -> "SpooledExportIterator":
        return self

    def __next__(self) -> str:
        if self._closed:
            raise StopIteration
        chunk = self._spool.read(64 * 1024)
        if not chunk:
            self.close()
            raise StopIteration
        return chunk

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._spool.close()


class PortabilityScopedIterator:
    """Bind a PortabilityReadContext to each step of a sync export generator.

    The context variable is set only for the duration of each ``next()`` so a
    suspended generator never leaks the scope into unrelated reads, and a worker
    thread copy cannot strand it. Cancellation is checked around every step and
    ``close()`` always reaches the underlying generator exactly once.
    """

    def __init__(self, source: Iterator[str], context: PortabilityReadContext) -> None:
        self._source = source
        self._context = context
        self._closed = False

    def __iter__(self) -> "PortabilityScopedIterator":
        return self

    def __next__(self) -> str:
        if self._closed:
            raise StopIteration
        self._context.check()
        try:
            with portability_read_scope(self._context):
                item = next(self._source)
        except StopIteration:
            self.close()
            raise
        self._context.check()
        return item

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with portability_read_scope(self._context):
            close = getattr(self._source, 'close', None)
            if callable(close):
                close()


def iter_user_subcollection(
    uid: str,
    collection_name: str,
    *,
    firestore_client: Any | None = None,
) -> Iterator[Mapping[str, Any]]:
    """Stream one user-owned primary collection without loading it in memory."""

    client = firestore_client if firestore_client is not None else database_client.get_firestore_client()
    collection = client.collection('users').document(uid).collection(collection_name)
    stream = iter_portability_guarded(collection.stream())
    try:
        for snapshot in stream:
            payload = snapshot.to_dict()
            if not isinstance(payload, dict):
                continue
            row = dict(payload)
            row.setdefault('id', snapshot.id)
            yield row
    finally:
        stream.close()


def iter_user_nested_subcollection(
    uid: str,
    parent_collection_name: str,
    child_collection_name: str,
    *,
    firestore_client: Any | None = None,
) -> Iterator[Mapping[str, Any]]:
    """Stream user-visible records nested below one user-owned collection."""

    client = firestore_client if firestore_client is not None else database_client.get_firestore_client()
    parents = client.collection('users').document(uid).collection(parent_collection_name)
    parent_stream = iter_portability_guarded(parents.stream())
    try:
        for parent_snapshot in parent_stream:
            child_stream = iter_portability_guarded(
                parent_snapshot.reference.collection(child_collection_name).stream()
            )
            try:
                for child_snapshot in child_stream:
                    payload = child_snapshot.to_dict()
                    if not isinstance(payload, dict):
                        continue
                    row = dict(payload)
                    row.setdefault('id', child_snapshot.id)
                    row['parent_id'] = parent_snapshot.id
                    yield row
            finally:
                child_stream.close()
    finally:
        parent_stream.close()
