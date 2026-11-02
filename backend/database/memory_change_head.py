"""Atomic, content-free invalidation for released memory query projections.

Installed on the GAPIC commit boundary, so document, batch, transaction,
sync and async writes (including hard deletes and field transforms) share the
same atomic change head. The source operation's response remains unchanged.
Non-atomic bulk writes permanently disqualify an owner before any source write.
"""

import functools
import inspect
import uuid
from typing import Any

from google.cloud.firestore_v1.services.firestore import FirestoreClient, FirestoreAsyncClient
from google.cloud.firestore_v1.types import CommitRequest, CommitResponse, Document, DocumentMask, Value, Write
from database.memory_collections import RELEASED_MEMORY_CHANGE_HEAD as HEAD_DOCUMENT

SOURCE_COLLECTIONS = frozenset({'memory_items', 'memories', 'memory_historical_overrides'})


def owners(writes: Any) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for write in writes:
        if isinstance(write, dict):
            update = write.get('update') or {}
            transform = write.get('transform') or {}
            path = (
                write.get('delete')
                or (update.get('name') if isinstance(update, dict) else update.name)
                or (transform.get('document') if isinstance(transform, dict) else transform.document)
                or ''
            )
        else:
            path = write.delete or write.update.name or write.transform.document
        parts = path.split('/')
        if len(parts) == 9 and parts[4:6] == ['documents', 'users'] and parts[7] in SOURCE_COLLECTIONS:
            result.add(('/'.join(parts[:5]), parts[6]))
    return result


def head_write(root: str, uid: str, *, blocked: bool = False) -> Write:
    fields = {'token': Value(string_value=uuid.uuid4().hex), 'schema': Value(integer_value=1)}
    if blocked:
        fields['blocked'] = Value(boolean_value=True)
    # A normal source commit never clears a bulk writer's permanent block.
    return Write(
        update=Document(name=f'{root}/users/{uid}/memory_state/{HEAD_DOCUMENT}', fields=fields),
        update_mask=DocumentMask(field_paths=list(fields)),
    )


def augment_commit(request: Any) -> tuple[Any, int]:
    writes = (request.get('writes') if isinstance(request, dict) else request.writes) or ()
    count = len(writes)
    affected = owners(writes)
    if not affected:
        # Do not copy large transcript/conversation commits on this hot path.
        return request, count
    prepared = CommitRequest(request)
    for root, uid in sorted(affected):
        prepared.writes.append(head_write(root, uid))
    return prepared, count


def _wrap_commit(original: Any) -> Any:
    if getattr(original, '_omi_memory_change_head', False):
        return original
    wrapped: Any

    def prepare(request: Any, kwargs: dict[str, Any]) -> tuple[Any, int]:
        # Preserve GAPIC's request-versus-flattened-arguments validation.
        fields = {key: kwargs.pop(key) for key in ('database', 'writes', 'transaction') if key in kwargs}
        if request is not None and any(value is not None for value in fields.values()):
            raise ValueError('request and flattened commit fields cannot both be supplied')
        return augment_commit(request if request is not None else fields)

    def response(value: Any, count: int) -> Any:
        if len(value.write_results) == count:
            return value
        result = CommitResponse(value)
        del result.write_results[count:]
        return result

    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def async_commit(client: Any, request: Any = None, **kwargs: Any) -> Any:
            prepared, count = prepare(request, kwargs)
            return response(await original(client, request=prepared, **kwargs), count)

        wrapped = async_commit
    else:

        @functools.wraps(original)
        def sync_commit(client: Any, request: Any = None, **kwargs: Any) -> Any:
            prepared, count = prepare(request, kwargs)
            return response(original(client, request=prepared, **kwargs), count)

        wrapped = sync_commit
    setattr(wrapped, '_omi_memory_change_head', True)
    return wrapped


def _wrap_bulk(original: Any) -> Any:
    if getattr(original, '_omi_memory_change_head', False):
        return original
    wrapped: Any

    def barrier(request: Any, kwargs: dict[str, Any]) -> dict[str, Any] | None:
        writes = request.get('writes', []) if isinstance(request, dict) else getattr(request, 'writes', [])
        database = request.get('database') if isinstance(request, dict) else getattr(request, 'database', None)
        affected = owners(writes or kwargs.get('writes', []))
        if not affected:
            return None
        return {
            'database': database or kwargs.get('database'),
            'writes': [head_write(root, uid, blocked=True) for root, uid in sorted(affected)],
        }

    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def async_bulk(client: Any, request: Any = None, **kwargs: Any) -> Any:
            block = barrier(request, kwargs)
            if block is not None:
                options = {key: kwargs[key] for key in ('retry', 'timeout', 'metadata') if key in kwargs}
                await client.commit(request=block, **options)
            return await original(client, request=request, **kwargs)

        wrapped = async_bulk
    else:

        @functools.wraps(original)
        def sync_bulk(client: Any, request: Any = None, **kwargs: Any) -> Any:
            block = barrier(request, kwargs)
            if block is not None:
                options = {key: kwargs[key] for key in ('retry', 'timeout', 'metadata') if key in kwargs}
                client.commit(request=block, **options)
            return original(client, request=request, **kwargs)

        wrapped = sync_bulk
    setattr(wrapped, '_omi_memory_change_head', True)
    return wrapped


def install_write_heads() -> None:
    for cls in (FirestoreClient, FirestoreAsyncClient):
        setattr(cls, 'commit', _wrap_commit(cls.commit))
        setattr(cls, 'batch_write', _wrap_bulk(cls.batch_write))
