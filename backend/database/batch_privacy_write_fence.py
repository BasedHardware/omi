"""Atomic batch-privacy invalidation at the Firestore Commit boundary.

The opaque token is independent of the admission/erasure generation. No reads,
credentials or clients are needed to prepare it. Source preconditions and result
positions are preserved. Install in every writer process before enabling readers.
"""

import functools
import hashlib
import inspect
from typing import Any, cast
from uuid import uuid4

from google.api_core.exceptions import GoogleAPICallError
from google.cloud.firestore_v1.services.firestore import FirestoreAsyncClient, FirestoreClient
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud.firestore_v1.types import (
    BatchWriteRequest,
    BatchWriteResponse,
    CommitRequest,
    CommitResponse,
    Document,
    DocumentMask,
    Value,
    Write,
    WriteResult,
)
from google.rpc import status_pb2
from database.batch_privacy_attempt import CONVERSATION_AUTHORITY_FIELDS, TOKEN_FIELD, SCHEMA_FIELD, TOKEN_SCHEMA

# Protobuf builds this class dynamically; the installed module has no typed declaration.
Status = cast(Any, status_pb2).Status

PRIVACY_COLLECTION = 'batch_pipeline_privacy'
_ROOT_AUTHORITIES = frozenset({'account_deletions', 'legal_holds', 'legal_hold_deletion_gates'})
_USER_FIELDS = frozenset(
    {'data_protection_level', 'migration_status', 'private_cloud_sync_enabled', 'speaker_auto_enroll_privacy_version'}
)
_CONVERSATION_FIELDS = CONVERSATION_AUTHORITY_FIELDS
_AUTHORITY_STATE_TYPES = {'generation': 'integer_value', 'blocked': 'boolean_value', 'purging': 'boolean_value'}


def _authority_path(path: str) -> tuple[str, ...]:
    try:
        return FieldPath.from_api_repr(path).parts
    except ValueError:
        raise ValueError('invalid batch privacy authority field path') from None


def _validate_authority_write(write: Any) -> None:
    """Invalidate a decision without silently removing its durable authority."""
    if write.delete:
        raise ValueError('batch privacy authority must survive deletion')
    transforms = [*write.update_transforms, *write.transform.field_transforms]
    for transform in transforms:
        if _authority_path(transform.field_path)[0] in _AUTHORITY_STATE_TYPES:
            raise ValueError('batch privacy authority state requires explicit typed values')
    if not write.update.name:
        return
    fields = write.update.fields
    if Write.pb(write).HasField('update_mask'):
        paths = [_authority_path(path) for path in write.update_mask.field_paths]
        state = set()
        for path in paths:
            if path[0] in _AUTHORITY_STATE_TYPES:
                if len(path) != 1:
                    raise ValueError('batch privacy authority state cannot be nested')
                state.add(path[0])
    else:
        # A replacement removes every omitted field, even if its payload only
        # mentions metadata. The epoch writer already supplies all three fields.
        state = set(_AUTHORITY_STATE_TYPES)
    for name in state:
        if name not in fields or Value.pb(fields[name]).WhichOneof('value_type') != _AUTHORITY_STATE_TYPES[name]:
            raise ValueError('batch privacy authority state cannot be removed or malformed')
        if name == 'generation' and fields[name].integer_value < 0:
            raise ValueError('batch privacy authority generation must be nonnegative')


def _changes_answer(write: Any, fields: frozenset[str]) -> bool:
    # An upsert can change document existence even when its field mask is only
    # metadata. Only a masked update with an exists=True precondition may be
    # excluded. CAS update_time also proves existence, but conservatively fences.
    if write.delete or not write.current_document.exists or not Write.pb(write).HasField('update_mask'):
        return True
    paths = [*write.update_mask.field_paths, *(t.field_path for t in write.update_transforms)]
    return any(path.split('.', 1)[0].strip('`') in fields for path in paths)


def authority_tokens(writes: Any) -> set[str]:
    """Return fully qualified token documents, including project AND database.

    All writes to authority documents qualify, including dynamic payloads,
    field deletes/transforms, metadata-only creates and hard deletes. Subcollection
    content that the privacy guard never reads does not qualify.
    """
    tokens = set()
    for raw in writes:
        write = Write(raw) if isinstance(raw, dict) else raw
        path = write.delete or write.update.name or write.transform.document
        parts = path.split('/')
        if len(parts) < 7 or parts[0] != 'projects' or parts[2] != 'databases' or parts[4] != 'documents':
            continue
        root, family, owner = '/'.join(parts[:5]), parts[5], parts[6]
        if family == PRIVACY_COLLECTION and len(parts) == 7:
            # This authority intentionally survives account erasure. Recreating
            # a deleted row with token fields alone would erase block/purge
            # state and its generation. Refuse before any RPC, including bulk.
            _validate_authority_write(write)
            tokens.add(path)
        elif (family in _ROOT_AUTHORITIES and len(parts) == 7) or (
            family == 'users'
            and (len(parts) == 7 or len(parts) == 9 and parts[7] in {'conversations', 'deleted_conversations'})
        ):
            if family == 'users' and len(parts) == 7 and not _changes_answer(write, _USER_FIELDS):
                continue
            if family == 'users' and len(parts) == 9 and parts[7] == 'conversations':
                if not _changes_answer(write, _CONVERSATION_FIELDS):
                    continue
            key = hashlib.sha256(owner.encode()).hexdigest()
            tokens.add(f'{root}/{PRIVACY_COLLECTION}/{key}')
    return tokens


def token_write(path: str) -> Write:
    return Write(
        update=Document(
            name=path,
            fields={TOKEN_FIELD: Value(string_value=uuid4().hex), SCHEMA_FIELD: Value(integer_value=TOKEN_SCHEMA)},
        ),
        update_mask=DocumentMask(field_paths=[TOKEN_FIELD, SCHEMA_FIELD]),
    )


def augment_commit(request: Any) -> tuple[Any, int]:
    writes = (request.get('writes') if isinstance(request, dict) else request.writes) or ()
    count = len(writes)
    tokens = authority_tokens(writes)
    if not tokens:
        return request, count
    prepared = CommitRequest(request)
    # Appending after source writes also handles authority field updates.
    # Authority deletion is rejected above; account-subtree erasure retains it.
    # The final token is unique after source wipe/recreation;
    # no generation, blocked or purging field is changed by this masked write.
    prepared.writes.extend(token_write(path) for path in sorted(tokens))
    # Preserve expanded atomic batches. The installed list-projection writer
    # already emits >500 writes in a Commit (covered by emulator tests). The
    # server owns request-size/transaction limits; never split the request or
    # drop a token to fit, and propagate any rejection to the caller.
    return prepared, count


def _wrap_commit(original: Any) -> Any:
    if getattr(original, '_omi_batch_privacy_fence', False):
        return original

    def prepare(request, kwargs):
        fields = {key: kwargs.pop(key) for key in ('database', 'writes', 'transaction') if key in kwargs}
        if request is not None and any(value is not None for value in fields.values()):
            raise ValueError('request and flattened commit fields cannot both be supplied')
        return augment_commit(request if request is not None else fields)

    def response(value, count):
        if len(value.write_results) == count:
            return value
        result = CommitResponse(value)
        del result.write_results[count:]
        return result

    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def async_wrapped(client, request=None, **kwargs):
            prepared, count = prepare(request, kwargs)
            return response(await original(client, request=prepared, **kwargs), count)

        wrapped = async_wrapped

    else:

        @functools.wraps(original)
        def sync_wrapped(client, request=None, **kwargs):
            prepared, count = prepare(request, kwargs)
            return response(original(client, request=prepared, **kwargs), count)

        wrapped = sync_wrapped

    setattr(wrapped, '_omi_batch_privacy_fence', True)
    return wrapped


def _bulk_parts(request, kwargs):
    fields = {key: kwargs.pop(key) for key in ('database', 'writes', 'labels') if key in kwargs}
    if request is not None and any(value is not None for value in fields.values()):
        raise ValueError('request and flattened batch-write fields cannot both be supplied')
    supplied = request if request is not None else fields
    prepared = BatchWriteRequest(supplied)
    # BatchWrite is non-atomic and forbids duplicate documents. Relevant writes
    # become independent atomic Commits, each containing its own fence. Unrelated
    # writes retain BatchWrite, its labels and its per-write status semantics.
    indices = [i for i, write in enumerate(prepared.writes) if authority_tokens([write])]
    return supplied, prepared, indices


def _bulk_failure(error):
    code = error.grpc_status_code
    if code is None:
        raise error
    return Status(code=code.value[0], message=str(error))


def _wrap_bulk(original: Any) -> Any:
    if getattr(original, '_omi_batch_privacy_fence', False):
        return original

    def finish(prepared, indices, individual, rest):
        result = BatchWriteResponse()
        cursor = 0
        for i in range(len(prepared.writes)):
            if i in individual:
                write_result, status = individual[i]
            else:
                write_result, status = rest.write_results[cursor], rest.status[cursor]
                cursor += 1
            result.write_results.append(write_result)
            result.status.append(status)
        return result

    def remainder(prepared, indices):
        return BatchWriteRequest(
            database=prepared.database,
            labels=prepared.labels,
            writes=[write for i, write in enumerate(prepared.writes) if i not in indices],
        )

    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def async_wrapped(client, request=None, **kwargs):
            supplied, prepared, indices = _bulk_parts(request, kwargs)
            if not indices:
                return await original(client, request=supplied, **kwargs)
            if prepared.labels:
                # Commit has no labels field. Refuse before any writes rather
                # than silently lose a caller's billing attribution.
                raise ValueError('labeled batch privacy bulk writes require atomic Commit migration')
            individual = {}
            for i in indices:
                try:
                    response = await client.commit(
                        request=CommitRequest(database=prepared.database, writes=[prepared.writes[i]]), **kwargs
                    )
                    individual[i] = (response.write_results[0], Status())
                except GoogleAPICallError as error:
                    individual[i] = (WriteResult(), _bulk_failure(error))
            pending = remainder(prepared, indices)
            rest = await original(client, request=pending, **kwargs) if pending.writes else None
            return finish(prepared, indices, individual, rest)

        wrapped = async_wrapped

    else:

        @functools.wraps(original)
        def sync_wrapped(client, request=None, **kwargs):
            supplied, prepared, indices = _bulk_parts(request, kwargs)
            if not indices:
                return original(client, request=supplied, **kwargs)
            if prepared.labels:
                raise ValueError('labeled batch privacy bulk writes require atomic Commit migration')
            individual = {}
            for i in indices:
                try:
                    response = client.commit(
                        request=CommitRequest(database=prepared.database, writes=[prepared.writes[i]]), **kwargs
                    )
                    individual[i] = (response.write_results[0], Status())
                except GoogleAPICallError as error:
                    individual[i] = (WriteResult(), _bulk_failure(error))
            pending = remainder(prepared, indices)
            rest = original(client, request=pending, **kwargs) if pending.writes else None
            return finish(prepared, indices, individual, rest)

        wrapped = sync_wrapped

    setattr(wrapped, '_omi_batch_privacy_fence', True)
    return wrapped


def install_write_fence() -> None:
    for cls in (FirestoreClient, FirestoreAsyncClient):
        cls.commit = _wrap_commit(cls.commit)
        cls.batch_write = _wrap_bulk(cls.batch_write)
