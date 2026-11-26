"""Drain durable post-window artifact erasure under the account legal-hold gate."""

from datetime import datetime, timedelta, timezone
import logging
import os
import re
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud import firestore

from database import legal_holds, rpc_deadline
from database._client import get_data_plane_firestore_client
from database.batch_account_authority_schema import ACCOUNT_DELETION_COLLECTION
from database.batch_pipeline_conversation_purge import purge_cursor
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_privacy_queries import owner_documents
from database.batch_pipeline_purge import NAMESPACES
from database.batch_pipeline_shadow_hook import purge_owner
from database.batch_privacy_late_intents import COLLECTION, DELAY
from database.privacy_check_metrics import POST_WINDOW_OPERATIONS, POST_WINDOW_SWEEPS
from utils.batch_pipeline.retention import BATCH_OBJECT_BUCKET_ENV, batch_object_address, delete_batch_object
from utils.other.local_storage import create_storage_client

logger = logging.getLogger(__name__)
GATE_KIND = 'explicit_memory_deletion'
REASONS = frozenset({'account_deleted', 'data_protection', 'recording_policy'})
RETRY = timedelta(minutes=5)
HOLD_RETRY = timedelta(hours=1)
PAGE_RETRY = timedelta(seconds=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def due_jobs(*, now: datetime, limit: int, firestore_client: Any = None) -> list:
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    return list(
        client.collection(COLLECTION)
        .where(filter=firestore.FieldFilter('due_at', '<=', now))
        .order_by('due_at')
        .limit(limit)
        .stream()
    )


def _matches(snapshot, data, uid, reason, source, changed_at):
    if data.get('owner_id') != uid or not data.get('uri'):
        return False
    if reason == 'account_deleted':
        # A completed, irreversible wipe owes all remnants of this account.
        return True
    pending = data.get('write_pending_until')
    # Registration happens before cloud IO. A still-open reservation at the
    # change may have landed an object after the first erasure passed its key.
    if not (
        isinstance(pending, datetime)
        and isinstance(snapshot.create_time, datetime)
        and snapshot.create_time <= changed_at <= pending
    ):
        return False
    if reason == 'data_protection':
        return True
    # A legacy reservation can predate both provenance stamping and job admission.
    return data.get('record_origin') is not False and (not source or source in (data.get('conversation_ids') or ()))


def _account_is_erased(client, uid, transaction):
    marker = client.collection(ACCOUNT_DELETION_COLLECTION).document(uid).get(transaction=transaction)
    user = client.collection('users').document(uid).get(transaction=transaction)
    return (marker.to_dict() or {}).get('wipe_status') == 'completed' and not user.exists


def _pin(uid, data, storage):
    uri = data['uri']
    allowed = {value for name in BATCH_OBJECT_BUCKET_ENV if (value := os.getenv(name, '').strip())}
    bucket_name, path, generation = batch_object_address(uid, uri, allowed)
    if generation is None:
        # These upload reservations own a create-only, attempt-scoped object
        # name. An unversioned reference outside that contract proves nothing.
        kind = data.get('kind')
        segment = data.get('segment_id')
        if (
            kind not in {'audio', 'result', 'results', 'voice_evidence'}
            or not isinstance(segment, str)
            or path.rsplit('/', 3)[-3:-1] != [kind, segment]
            or not re.fullmatch(r'[a-f0-9]{32}\.enc', path.rsplit('/', 1)[-1])
        ):
            raise ValueError('late erasure requires an immutable artifact identity')
        blob = storage.bucket(bucket_name).blob(path)
        try:
            blob.reload(timeout=5, retry=None)
        except NotFound:
            return None
        generation = int(blob.generation or 0)
    if generation <= 0:
        raise ValueError('late erasure requires a pinned storage generation')
    return f'gs://{bucket_name}/{path}#{generation}'


def _settle(client, uid):
    stuck = legal_holds.stuck_remote_erasure(uid, kind=GATE_KIND, firestore_client=client)
    if stuck is None:
        return
    token, target = stuck
    # Leave other gate owners' recovery to their existing consumers.
    if not target.startswith('late-batch:'):
        return
    namespace, _, uri = target.removeprefix('late-batch:').partition(':')
    if namespace not in NAMESPACES:
        return
    call = (lambda: delete_batch_object(uid, uri, timeout=5)) if uri else (lambda: purge_owner(namespace, uid))
    if legal_holds.settles_unknown_erasure(call):
        legal_holds.settle_stuck_remote_erasure(uid, kind=GATE_KIND, token=token, firestore_client=client)


def _authorize(client, reference, authority, uid, reason, event, artifact=None):
    @firestore.transactional
    def read(transaction):
        authority.fence(transaction)
        latest = reference.get(transaction=transaction)
        if not latest.exists or latest.update_time != event.update_time:
            return 'changed'
        if reason == 'account_deleted' and not _account_is_erased(client, uid, transaction):
            return 'superseded'
        if artifact is not None:
            current = artifact.reference.get(transaction=transaction)
            if not current.exists or current.update_time != artifact.update_time:
                return 'changed'
        return 'ready'

    return read(client.transaction())


def _advance(client, reference, authority, event, uid, reason, changes, *, artifact=None, complete=False):
    @firestore.transactional
    def apply(transaction):
        authority.fence(transaction)
        latest = reference.get(transaction=transaction)
        if not latest.exists or latest.update_time != event.update_time:
            return False
        if reason == 'account_deleted' and not _account_is_erased(client, uid, transaction):
            if complete and artifact is None:
                transaction.delete(reference)
                return True
            return False
        if artifact is not None:
            current = artifact.reference.get(transaction=transaction)
            if not current.exists or current.update_time != artifact.update_time:
                return False
            transaction.delete(artifact.reference)
        if complete:
            transaction.delete(reference)
        else:
            transaction.update(reference, changes)
        return True

    return apply(client.transaction())


def _run(client, event, now):
    data = event.to_dict() or {}
    uid, reason, changed_at = data['uid'], data['reason'], data['changed_at']
    if reason not in REASONS or not isinstance(changed_at, datetime):
        raise ValueError('malformed late sweep intent')
    key = privacy_owner_key(uid)
    if changed_at + DELAY > now:
        event.reference.update({'due_at': changed_at + DELAY}, option=firestore.LastUpdateOption(event.update_time))
        return 'early'
    index = int(data.get('namespace_index', 0))
    source = data.get('conversation_id') or ''
    _settle(client, uid)
    with legal_holds.bounded_destructive_unit(uid, kind=GATE_KIND, firestore_client=client) as authority:
        status = _authorize(client, event.reference, authority, uid, reason, event)
        if status == 'superseded':
            _advance(client, event.reference, authority, event, uid, reason, {}, complete=True)
            return status
        if status != 'ready':
            return status
        if index >= len(NAMESPACES):
            if _advance(client, event.reference, authority, event, uid, reason, {}, complete=True):
                POST_WINDOW_SWEEPS.labels(reason).inc()
                return 'completed'
            return 'changed'

        namespace = NAMESPACES[index]
        page = owner_documents(
            client, namespace, 'artifacts', key, after=purge_cursor(client, namespace, 'artifacts', data.get('after'))
        )
        for snapshot in page:
            receipt = snapshot.to_dict() or {}
            if not _matches(snapshot, receipt, uid, reason, source, changed_at):
                continue
            pending = receipt.get('write_pending_until')
            if isinstance(pending, datetime) and pending > now:
                _advance(client, event.reference, authority, event, uid, reason, {'due_at': pending + PAGE_RETRY})
                return 'waiting_for_upload'
            if _authorize(client, event.reference, authority, uid, reason, event, artifact=snapshot) != 'ready':
                return 'changed'
            storage = rpc_deadline.bind_storage_client(create_storage_client())
            if uri := _pin(uid, receipt, storage):
                authority.remote(
                    lambda: delete_batch_object(uid, uri, timeout=5, storage_client=storage),
                    target=f'late-batch:{namespace}:{uri}',
                )
                POST_WINDOW_OPERATIONS.labels(reason, 'object_storage').inc()
            changes = {'after': snapshot.id, 'needs_postgres': True, 'due_at': now + PAGE_RETRY}
            if _advance(client, event.reference, authority, event, uid, reason, changes, artifact=snapshot):
                POST_WINDOW_OPERATIONS.labels(reason, 'firestore').inc()
            return 'progress'

        if page:
            changes = {'after': page[-1].id, 'due_at': now + PAGE_RETRY}
        else:
            if data.get('needs_postgres') or reason == 'account_deleted':
                rows = authority.remote(lambda: purge_owner(namespace, uid), target=f'late-batch:{namespace}')
                POST_WINDOW_OPERATIONS.labels(reason, 'postgres').inc(rows)
            changes = {'namespace_index': index + 1, 'after': None, 'needs_postgres': False, 'due_at': now + PAGE_RETRY}
        _advance(client, event.reference, authority, event, uid, reason, changes)
        return 'progress'


def reconcile_batch_privacy_late_sweeps(limit: int = 4, *, firestore_client: Any = None) -> dict[str, int]:
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    client = rpc_deadline.bind_firestore_client(client)
    now = _now()
    counts: dict[str, int] = {}
    for event in due_jobs(now=now, limit=max(1, min(limit, 4)), firestore_client=client):
        try:
            outcome = _run(client, event, now)
        except legal_holds.LegalHoldActive:
            event.reference.update({'due_at': now + HOLD_RETRY}, option=firestore.LastUpdateOption(event.update_time))
            outcome = 'held'
        except Exception as error:
            logger.warning('batch privacy late sweep retry error_type=%s', type(error).__name__)
            try:
                event.reference.update({'due_at': now + RETRY}, option=firestore.LastUpdateOption(event.update_time))
            except Exception:
                pass  # Another runner may already have moved or completed the row.
            outcome = 'retry'
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts
