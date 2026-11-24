"""No-I/O Home projection coverage fence at the existing atomic Commit boundary.

Content remains on owning documents. episode_links contains content-free dirty
receipts so explicit preparation can reconcile hard deletes without scanning
history. Result positions and source preconditions belong to the existing fence.
"""

from uuid import uuid4
from contextvars import ContextVar
from contextlib import contextmanager
import inspect
from functools import wraps
from database.batch_account_authority_schema import USER_POLICY_FIELDS

from database.home_feed_fields import LIST_TRANSCRIPT, LIST_TRANSCRIPT_SOURCE_VERSION as LIST_SOURCE_VERSION
from google.cloud.firestore_v1.types import Document, DocumentMask, Value, Write

_ERASING_ROOTS: ContextVar[frozenset[str]] = ContextVar("home_feed_erasing_roots", default=frozenset())

_ERASING: ContextVar[frozenset[str]] = ContextVar("home_feed_erasing_owner", default=frozenset())


def suppress_during_account_erasure(fn):
    @wraps(fn)
    def wrapped(uid, *args, **kwargs):
        token = _ERASING.set(_ERASING.get() | {uid})
        try:
            return fn(uid, *args, **kwargs)
        finally:
            _ERASING.reset(token)

    return wrapped


CONTROL = 'home_feed_control'
SCHEMA = 1
# Metadata progress does not remove source text or change feed ownership.
SAFE_FIELDS = frozenset(
    {
        'updated_at',
        'last_speech_at',
        'last_activity_at',
        'member_activity',
        'processing_admitted_at',
        'processing_heartbeat_at',
        'postprocessing',
        'playback_eager_epoch',
        'audio_files',
        'audio_url',
        'audio_base64_url',
        'record_upload_sessions',
        'share_email_recipients',
        'share_email_in_flight',
        'external_data',
        'summary_due_at',
        'v3_live_title_state',
    }
)


def _parts(write):
    path = write.delete or write.update.name or write.transform.document
    parts = path.split('/')
    return parts if len(parts) == 9 and parts[4:6] == ['documents', 'users'] else []


def _policy_owner(write):
    path = write.delete or write.update.name or write.transform.document
    parts = path.split('/')
    if len(parts) < 7 or parts[4:6] != ['documents', 'users']:
        return None
    if len(parts) == 9 and parts[7] in {'subscriptions', 'privacy'}:
        return '/'.join(parts[:7])
    roots = {p.split('.', 1)[0].strip('`') for p in write.update_mask.field_paths}
    roots.update(t.field_path.split('.', 1)[0] for t in write.update_transforms)
    if (
        len(parts) == 7
        and not write.delete
        and (not Write.pb(write).HasField('update_mask') or roots.intersection(USER_POLICY_FIELDS))
    ):
        return '/'.join(parts[:7])
    return None


def affects_home(write):
    write = Write(write) if isinstance(write, dict) else write
    if _policy_owner(write):
        return True
    parts = _parts(write)
    if not parts or parts[7] not in {'conversations', 'episodes', 'deleted_conversations'}:
        return False
    if write.delete or not Write.pb(write).HasField('update_mask'):
        return True
    fields = {p.split('.', 1)[0].strip('`') for p in write.update_mask.field_paths}
    fields.update(t.field_path.split('.', 1)[0] for t in write.update_transforms)
    additive = write.update.fields.get('home_append_only')
    if (
        additive is not None
        and additive.boolean_value
        and not fields.intersection(
            {
                'structured',
                'deleted',
                'discarded',
                'is_locked',
                'sync_merged_into',
                'dream_duplicate_of',
                'episode_id',
                'user_title',
                'relevance_decision',
                'status',
                'user_corrections',
                'sync_relevance_user_kept',
                'folder_user_set',
                'has_photos',
                'sync_bridge_pending',
            }
        )
    ):
        return False
    # Preparation only changes home_* fields, atomically with its control CAS.
    return any(not p.startswith('home_') and p not in SAFE_FIELDS for p in fields)


def _patch(path, values):
    return Write(update=Document(name=path, fields=values), update_mask=DocumentMask(field_paths=list(values)))


def augment_home_writes(writes):
    writes = [Write(write) if isinstance(write, dict) else write for write in writes]
    additions, owners, policy_owners = [], set(), set()
    deleted_owners = {write.delete for write in writes if write.delete and len(write.delete.split('/')) == 7}
    for index, write in enumerate(writes):
        policy_owner = _policy_owner(write)
        if (
            policy_owner
            and policy_owner not in deleted_owners
            and policy_owner not in _ERASING_ROOTS.get()
            and policy_owner.split('/')[6] not in _ERASING.get()
        ):
            owners.add(policy_owner)
            policy_owners.add(policy_owner)
        parts = _parts(write)
        if not affects_home(write):
            # Append-only writes bypass Home invalidation, but can change
            # transcript-derived speech, duration and previews.
            if parts and parts[7] == 'conversations' and write.update.name:
                paths = write.update_mask.field_paths
                if any(p.split('.', 1)[0].strip('`') == 'transcript_segments' for p in paths):
                    prepared = Write(write)
                    for field in (LIST_TRANSCRIPT, LIST_SOURCE_VERSION):
                        prepared.update.fields.pop(field, None)
                        if field not in prepared.update_mask.field_paths:
                            prepared.update_mask.field_paths.append(field)
                    writes[index] = prepared
            continue
        if not parts or parts[7] not in {'conversations', 'episodes', 'deleted_conversations'}:
            continue
        owner = '/'.join(parts[:7])
        if owner in deleted_owners or owner in _ERASING_ROOTS.get() or parts[6] in _ERASING.get():
            continue
        owners.add(owner)
        values = {}
        if parts[7] == 'episodes':
            if write.delete:
                policy_owners.add(owner)
            else:
                values = {
                    'home_needs_prepare': Value(boolean_value=True),
                    'home_content_epoch': Value(string_value=uuid4().hex),
                }
        elif parts[7] == 'conversations' and not write.delete:
            paths = (
                list(write.update_mask.field_paths)
                + [t.field_path for t in write.update_transforms]
                + [t.field_path for t in write.transform.field_transforms]
            )
            roots = {p.split('.', 1)[0].strip('`') for p in paths} | set(write.update.fields)
            values = {'home_source_version': Value(string_value=uuid4().hex)}
            if (
                'transcript_segments' in write.update.fields
                and LIST_TRANSCRIPT in write.update.fields
                and write.update.fields[LIST_TRANSCRIPT].string_value
            ):
                values[LIST_SOURCE_VERSION] = values['home_source_version']
            if {'transcript_segments', 'user_corrections'}.intersection(roots):
                values['home_content_invalidated'] = Value(boolean_value='structured' not in roots)
        if values:
            transformed = {t.field_path for t in write.update_transforms}
            if write.update.name and not transformed.intersection(values):
                # Copy; the caller's request, precondition and result slot are
                # preserved. Metadata joins the original source write rather
                # than billing a second update of the same document.
                prepared = Write(write)
                prepared.update.fields.update(values)
                if parts[7] == 'conversations' and LIST_SOURCE_VERSION not in values:
                    for field in (LIST_TRANSCRIPT, LIST_SOURCE_VERSION):
                        prepared.update.fields.pop(field, None)
                        if Write.pb(write).HasField('update_mask') and field not in prepared.update_mask.field_paths:
                            prepared.update_mask.field_paths.append(field)
                if Write.pb(write).HasField('update_mask'):
                    prepared.update_mask.field_paths.extend(
                        key for key in values if key not in prepared.update_mask.field_paths
                    )
                writes[index] = prepared
            else:
                additions.append(_patch('/'.join(parts), values))
        if parts[7] != 'episodes':
            # These receipts survive deletion, have no content and are consumed
            # by explicit POST preparation. The authoritative ownership link is
            # preserved even when the source and link are written together.
            additions.append(_patch(f'{owner}/episode_links/{parts[8]}', {'home_dirty': Value(boolean_value=True)}))
    for owner in sorted(owners):
        values = {'ready': Value(boolean_value=False), 'generation': Value(string_value=uuid4().hex)}
        if owner in policy_owners:
            values.update(policy_dirty=Value(boolean_value=True), policy_epoch=Value(string_value=uuid4().hex))
        additions.append(_patch(f'{owner}/episode_links/{CONTROL}', values))
    return [*writes, *additions]


@contextmanager
def _bulk_erasure_scope(request, kwargs):
    writes = (
        (request.get('writes') if isinstance(request, dict) else request.writes)
        if request is not None
        else kwargs.get('writes', ())
    )
    owners = {
        write.delete
        for raw in writes or ()
        if (write := Write(raw)).delete and len(write.delete.split('/')) == 7 and write.delete.split('/')[5] == 'users'
    }
    token = _ERASING_ROOTS.set(_ERASING_ROOTS.get() | owners)
    try:
        yield
    finally:
        _ERASING_ROOTS.reset(token)


def bulk_erasure_scope(fn):
    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def asynchronous(client, request=None, **kwargs):
            with _bulk_erasure_scope(request, kwargs):
                return await fn(client, request=request, **kwargs)

        return asynchronous

    @wraps(fn)
    def synchronous(client, request=None, **kwargs):
        with _bulk_erasure_scope(request, kwargs):
            return fn(client, request=request, **kwargs)

    return synchronous
