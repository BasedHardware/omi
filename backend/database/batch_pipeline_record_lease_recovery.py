"""Re-arm the existing partial continuation without rewriting completed work."""

from datetime import datetime, timezone
import hashlib

from config.record_audio import record_identity
from database.record_recovery_gate import publication_ready, WAITING_STATE
from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.batch_pipeline_policy import policy_in_transaction
from database.batch_pipeline_store import FirestoreTransaction
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.stage import current_stage


def recovery_segment(uid, cid):
    return hashlib.sha256(f'record-lease-recovery-v1:{uid}:{cid}'.encode()).hexdigest()


def prepare_recovery(client, tx, uid, cid, row, revision, now):
    """Read all authorities before writes; return a row patch and deferred job write.

    A separate coordinator leaves completed/leased original units and their
    immutable projection bindings alone. Partial continuation fills empty audio
    spans, including interior gaps, and preserves existing annotated text.
    """
    finish = row.get('finished_at')
    if not isinstance(finish, datetime):
        return {}, None
    namespace = 'batch_pipeline_' + current_stage()
    content, original = record_identity(uid, cid)
    jobs = client.collection(namespace + '_jobs')
    original_ref = jobs.document(original)
    original_job = original_ref.get(transaction=tx).to_dict() or {}
    if not original_job.get('partial_coordinator') and not row.get('record_audio_partial'):
        captured = original_job.get('record_input_upload_revision')
        if captured is not None and revision <= captured:
            return {}, None
        if (not original_job and not row.get('record_audio_closed')) or (
            original_job.get('state') == 'record_pending'
            and captured is None
            and not original_job.get('projection_binding')
        ):
            # Input has not been admitted. Admission reads the current barrier
            # and CAS-validates it after staging, so an older plan must retry.
            return {'record_audio_closed': False}, None
        # A closed legacy row without the native reservation may have already
        # published through another intake. Preserve a conservative obligation.
    # Existing partial captures retain their coordinator and sample coverage.
    ref = (
        original_ref
        if original_job.get('partial_coordinator') or original_job.get('state') == 'partial_retired'
        else jobs.document(recovery_segment(uid, cid))
    )
    job = original_job if ref == original_ref else ref.get(transaction=tx).to_dict() or {}
    ready = ref == original_ref or publication_ready(client, tx, namespace, uid, cid, original_job)
    generation = assert_batch_write_allowed(client, tx, uid, conversation_ids=(cid,))
    snapshot = {
        key: row.get(key)
        for key in (
            'id',
            'source',
            'language',
            'client_device_id',
            'client_platform',
            'started_at',
            'finished_at',
            'data_protection_level',
        )
    }
    if (row.get('external_data') or {}).get('server_batch_only') is True:
        snapshot['server_batch_only'] = True
    mark = dict(row.get('record_audio_partial') or {})
    mark.update(
        version=1,
        reason=mark.get('reason', 'tail_lost_or_unproven'),
        finished_at=finish,
        upload_revision=revision,
        generation=mark.get('generation', 0),
        applied_generation=mark.get('applied_generation', 0),
        finished_partial_at=mark.get('finished_partial_at', datetime.fromtimestamp(now, timezone.utc)),
    )
    job = {
        **job,
        'segment_id': ref.id,
        'owner_id': uid,
        'owner_key': owner_key(uid),
        'conversation_id': cid,
        'privacy_generation': generation,
        'priority': 0,
        'state': 'record_pending' if ready else WAITING_STATE,
        'available_at': now,
        'enqueued_at': job.get('enqueued_at', now),
        'record_content_id': content,
        'record_snapshot': snapshot,
        'policy': job.get('policy') or original_job.get('policy'),
        'policy_source': job.get('policy_source') or original_job.get('policy_source', 'admission'),
        'merge_pending': False,
        'partial_coordinator': True,
        'lease_recovery': ref != original_ref,
        'partial_reason': mark['reason'],
    }
    partial_run = job.get('partial_run')
    if partial_run:
        if not isinstance(partial_run, dict):
            raise ValueError('partial recovery run must be a mapping')
        run = dict(partial_run)
        run.pop('retired_at', None)
        run.update(next_inventory_at=now, inventory_changed_at=now, complete=True, fingerprint='')
        job['partial_run'] = run
    # Copy a recorded admission snapshot. Pre-policy reservations use the
    # canonical first-writer fallback and persist it on this obligation in the
    # same transaction; a later append never re-resolves its policy.
    view = FirestoreTransaction(client, namespace, tx)
    policy = policy_in_transaction(view, job)
    if set(view.writes) - {('jobs', ref.id)}:
        raise ValueError('recovery cannot rewrite original policy siblings')
    job['policy'] = policy.to_dict()
    return {'record_audio_closed': False, 'record_audio_partial': mark}, (ref, job)
