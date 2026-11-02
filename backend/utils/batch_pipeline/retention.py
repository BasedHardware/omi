"""Batch artifact erasure and completion-only retention; no import-time IO.

Object cleanup is due 24h after successful projection. Metadata receipts expire
45d later, matching the existing content-ledger replay window. Pending outboxes
and dead letters have no TTL: accepted audio must not silently expire.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
from typing import Any
from urllib.parse import urlsplit

from google.api_core.exceptions import FailedPrecondition, NotFound
from google.cloud import firestore

from config.batch_language_recovery import language_guarded, words_repair_eligible, REPAIR_EPOCH, REPAIR_PROVIDER
from config.policy import RecoveryPolicy
from database import batch_pipeline_privacy_queries as queries
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed, privacy_owner_key
from database.batch_pipeline_shadow_hook import mirror_refresh

from utils.batch_pipeline.upload_policy import UPLOAD_PENDING_SECONDS
from utils.batch_pipeline.voice_centroids import deadline as voice_deadline, FINALIZED_TTL
from utils.audio_cleanup_custody import cleanup_hold_reason

ARTIFACT_RETENTION = timedelta(hours=24)
RECEIPT_RETENTION = timedelta(days=45)
HOLD_RECHECK = timedelta(hours=1)
logger = logging.getLogger(__name__)


def delete_batch_object(uid: str, uri: str) -> None:
    """Delete only a configured, owner-scoped object; foreign refs fail closed."""
    parsed = urlsplit(uri)
    bucket_name, path = parsed.netloc, parsed.path.lstrip('/')
    allowed_buckets = {
        value
        for name in ('BUCKET_BATCH_PIPELINE', 'BUCKET_TEMPORAL_SYNC_LOCAL')
        if (value := os.getenv(name, '').strip())
    }
    if (
        parsed.scheme != 'gs'
        or bucket_name not in allowed_buckets
        or parsed.query
        or not path.startswith(
            (
                f'batch-pipeline/batch_pipeline_prod/owners/{privacy_owner_key(uid)}/',
                f'batch-pipeline/batch_pipeline_dev/owners/{privacy_owner_key(uid)}/',
                f'syncing/{uid}/',
            )
        )
        or any(part in {'.', '..'} for part in path.split('/'))
    ):
        raise ValueError('batch object reference outside configured owner storage')
    generation = int(parsed.fragment) if parsed.fragment else None
    from utils.other.local_storage import create_storage_client

    storage_client: Any = create_storage_client()
    blob = storage_client.bucket(bucket_name).blob(path, generation=generation)
    try:
        blob.delete(if_generation_match=generation)
    except NotFound:
        pass


def register_batch_artifact(
    store: Any,
    uid: str,
    segment_id: str,
    uri: str,
    kind: str,
    expected_generation: int,
    *,
    item: Any = None,
) -> str:
    """Register BEFORE object upload; rejected late upload must delete its object.

    Caller repeats the privacy guard after storage IO. The pre-upload reference
    remains retryable during any storage/metadata crash, even if the job is gone.
    """
    if kind not in {'audio', 'result', 'results', 'voice_evidence'}:

        raise ValueError('unknown artifact kind')
    artifact_id = hashlib.sha256(f'{segment_id}\0{uri}'.encode()).hexdigest()
    client, namespace = store.client, store.namespace
    reference = client.collection(f'{namespace}_artifacts').document(artifact_id)

    @firestore.transactional
    def register(transaction):
        table = 'shadow_jobs' if getattr(item, 'shadow', False) else 'jobs'
        job = (
            client.collection(f'{namespace}_{table}').document(segment_id).get(transaction=transaction).to_dict() or {}
        )
        shadow = getattr(item, 'shadow', False)
        if shadow and (kind != 'audio' or job.get('shadow') is not True or job.get('state') != 'staging'):
            raise BatchPrivacyBlocked('shadow_artifact_state')
        if shadow and job.get('owner_key') != privacy_owner_key(uid):
            raise BatchPrivacyBlocked('shadow_artifact_owner')
        binding = job.get('projection_binding') or {}
        voice_write = kind == 'voice_evidence'
        projected_ids = []
        voice_due = None
        if voice_write:
            result = (
                client.collection(f'{namespace}_results').document(segment_id).get(transaction=transaction).to_dict()
                or {}
            )
            receipts = list((result.get('projection_parts') or {}).values()) or [result.get('projection') or {}]
            projected_ids = [
                r['conversation_id']
                for r in receipts
                if r.get('conversation_id') and (r.get('speaker_scope') or '').startswith('final:batch:')
            ]
            if (
                not projected_ids
                or binding.get('private_cloud_sync_enabled') is not False
                or item is None
                or datetime.now(timezone.utc).timestamp() + UPLOAD_PENDING_SECONDS >= voice_deadline(item.capture_at)
            ):
                raise PermissionError('voice evidence requires current sync-off batch projection')
            voice_due = datetime.fromtimestamp(voice_deadline(item.capture_at), timezone.utc)
            if result.get('expires_at'):
                voice_due = min(voice_due, result['expires_at'] - RECEIPT_RETENTION + timedelta(seconds=FINALIZED_TTL))
            if datetime.now(timezone.utc) + timedelta(seconds=UPLOAD_PENDING_SECONDS) >= voice_due:
                raise PermissionError('voice evidence upload cannot finish within retention window')
        conversation_ids = [
            value
            for value in (
                job.get('conversation_id'),
                binding.get('target_conversation_id'),
                getattr(item, 'conversation_id', None),
            )
            if value
        ] + projected_ids
        assert_batch_write_allowed(
            client, transaction, uid, conversation_ids=conversation_ids, expected_generation=expected_generation
        )
        recovery = job.get('recovery') or {}
        recovery_write = (
            job.get('state') == 'quarantined'
            and job.get('recovery_state') == 'running'
            and recovery.get('privacy_generation') == expected_generation
            and bool(recovery.get('token'))
            and uri.endswith(f"/{recovery['token']}.enc")
        )
        disposition = job.get('silence_disposition') or {}
        from config.batch_pipeline import empty_asr_disposition_enabled

        disposition_write = (
            empty_asr_disposition_enabled()
            and job.get('state') == 'quarantined'
            and job.get('recovery_state') == 'failed_held'
            and disposition.get('state') == 'prepared'
            and disposition.get('privacy_generation') == expected_generation
            and bool(disposition.get('token'))
            and uri.endswith(f"/{disposition['token']}.enc")
        )
        policy = RecoveryPolicy.from_dict((job.get('policy_parts') or {}).get('recovery', {}))
        terminal = job.get('terminal_disposition') or {}
        terminal_write = (
            policy.terminal_empty_disposition
            and job.get('state') == 'quarantined'
            and job.get('recovery_state') in {'held', 'failed_held'}
            and terminal.get('state') == 'prepared'
            and terminal.get('privacy_generation') == expected_generation
            and bool(terminal.get('token'))
            and uri.endswith(f"/{terminal['token']}.enc")
        )
        # C8: the provider stage persists its one paid result under the intent minted by the
        # provider_pending -> provider_running CAS (utils/batch_pipeline/provider_stt.py).
        intent = job.get('provider_intent') or {}
        provider_write = (
            job.get('state') == 'provider_running'
            and intent.get('privacy_generation') == expected_generation
            and bool(intent.get('token'))
            and uri.endswith(f"/{intent['token']}.enc")
        )
        redrive = job.get('speech_redrive') or {}
        redrive_write = (
            (
                (policy.speech_empty_multilingual and redrive.get('paid_epoch') == 2)
                or (
                    policy.recovery_enabled
                    and redrive.get('paid_epoch') == REPAIR_EPOCH
                    and redrive.get('provider') == REPAIR_PROVIDER
                    and words_repair_eligible(job)
                )
                or (
                    policy.recovery_enabled
                    and language_guarded(job)
                    and recovery.get('provider') == 'modulate'
                    and redrive.get('paid_epoch') == 3
                    and redrive.get('provider') == 'soniox'
                )
            )
            and job.get('state') == 'quarantined'
            and job.get('recovery_state') in {'held', 'failed_held'}
            and redrive.get('state') == 'running'
            and redrive.get('privacy_generation') == expected_generation
            and bool(redrive.get('token'))
            and uri.endswith(f"/{redrive['token']}.enc")
        )
        if (
            kind != 'audio'
            and job.get('state') != 'leased'
            and not recovery_write
            and not provider_write
            and not disposition_write
            and not redrive_write
            and not terminal_write
            and not voice_write
        ):
            raise BatchPrivacyBlocked('result_lease_lost')
        if job and not shadow and job.get('owner_id') != uid:
            raise ValueError('artifact owner mismatch')
        if not job and (item is None or item.owner_id != uid or kind != 'audio'):
            raise ValueError('result requires an existing owner job')
        existing = reference.get(transaction=transaction)
        if not existing.exists:
            transaction.create(
                reference,
                {
                    'owner_key': privacy_owner_key(uid),
                    'owner_id': uid,
                    'segment_id': segment_id,
                    'conversation_ids': conversation_ids,
                    'uri': uri,
                    'kind': kind,
                    'capture_at': getattr(item, 'capture_at', None) or job.get('capture_at'),
                    'duration_seconds': getattr(item, 'duration_seconds', None) or job.get('duration_seconds'),
                    'privacy_generation': expected_generation,
                    'write_pending_until': datetime.now(timezone.utc) + timedelta(seconds=UPLOAD_PENDING_SECONDS),
                    **({'cleanup_after': voice_due} if voice_write else {}),
                    **(
                        {'shadow': True, 'cleanup_after': datetime.now(timezone.utc) + timedelta(hours=1)}
                        if shadow
                        else {}
                    ),
                },
            )

    register(client.transaction())
    mirror_refresh(namespace, [('artifacts', artifact_id)])  # A2 shadow: no-op unless shadow mode
    return artifact_id


def expire_completed_segment(store: Any, uid: str, segment_id: str, now: float) -> bool:
    """Arm cleanup only after C has durably checkpointed successful projection."""
    client, namespace = store.client, store.namespace
    completed_at = datetime.fromtimestamp(now, timezone.utc)
    touched: list[tuple[str, str]] = []  # the last (committed) attempt's writes, for the A2 shadow refresh

    @firestore.transactional
    def expire(transaction):
        touched.clear()
        job_ref = client.collection(f'{namespace}_jobs').document(segment_id)
        result_ref = client.collection(f'{namespace}_results').document(segment_id)
        job = job_ref.get(transaction=transaction).to_dict() or {}
        if job.get('shadow'):
            return False
        result = result_ref.get(transaction=transaction).to_dict() or {}
        artifacts = queries.segment_artifacts(client, namespace, segment_id, transaction)
        intake_id = (job.get('projection_binding') or {}).get('job_id')
        intake_ref = client.collection(f'{namespace}_intakes').document(intake_id) if intake_id else None
        intake = intake_ref.get(transaction=transaction) if intake_ref is not None else None
        if not result or result.get('projection_state') not in {'ready', 'projected', 'completed'}:
            return False
        if job.get('owner_id') != uid or result.get('owner_key') != privacy_owner_key(uid):
            raise ValueError('completion owner mismatch')
        if result.get('expires_at'):
            return True
        expires = completed_at + RECEIPT_RETENTION
        transaction.update(job_ref, {'expires_at': expires})
        transaction.update(result_ref, {'expires_at': expires})
        touched.extend([('jobs', segment_id), ('results', segment_id)])
        if intake_ref is not None and intake is not None and intake.exists:
            transaction.update(intake_ref, {'expires_at': expires})
            touched.append(('intakes', str(intake_id)))
        touched.extend(('artifacts', artifact.id) for artifact in artifacts)
        for artifact in artifacts:
            metadata = artifact.to_dict() or {}
            if metadata.get('kind') == 'voice_evidence':
                if metadata.get('uri'):
                    due = min(metadata['cleanup_after'], completed_at + timedelta(seconds=FINALIZED_TTL))
                    transaction.update(artifact.reference, {'cleanup_after': due})
                continue
            # The native audio artifact is a small reference manifest. Keep its
            # proof through the receipt window so a first late WAL can prove
            # coverage without reprocessing retained audio. GPU results keep
            # their existing 24h retention; privacy erasure remains immediate.
            retention = (
                RECEIPT_RETENTION
                if (job.get('projection_binding') or {}).get('native_record') and metadata.get('kind') == 'audio'
                else ARTIFACT_RETENTION
            )
            transaction.update(artifact.reference, {'cleanup_after': completed_at + retention})
        return True

    expired = run_retention_transaction(client, expire)
    if touched:
        mirror_refresh(namespace, list(touched))  # A2 shadow: no-op unless shadow mode; never raises
    return expired


def run_retention_transaction(client: Any, operation: Callable[[Any], Any]) -> Any:
    """Run a retention transaction with the projection path's bounded retries.

    A bare ``operation(client.transaction())`` is retried by the SDK only for a
    commit ``Aborted``, reusing one transaction id: a read-time ``Aborted``, an
    expired transaction (``InvalidArgument`` on commit) and the SDK's
    exhausted-commit ``ValueError`` all escaped and failed the completion's
    retention phase. Aborted and expired transactions write nothing, and the
    body rereads every document, so a fresh transaction replays it safely.
    """
    from database._client import run_transactional
    from database.firestore_transaction_retry import run_with_transaction_contention_retry

    return run_with_transaction_contention_retry(
        # One SDK commit attempt per transaction: the outer helper is the only
        # commit-contention budget (5 bodies, not 5 x 5).
        lambda: client.transaction(max_attempts=1),
        lambda transaction: run_transactional(client, operation, initial_transaction=transaction),
        operation_name='batch_retention',
    )


def _flag_invalid_cleanup_receipt(artifact: Any, now: datetime, reason: str) -> bool:
    """Park inconsistent metadata without overwriting a newer privacy request."""
    updated = False
    try:
        artifact.reference.update(
            {
                'cleanup_error': reason,
                'cleanup_flagged_at': now,
                'cleanup_after': firestore.DELETE_FIELD,
                'expires_at': firestore.DELETE_FIELD,
            },
            option=firestore.LastUpdateOption(artifact.update_time),
        )
        updated = True
    except (NotFound, FailedPrecondition):
        pass
    logger.warning('event=batch_cleanup outcome=retained reason=%s', reason)
    return updated


def cleanup_completed_artifacts(
    store: Any,
    now: datetime,
    *,
    delete_uri: Callable[[str, str], None] = delete_batch_object,
    limit: int = 100,
) -> int:
    """Erase objects first; only then permit TTL to remove their last reference."""
    cleaned = 0
    touched: list[tuple[str, str]] = []
    try:
        for artifact in queries.due_artifacts(store.client, store.namespace, now, limit):
            data = artifact.to_dict() or {}
            erasure_requested = data.get('erasure_requested') is True
            uri = data.get('uri')
            uid = data.get('owner_id')
            if not isinstance(uri, str) or not uri.strip():
                if (
                    erasure_requested
                    and isinstance(uid, str)
                    and uid
                    and data.get('owner_key') == privacy_owner_key(uid)
                ):
                    # Explicit privacy intent erases metadata too. No URI is
                    # fabricated and no object outside that intent is touched.
                    artifact.reference.delete()
                    touched.append(('artifacts', artifact.id))
                    cleaned += 1
                    continue
                invalid_reason = 'missing_uri'
            elif not isinstance(uid, str) or not uid or data.get('owner_key') != privacy_owner_key(uid):
                invalid_reason = 'owner_mismatch'
            else:
                invalid_reason = None
            if invalid_reason:
                # A malformed/previously cleaned receipt is not delete authority.
                # Park and flag it so it cannot starve every subsequent due page.
                if _flag_invalid_cleanup_receipt(artifact, now, invalid_reason):
                    touched.append(('artifacts', artifact.id))
                continue
            if not erasure_requested and data.get('kind') != 'voice_evidence':
                capture_at, duration = data.get('capture_at'), data.get('duration_seconds')
                if capture_at is None or duration is None:
                    job = (
                        store.client.collection(f'{store.namespace}_jobs')
                        .document(data.get('segment_id') or artifact.id)
                        .get()
                        .to_dict()
                        or {}
                    )
                    if job and job.get('owner_id') != uid:
                        if _flag_invalid_cleanup_receipt(artifact, now, 'capture_owner_mismatch'):
                            touched.append(('artifacts', artifact.id))
                        continue
                    capture_at = job.get('capture_at') if capture_at is None else capture_at
                    duration = job.get('duration_seconds') if duration is None else duration
                reason = cleanup_hold_reason(capture_at, duration)
                if reason:
                    try:
                        artifact.reference.update(
                            {
                                'cleanup_hold': reason,
                                'cleanup_after': now + HOLD_RECHECK,
                                'expires_at': firestore.DELETE_FIELD,
                            },
                            option=firestore.LastUpdateOption(artifact.update_time),
                        )
                        touched.append(('artifacts', artifact.id))
                    except (NotFound, FailedPrecondition):
                        pass
                    logger.info('event=batch_cleanup outcome=held reason=%s', reason)
                    continue
            delete_uri(data['owner_id'], data['uri'])
            touched.append(('artifacts', artifact.id))
            # Deletion races must never recreate a purged metadata document.
            try:
                if erasure_requested or data.get('shadow'):
                    artifact.reference.delete()
                    cleaned += 1
                    continue
                artifact.reference.update(
                    {
                        'uri': firestore.DELETE_FIELD,
                        'cleanup_after': firestore.DELETE_FIELD,
                        'cleanup_hold': firestore.DELETE_FIELD,
                        'expires_at': now + RECEIPT_RETENTION,
                    }
                )
            except NotFound:
                pass
            cleaned += 1
    finally:
        if touched:  # A2 shadow: re-copy (or delete) what this pass touched; no-op unless shadow mode
            mirror_refresh(store.namespace, touched)
    return cleaned


def batch_artifact_authorize(store: Any, item: Any, *, snapshots: dict | None = None):
    """B's required authorize(item) callback, using uncached transactional reads."""
    from utils.batch_pipeline.artifacts import ProtectionContext

    @firestore.transactional
    def authorize(transaction):
        loaded = {}
        generation = assert_batch_write_allowed(
            store.client,
            transaction,
            item.owner_id,
            conversation_ids=(item.conversation_id,) if item.conversation_id else (),
            expected_generation=item.privacy_generation,
            snapshots=loaded,
        )
        if snapshots is not None:
            snapshots.clear()
            snapshots.update(loaded)
        user = loaded['user']
        return ProtectionContext(user.get('data_protection_level', 'enhanced'), generation)

    return authorize(store.client.transaction())


def batch_artifact_register(store: Any, item: Any, uri: str, kind: str, context: Any) -> None:
    """B's register_artifact(item, uri, kind, context) callback (before upload)."""
    register_batch_artifact(store, item.owner_id, item.segment_id, uri, kind, context.generation, item=item)


def purge_batch_storage_owner(uid: str, namespace: str) -> None:
    """Sweep all versions of the deterministic owner prefix, including orphans."""
    bucket_name = os.getenv('BUCKET_BATCH_PIPELINE', '').strip()
    if not bucket_name:
        return  # No artifact store can be constructed without an explicit bucket.
    from utils.other.local_storage import create_storage_client

    client: Any = create_storage_client()
    bucket = client.bucket(bucket_name)
    prefix = f'batch-pipeline/{namespace}/owners/{privacy_owner_key(uid)}/'
    for blob in bucket.list_blobs(prefix=prefix, versions=True):
        try:
            blob.delete(if_generation_match=int(blob.generation))
        except NotFound:
            pass
    if list(bucket.list_blobs(prefix=prefix, versions=True, max_results=1)):
        raise RuntimeError('batch owner storage purge did not converge')
