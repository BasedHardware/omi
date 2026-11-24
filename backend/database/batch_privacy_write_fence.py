"""Atomic batch-privacy invalidation at the Firestore Commit boundary.

The opaque token is independent of the admission/erasure generation. No reads,
credentials or clients are needed to prepare it. Source preconditions and result
positions are preserved. Install in every writer process before enabling readers.
"""

import functools
import hashlib
import inspect
import os
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
    Precondition,
    Value,
    Write,
    WriteResult,
)
from google.rpc import status_pb2
from database.batch_account_authority_schema import (
    ACCOUNT_DELETION_COLLECTION,
    ACCOUNT_EPOCH,
    ACCOUNT_FIELD_GROUPS,
    ACCOUNT_HEAD,
    ACCOUNT_OPERATIONS,
    ACCOUNT_STATE_COLLECTION,
    PRIVACY_COLLECTION,
    USER_POLICY_FIELDS,
)
from database.home_feed_writer import augment_home_writes, affects_home, bulk_erasure_scope
from database.batch_privacy_attempt import CONVERSATION_AUTHORITY_FIELDS, TOKEN_FIELD, SCHEMA_FIELD, TOKEN_SCHEMA

# Protobuf builds this class dynamically; the installed module has no typed declaration.
Status = cast(Any, status_pb2).Status

_ROOT_AUTHORITIES = frozenset({ACCOUNT_DELETION_COLLECTION, 'legal_holds', 'legal_hold_deletion_gates'})
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
            if family == 'users' and len(parts) == 7 and not _changes_answer(write, USER_POLICY_FIELDS):
                continue
            if family == 'users' and len(parts) == 9 and parts[7] == 'conversations':
                if not _changes_answer(write, _CONVERSATION_FIELDS):
                    continue
            key = hashlib.sha256(owner.encode()).hexdigest()
            tokens.add(f'{root}/{PRIVACY_COLLECTION}/{key}')
    return tokens


def _write_path(write: Write) -> str:
    return write.delete or write.update.name or write.transform.document


def _account_write_group(write: Write, family: str) -> str | None:
    if write.delete or write.update.name and not Write.pb(write).HasField('update_mask'):
        return 'existence'
    groups = ACCOUNT_FIELD_GROUPS[family]
    paths = (
        list(write.update_mask.field_paths)
        + [item.field_path for item in write.update_transforms]
        + [item.field_path for item in write.transform.field_transforms]
    )
    # The SDK emits escaped paths. Classify the top-level root, including
    # transform-only writes and a masked field deletion (no update value).
    affected = {groups.get(_authority_path(path)[0]) for path in paths} - {None}
    if len(affected) > 1:
        return 'protection_and_sync'
    if affected:
        return next(iter(affected))
    if not (write.current_document.exists or write.current_document.update_time):
        return 'existence'
    return None


def _written_epoch(write: Write, path: str, *, create: bool = False) -> int | None:
    if write.update.name != path or write.update_transforms:
        return None
    current = write.current_document
    creates_document = Precondition.pb(current).WhichOneof('condition_type') == 'exists' and not current.exists
    if (create and not creates_document) or (
        not creates_document and ACCOUNT_EPOCH not in write.update_mask.field_paths
    ):
        return None
    value = write.update.fields.get(ACCOUNT_EPOCH)
    if value is None or Value.pb(value).WhichOneof('value_type') != 'integer_value' or value.integer_value < 1:
        return None
    return value.integer_value


def account_write_observations(request: Any) -> list[tuple[str, str, bool]]:
    """Observe the primitive's source, owner patch, durable head and create receipt.

    A legacy generation update, a receipt for a different owner or a second raw
    write to the same account cannot certify the classified source write.
    """
    raw_writes = request.get('writes') if isinstance(request, dict) else request.writes
    transaction = request.get('transaction') if isinstance(request, dict) else request.transaction
    writes = [Write(raw) if isinstance(raw, dict) else raw for raw in raw_writes or ()]
    observations = []
    for index, write in enumerate(writes):
        parts = _write_path(write).split('/')
        if len(parts) != 7 or parts[0] != 'projects' or parts[2] != 'databases' or parts[4] != 'documents':
            continue
        family, uid = parts[5:]
        if family not in ACCOUNT_FIELD_GROUPS:
            continue
        group = _account_write_group(write, family)
        if group is None:
            continue
        certified = False
        if transaction and index + 3 < len(writes):
            key = hashlib.sha256(uid.encode()).hexdigest()
            owner = '/'.join([*parts[:5], PRIVACY_COLLECTION, key])
            stamp, head, receipt = writes[index + 1 : index + 4]
            receipt_path = _write_path(receipt)
            receipt_prefix = f'{owner}/{ACCOUNT_OPERATIONS}/'
            receipt_id = receipt_path.removeprefix(receipt_prefix)
            epoch = _written_epoch(stamp, owner)
            certified = (
                epoch is not None
                and _written_epoch(head, f'{owner}/{ACCOUNT_STATE_COLLECTION}/{ACCOUNT_HEAD}') == epoch
                and receipt_path.startswith(receipt_prefix)
                and len(receipt_id) == 64
                and all(char in '0123456789abcdef' for char in receipt_id)
                and _written_epoch(receipt, receipt_path, create=True) == epoch
            )
        observations.append((family, group, certified))
    return observations


def _observe_account_writes(request: Any) -> None:
    # Observation must not turn a successful Commit into a caller-visible
    # failure. No client, authority read or identifier enters the metric.
    try:
        observations = account_write_observations(request)
        if observations:
            from database.privacy_check_metrics import ACCOUNT_AUTHORITY_WRITES

            for family, group, certified in observations:
                ACCOUNT_AUTHORITY_WRITES.labels(family, group, 'true' if certified else 'false').inc()
    except Exception:
        pass


def token_write(path: str) -> Write:
    return Write(
        update=Document(
            name=path,
            fields={TOKEN_FIELD: Value(string_value=uuid4().hex), SCHEMA_FIELD: Value(integer_value=TOKEN_SCHEMA)},
        ),
        update_mask=DocumentMask(field_paths=[TOKEN_FIELD, SCHEMA_FIELD]),
    )


def augment_commit(request: Any, *, tokens_out: set[str] | None = None) -> tuple[Any, int]:
    writes = (request.get('writes') if isinstance(request, dict) else request.writes) or ()
    count = len(writes)
    home_writes = augment_home_writes(writes)
    tokens = authority_tokens(writes)
    if tokens_out is not None:
        tokens_out.update(tokens)
    if not tokens and len(home_writes) == count:
        return request, count
    prepared = CommitRequest(request)
    del prepared.writes[:]
    prepared.writes.extend(home_writes)
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


def _invalidate_tokenless(tokens: set[str]) -> None:
    # The Firestore Commit has already succeeded. Cache failures cannot change
    # its outcome; the absolute precheck deadline bounds an uncertain delivery.
    try:
        from database.batch_privacy_tokenless import invalidate

        invalidate(tokens)
    except Exception:
        pass


def _wrap_commit(original: Any) -> Any:
    if getattr(original, '_omi_batch_privacy_fence', False):
        return original

    def prepare(request, kwargs):
        fields = {key: kwargs.pop(key) for key in ('database', 'writes', 'transaction') if key in kwargs}
        if request is not None and any(value is not None for value in fields.values()):
            raise ValueError('request and flattened commit fields cannot both be supplied')
        source = request if request is not None else fields
        tokens: set[str] = set()
        prepared, count = augment_commit(source, tokens_out=tokens)
        return prepared, count, source, tokens

    def response(value, count):
        if len(value.write_results) == count:
            return value
        result = CommitResponse(value)
        del result.write_results[count:]
        return result

    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def async_wrapped(client, request=None, **kwargs):
            prepared, count, source, tokens = prepare(request, kwargs)
            result = await original(client, request=prepared, **kwargs)
            if tokens and os.getenv('REDIS_DB_HOST') and not os.getenv('FIRESTORE_EMULATOR_HOST'):
                from utils.executors import db_executor, run_blocking

                try:
                    await run_blocking(db_executor, _invalidate_tokenless, tokens)
                except Exception:
                    pass
            _observe_account_writes(source)
            return response(result, count)

        wrapped = async_wrapped

    else:

        @functools.wraps(original)
        def sync_wrapped(client, request=None, **kwargs):
            prepared, count, source, tokens = prepare(request, kwargs)
            result = original(client, request=prepared, **kwargs)
            if tokens and os.getenv('REDIS_DB_HOST') and not os.getenv('FIRESTORE_EMULATOR_HOST'):
                _invalidate_tokenless(tokens)
            _observe_account_writes(source)
            return response(result, count)

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
    indices = [i for i, write in enumerate(prepared.writes) if authority_tokens([write]) or affects_home(write)]
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

    wrapped = bulk_erasure_scope(wrapped)
    setattr(wrapped, '_omi_batch_privacy_fence', True)
    return wrapped


def install_write_fence() -> None:
    for cls in (FirestoreClient, FirestoreAsyncClient):
        cls.commit = _wrap_commit(cls.commit)
        cls.batch_write = _wrap_bulk(cls.batch_write)
