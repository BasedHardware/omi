"""Re-arm the existing partial continuation without rewriting completed work."""

from dataclasses import replace
from datetime import datetime, timezone
import hashlib

from config.policy import resolve_batch_policy
from config.record_audio import record_identity
from database.batch_pipeline_privacy import assert_batch_write_allowed
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
    if row.get('status') != 'completed' or not isinstance(finish, datetime):
        return {}, None
    namespace = 'batch_pipeline_' + current_stage()
    content, original = record_identity(uid, cid)
    jobs = client.collection(namespace + '_jobs')
    original_ref = jobs.document(original)
    original_job = original_ref.get(transaction=tx).to_dict() or {}
    # Existing partial captures retain their coordinator and sample coverage.
    ref = (
        original_ref
        if original_job.get('partial_coordinator') or original_job.get('state') in {'record_pending', 'partial_retired'}
        else jobs.document(recovery_segment(uid, cid))
    )
    job = original_job if ref == original_ref else ref.get(transaction=tx).to_dict() or {}
    generation = assert_batch_write_allowed(client, tx, uid, conversation_ids=(cid,))
    policy = (
        original_job.get('policy')
        or replace(
            resolve_batch_policy(uid), batch_enabled=True, live_admission_enabled=True, live_record_enabled=True
        ).to_dict()
    )
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
        'state': 'record_pending',
        'available_at': now,
        'enqueued_at': job.get('enqueued_at', now),
        'record_content_id': content,
        'record_snapshot': snapshot,
        'policy': job.get('policy') or policy,
        'policy_source': 'admission',
        'merge_pending': False,
        'partial_coordinator': True,
        'lease_recovery': ref != original_ref,
        'partial_reason': mark['reason'],
    }
    if job.get('partial_run'):
        run = dict(job['partial_run'])
        run.pop('retired_at', None)
        run.update(next_inventory_at=now, inventory_changed_at=now, complete=True, fingerprint='')
        job['partial_run'] = run
    return {'record_audio_closed': False, 'record_audio_partial': mark}, (ref, job)
