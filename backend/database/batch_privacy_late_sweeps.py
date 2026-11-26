"""Drain durable post-window artifact erasure under the account legal-hold gate."""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
import re
from typing import Any

from google.api_core.exceptions import FailedPrecondition, GoogleAPICallError, InvalidArgument, NotFound
from google.cloud import firestore
from google.cloud.firestore_v1.base_client import _parse_batch_get  # pyright: ignore[reportPrivateUsage]

from database import legal_holds, rpc_deadline
from database._client import get_data_plane_firestore_client
from database.batch_account_authority_schema import ACCOUNT_DELETION_COLLECTION, recording_policy_denies
from database.batch_pipeline_conversation_purge import purge_cursor
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_privacy_queries import owner_documents
from database.batch_pipeline_purge import NAMESPACES
from database.batch_pipeline_shadow_hook import purge_owner
from database.batch_privacy_late_intents import COLLECTION, DELAY
from database.privacy_check_metrics import POST_WINDOW_DEAD_LETTERS, POST_WINDOW_OPERATIONS, POST_WINDOW_SWEEPS
from utils.batch_pipeline.retention import BATCH_OBJECT_BUCKET_ENV, batch_object_address, delete_batch_object
from utils.other.local_storage import create_storage_client

logger = logging.getLogger(__name__)
GATE_KIND = 'explicit_memory_deletion'
REASONS = frozenset({'account_deleted', 'data_protection', 'recording_policy'})
RETRY = timedelta(minutes=5)
HOLD_RETRY = timedelta(hours=1)
PAGE_RETRY = timedelta(seconds=5)
DEFAULT_PERMANENT_ATTEMPTS = 5
SCOPE_FIELDS = ('record_lane_owner', 'private_cloud_sync_enabled', 'uses_custom_stt')


class PermanentSweepError(ValueError):
    """A deterministic refusal that must keep a durable recovery record."""


def _attempt_limit() -> int:
    try:
        configured = os.getenv('BATCH_PRIVACY_LATE_SWEEP_PERMANENT_ATTEMPTS', str(DEFAULT_PERMANENT_ATTEMPTS))
        return max(1, min(20, int(configured)))
    except ValueError:
        return DEFAULT_PERMANENT_ATTEMPTS


def _attempts(previous: Any) -> int:
    return previous + 1 if type(previous) is int and 0 <= previous < 20 else 1


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
    if data.get('owner_id') != uid:
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
    uri = data.get('uri')
    if not isinstance(uri, str) or not uri:
        raise PermanentSweepError('artifact_address')
    allowed = {value for name in BATCH_OBJECT_BUCKET_ENV if (value := os.getenv(name, '').strip())}
    try:
        bucket_name, path, generation = batch_object_address(uid, uri, allowed)
    except (TypeError, ValueError, AttributeError):
        raise PermanentSweepError('artifact_address') from None
    if generation is None:
        # These upload reservations own a create-only, attempt-scoped object
        # name. An unversioned reference outside that contract proves nothing.
        kind = data.get('kind')
        segment = data.get('segment_id')
        if (
            kind not in ('audio', 'result', 'results', 'voice_evidence')
            or not isinstance(segment, str)
            or path.rsplit('/', 3)[-3:-1] != [kind, segment]
            or not re.fullmatch(r'[a-f0-9]{32}\.enc', path.rsplit('/', 1)[-1])
        ):
            raise PermanentSweepError('artifact_identity')
        blob = storage.bucket(bucket_name).blob(path)
        try:
            blob.reload(timeout=5, retry=None)
        except NotFound:
            return None
        try:
            generation = int(blob.generation or 0)
        except (TypeError, ValueError):
            raise PermanentSweepError('artifact_identity') from None
    if generation <= 0:
        raise PermanentSweepError('artifact_identity')
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


def _advance(
    client,
    reference,
    authority,
    event,
    uid,
    reason,
    changes,
    *,
    artifact=None,
    complete=False,
    preserve_artifact=False,
    receipt_retry=None,
):
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
            if receipt_retry is not None:
                debt_id = hashlib.sha256(f'{event.id}\0{artifact.reference.path}'.encode()).hexdigest()
                transaction.create(reference.parent.document(debt_id), receipt_retry)
            elif not preserve_artifact:
                transaction.delete(artifact.reference)
        if complete:
            transaction.delete(reference)
        else:
            transaction.update(reference, changes)
        return True

    return apply(client.transaction())


def _historical_scope(client, reference, read_time):
    # The high-level SDK only exposes current snapshots for point reads.
    request, references, kwargs = client._prep_get_all([reference], SCOPE_FIELDS, None, None, 5)
    del request['transaction']
    request['read_time'] = read_time
    responses = client._firestore_api.batch_get_documents(request=request, metadata=client._rpc_metadata, **kwargs)
    try:
        return _parse_batch_get(next(responses), references, client)
    except StopIteration:
        raise RuntimeError('recording scope read returned no snapshot') from None


def _certify_scope(client, event, uid, source, changed_at, now):
    reference = client.document(f'users/{uid}/conversations/{source}')
    snapshot = reference.get(field_paths=SCOPE_FIELDS, timeout=5, retry=None)
    # A later lane claim (or a new document with the same ID) cannot turn an
    # ordinary edit into recording erasure. A later re-enable cannot undo a
    # genuine obligation. Recover the exact state committed with the intent.
    if not snapshot.exists or snapshot.update_time > event.create_time:
        try:
            snapshot = _historical_scope(client, reference, event.create_time)
        except (InvalidArgument, FailedPrecondition):
            if datetime.now(timezone.utc) - event.create_time >= timedelta(hours=1):
                raise PermanentSweepError('scope_history_unavailable') from None
            raise
    option = firestore.LastUpdateOption(event.update_time)
    if not recording_policy_denies(snapshot.to_dict() or {}):
        event.reference.delete(option=option)
        return 'superseded'
    event.reference.update({'scope_verified': True, 'due_at': max(now, changed_at + DELAY)}, option=option)
    return 'scope_verified'


def _receipt_failure(client, event, authority, uid, reason, now, artifact, error):
    data = event.to_dict()
    direct = 'artifact_id' in data
    attempts = _attempts(data.get('permanent_attempts'))
    dead = attempts >= _attempt_limit()
    retry = {
        'uid': uid,
        'reason': reason,
        'changed_at': data['changed_at'],
        'conversation_id': data.get('conversation_id', ''),
        'scope_verified': data.get('scope_verified', False),
        'artifact_id': artifact.id,
        'namespace_index': data.get('namespace_index', 0),
        'permanent_attempts': attempts,
    }
    if dead:
        retry.update(dead_letter_error=str(error), dead_lettered_at=now)
    else:
        retry['due_at'] = now + RETRY
    if direct:
        changes = retry
        if dead:
            changes['due_at'] = firestore.DELETE_FIELD
    else:
        # Register the retry atomically with advancing the scan. No later
        # receipt waits for retries on a different storage identity.
        changes = {'after': artifact.id, 'due_at': now + PAGE_RETRY, 'has_receipt_retries': True}
    if not _advance(
        client,
        event.reference,
        authority,
        event,
        uid,
        reason,
        changes,
        artifact=artifact,
        preserve_artifact=True,
        receipt_retry=None if direct else retry,
    ):
        return 'changed'
    if dead:
        POST_WINDOW_DEAD_LETTERS.labels(str(error)).inc()
        logger.error('batch privacy late sweep receipt dead-lettered cause=%s', error)
        return 'dead_lettered'
    return 'retry'


def _run(client, event, now):
    data = event.to_dict() or {}
    uid, reason, changed_at = data.get('uid'), data.get('reason'), data.get('changed_at')
    index, source, after = data.get('namespace_index', 0), data.get('conversation_id', ''), data.get('after')
    artifact_id = data.get('artifact_id')
    if (
        not isinstance(uid, str)
        or not uid
        or '/' in uid
        or len(uid.encode()) > 256
        or not isinstance(reason, str)
        or reason not in REASONS
        or not isinstance(changed_at, datetime)
        or changed_at.utcoffset() is None
        or type(index) is not int
        or not 0 <= index <= len(NAMESPACES)
        or not isinstance(source, str)
        or '/' in source
        or len(source.encode()) > 256
        or (reason != 'recording_policy' and source)
        or (after is not None and (not isinstance(after, str) or not after or '/' in after))
        or (
            artifact_id is not None
            and (not isinstance(artifact_id, str) or not artifact_id or '/' in artifact_id or index == len(NAMESPACES))
        )
    ):
        raise PermanentSweepError('malformed_intent')
    if source and data.get('scope_verified') is not True:
        return _certify_scope(client, event, uid, source, changed_at, now)
    if changed_at + DELAY > now:
        event.reference.update({'due_at': changed_at + DELAY}, option=firestore.LastUpdateOption(event.update_time))
        return 'early'
    key = privacy_owner_key(uid)
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
                if not data.get('has_receipt_retries'):
                    POST_WINDOW_SWEEPS.labels(reason).inc()
                return 'completed'
            return 'changed'

        namespace = NAMESPACES[index]
        if artifact_id:
            page = [client.document(f'{namespace}_artifacts/{artifact_id}').get()]
        else:
            page = owner_documents(
                client, namespace, 'artifacts', key, after=purge_cursor(client, namespace, 'artifacts', after)
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
            try:
                uri = _pin(uid, receipt, storage)
            except PermanentSweepError as error:
                return _receipt_failure(client, event, authority, uid, reason, now, snapshot, error)
            if uri:
                authority.remote(
                    lambda: delete_batch_object(uid, uri, timeout=5, storage_client=storage),
                    target=f'late-batch:{namespace}:{uri}',
                )
                POST_WINDOW_OPERATIONS.labels(reason, 'object_storage').inc()
            changes = {'after': snapshot.id, 'needs_postgres': True, 'due_at': now + PAGE_RETRY}
            if _advance(client, event.reference, authority, event, uid, reason, changes, artifact=snapshot):
                POST_WINDOW_OPERATIONS.labels(reason, 'firestore').inc()
            return 'progress'

        if artifact_id:
            if data.get('needs_postgres'):
                rows = authority.remote(lambda: purge_owner(namespace, uid), target=f'late-batch:{namespace}')
                POST_WINDOW_OPERATIONS.labels(reason, 'postgres').inc(rows)
            return (
                'completed'
                if _advance(client, event.reference, authority, event, uid, reason, {}, complete=True)
                else 'changed'
            )
        if page:
            changes = {'after': page[-1].id, 'due_at': now + PAGE_RETRY}
        else:
            if data.get('needs_postgres') or reason == 'account_deleted':
                rows = authority.remote(lambda: purge_owner(namespace, uid), target=f'late-batch:{namespace}')
                POST_WINDOW_OPERATIONS.labels(reason, 'postgres').inc(rows)
            changes = {'namespace_index': index + 1, 'after': None, 'needs_postgres': False, 'due_at': now + PAGE_RETRY}
        _advance(client, event.reference, authority, event, uid, reason, changes)
        return 'progress'


def _reschedule(event, changes) -> bool:
    try:
        event.reference.update(changes, option=firestore.LastUpdateOption(event.update_time))
    except (FailedPrecondition, NotFound):
        return False
    except GoogleAPICallError as error:
        logger.warning('batch privacy late sweep could not reschedule error_type=%s', type(error).__name__)
        return False
    return True


def _intent_failure(event, now, error):
    attempts = _attempts((event.to_dict() or {}).get('permanent_attempts'))
    if attempts < _attempt_limit():
        return 'retry' if _reschedule(event, {'permanent_attempts': attempts, 'due_at': now + RETRY}) else 'changed'
    if not _reschedule(
        event,
        {
            'permanent_attempts': attempts,
            'dead_lettered_at': now,
            'dead_letter_error': str(error),
            'due_at': firestore.DELETE_FIELD,
        },
    ):
        return 'changed'
    POST_WINDOW_DEAD_LETTERS.labels(str(error)).inc()
    logger.error('batch privacy late sweep intent dead-lettered cause=%s', error)
    return 'dead_lettered'


def reconcile_batch_privacy_late_sweeps(limit: int = 4, *, firestore_client: Any = None) -> dict[str, int]:
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    client = rpc_deadline.bind_firestore_client(client)
    now = _now()
    counts: dict[str, int] = {}
    for event in due_jobs(now=now, limit=max(1, min(limit, 4)), firestore_client=client):
        try:
            outcome = _run(client, event, now)
        except legal_holds.LegalHoldActive:
            outcome = 'held' if _reschedule(event, {'due_at': now + HOLD_RETRY}) else 'changed'
        except PermanentSweepError as error:
            outcome = _intent_failure(event, now, error)
        except Exception as error:
            logger.warning('batch privacy late sweep retry error_type=%s', type(error).__name__)
            try:
                _reschedule(event, {'due_at': now + RETRY})
            except Exception:
                pass  # Another runner may already have moved or completed the row.
            outcome = 'retry'
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts
