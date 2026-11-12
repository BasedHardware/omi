"""Atomic, write-maintained list rows and opaque owner versions.

The rows are a migration substrate, NOT a replacement for source queries: a
partial update of a legacy source cannot establish complete row coverage.
Only Commit (not non-atomic BatchWrite) may publish a usable owner version.
No clients, reads, decryption, or network operations run while preparing writes.
"""

import functools
import inspect
from typing import Any
from uuid import uuid4

from google.cloud.firestore_v1.base_document import BaseDocumentReference
from google.cloud.firestore_v1.batch import WriteBatch
from google.cloud.firestore_v1.async_batch import AsyncWriteBatch
from google.cloud.firestore_v1.transaction import Transaction
from google.cloud.firestore_v1.async_transaction import AsyncTransaction
from google.cloud.firestore_v1.types import Document, DocumentMask, Value, Write

from config.list_projection import ROW_COLLECTIONS, STATE_COLLECTION, writer_enabled

# Deliberately content-free migration rows. The source remains the owner of
# titles/descriptions/transcripts and every authorization/visibility decision.
# Coverage is per field: an update must never label a partial legacy row ready.
ROW_FIELDS = frozenset(
    {
        'created_at',
        'updated_at',
        'started_at',
        'finished_at',
        'status',
        'discarded',
        'deleted',
        'sync_merged_into',
        'dream_duplicate_of',
        'is_locked',
        'folder_id',
        'folder_user_set',
        'starred',
        'source',
        'completed',
        'completed_at',
        'due_at',
        'sort_order',
        'indent_level',
        'conversation_id',
        'goal_id',
        'workstream_id',
        'superseded_by',
    }
)

# Exact fields written by users.record_user_platform. They do not participate
# in list authorization or representation. Unknown root fields still invalidate
# both families, as do full replacements and deletes (which can remove fences).
_PLATFORM_TELEMETRY_FIELDS = frozenset(
    {
        'last_active_platform',
        'last_active_os',
        'last_active_at',
        'last_active_at_desktop',
        'last_active_at_mobile',
        'last_active_at_web',
        'platforms_used',
        'signup_platform',
        'signup_os',
        'signup_platform_at',
    }
)


def _root_affects_lists(write: Any) -> bool:
    if write.delete:
        return True
    if write.transform.document:
        paths = {transform.field_path for transform in write.transform.field_transforms}
    elif Write.pb(write).HasField('update_mask'):
        paths = set(write.update_mask.field_paths)
        paths.update(transform.field_path for transform in write.update_transforms)
    else:
        return True
    return not paths or not paths.issubset(_PLATFORM_TELEMETRY_FIELDS)


def _path(write: Any) -> str:
    return write.delete or write.update.name or write.transform.document


def _row_write(write: Any, parts: list[str]) -> Write | None:
    """Copy a small metadata field mask without replaying source preconditions."""
    family = parts[7]
    name = '/'.join(parts[:7] + [ROW_COLLECTIONS[family], parts[8]])
    if write.delete:
        return Write(delete=name)
    if write.transform.document:
        transforms = [t for t in write.transform.field_transforms if t.field_path in ROW_FIELDS]
        if not transforms:
            return None
        return Write(update=Document(name=name), update_mask=DocumentMask(field_paths=[]), update_transforms=transforms)
    fields = {key: value for key, value in write.update.fields.items() if key in ROW_FIELDS}
    # A mask is present for merge/update, absent for full replacement. Keep
    # deletions in the mask even though the field is absent from the payload.
    has_mask = Write.pb(write).HasField('update_mask')
    mask = [path for path in write.update_mask.field_paths if path in ROW_FIELDS]
    transforms = [t for t in write.update_transforms if t.field_path in ROW_FIELDS]
    if has_mask and not mask and not transforms:
        return None
    result = Write(update=Document(name=name, fields=fields), update_transforms=transforms)
    if has_mask:
        result.update_mask = DocumentMask(field_paths=mask)
    return result


def project_writes(writes: list[Any]) -> list[Any]:
    """Append rows and one random version per owner/family, in the SAME commit.

    Never alter source writes, preconditions, masks, transforms, or their order.
    Random versions prevent ABA after account wipe/recreation and commit retry.
    """
    if not writer_enabled():
        return writes
    additions = []
    owners: set[tuple[str, str]] = set()
    deleted_owners: set[str] = set()
    for write in writes:
        parts = _path(write).split('/')
        if len(parts) < 7 or parts[4:6] != ['documents', 'users']:
            continue
        owner = '/'.join(parts[:7])
        if len(parts) == 7 and write.delete:
            deleted_owners.add(owner)
        if len(parts) >= 9 and parts[7] in ROW_COLLECTIONS:
            owners.add((owner, parts[7]))
            row = _row_write(write, parts) if len(parts) == 9 else None
            if row is not None:
                additions.append(row)
        # Account/entitlement/privacy changes and deletion intent invalidate
        # both lists. No authorization fence is replaced by these versions.
        elif (len(parts) == 7 and _root_affects_lists(write)) or (
            len(parts) >= 9
            and parts[7]
            in {
                'deleted_conversations',
                'subscriptions',
                'privacy',
                'task_intelligence_control',
            }
        ):
            owners.update((owner, family) for family in ROW_COLLECTIONS)
    for owner, family in sorted(owners):
        if owner in deleted_owners:
            additions.append(Write(delete=f'{owner}/{STATE_COLLECTION}/{family}'))
            continue
        additions.append(
            Write(
                update=Document(
                    name=f'{owner}/{STATE_COLLECTION}/{family}',
                    fields={'version': Value(string_value=uuid4().hex)},
                )
            )
        )
    return [*writes, *additions] if additions else writes


def _wrap_commit(original: Any) -> Any:
    if getattr(original, '_omi_list_projection', False):
        return original
    wrapped: Any

    def prepare(batch: Any) -> tuple[list[Any], int]:
        source = batch._write_pbs
        batch._write_pbs = project_writes(source)
        return source, len(source)

    def restore(batch: Any, source: list[Any], size: int, succeeded: bool) -> None:
        if not succeeded:
            batch._write_pbs = source
        elif getattr(batch, 'write_results', None) is not None:
            batch.write_results = batch.write_results[:size]

    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def async_commit(batch: Any, *args: Any, **kwargs: Any) -> Any:
            source, size = prepare(batch)
            succeeded = False
            try:
                result = await original(batch, *args, **kwargs)
                succeeded = True
                return result[:size]
            finally:
                restore(batch, source, size, succeeded)

        wrapped = async_commit
    else:

        @functools.wraps(original)
        def sync_commit(batch: Any, *args: Any, **kwargs: Any) -> Any:
            source, size = prepare(batch)
            succeeded = False
            try:
                result = original(batch, *args, **kwargs)
                succeeded = True
                return result[:size]
            finally:
                restore(batch, source, size, succeeded)

        wrapped = sync_commit
    setattr(wrapped, '_omi_list_projection', True)
    return wrapped


def _wrap_delete(original: Any) -> Any:
    if getattr(original, '_omi_list_projection', False):
        return original

    @functools.wraps(original)
    def prepare(reference: Any, *args: Any, **kwargs: Any) -> Any:
        request, options = original(reference, *args, **kwargs)
        request['writes'] = project_writes(request['writes'])
        return request, options

    setattr(prepare, '_omi_list_projection', True)
    return prepare


def install_list_projection_writer() -> None:
    for cls, method in (
        (WriteBatch, 'commit'),
        (AsyncWriteBatch, 'commit'),
        (Transaction, '_commit'),
        (AsyncTransaction, '_commit'),
    ):
        setattr(cls, method, _wrap_commit(getattr(cls, method)))
    # Shared by sync and async DocumentReference.delete, which bypass batches.
    setattr(BaseDocumentReference, '_prep_delete', _wrap_delete(getattr(BaseDocumentReference, '_prep_delete')))
