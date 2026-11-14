"""Partial finish and serial continuation; no complete-seal authority."""

from datetime import datetime, timezone

from google.cloud import firestore
from prometheus_client import Counter

from config import record_partial as config
from config import record_seal_repair as repair_config
from config.record_audio import record_identity, require_record_audio_barrier
from database._client import run_transactional
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreTransaction
from utils.batch_pipeline.record_producer_proof import producer_tokens_dead, leases_would_release
from database import record_token_lease_metrics as lease_metrics
from config import record_seal_rules as lease

PAYER_REFUSALS = Counter('omi_record_audio_partial_byok_refusals_total', 'Partial finishes refused for BYOK')


def continuation_refusal(store, pending):
    """Fresh row/payer read immediately before continuation storage IO."""

    def read(tx):
        row = tx.get('conversations', f"{pending['owner_id']}/{pending['conversation_id']}")
        job = tx.get('jobs', pending['segment_id'])
        if row.get('discarded'):
            return 'discarded_refused'
        if (job.get('policy') or {}).get('provider_reason') == 'byok':
            return 'byok_refused'
        if job.get('state') != 'record_pending':
            return 'state_changed'
        if job.get('lease_recovery'):
            # A full projection of the old sealed inventory must settle before
            # a partial fill, otherwise that older full pass could erase it.
            content, original = record_identity(pending['owner_id'], pending['conversation_id'])
            intake = tx.get('intakes', 'bp_' + content)
            ledger = tx.get('content', f"{pending['owner_id']}/{content}")
            if intake:
                if ledger.get('status') != 'completed':
                    return 'state_changed'
            else:
                previous = tx.get('jobs', original)
                if previous and previous.get('state') != 'committed':
                    return 'state_changed'
        return None

    return store.run(read)


def finish_partial(store, path, *, reason, proof, now, register=None, preview=False, retry_aged=False):
    """Fresh transactional fence, including producer completion during planning.

    The complete planner's refusal is diagnostic only. This path checks its own
    age, producer and privacy authorities and can only write a partial marker.
    """
    if not config.enabled() or reason not in config.REASONS:
        return 'disabled'
    _, uid, _, cid = path.split('/')
    _, segment = record_identity(uid, cid)
    row_ref = store.client.collection('users').document(uid).collection('conversations').document(cid)

    observation = {}

    @firestore.transactional
    def commit(raw):
        observation.clear()
        tx = FirestoreTransaction(store.client, store.namespace, raw)
        row = tx.get('conversations', f'{uid}/{cid}')
        selected_segment = segment
        job = tx.get('jobs', segment)
        if row.get('record_audio_partial') and not job.get('partial_coordinator'):
            from database.batch_pipeline_record_lease_recovery import recovery_segment

            recovery = recovery_segment(uid, cid)
            continuation = tx.get('jobs', recovery)
            if continuation.get('partial_coordinator'):
                selected_segment, job = recovery, continuation
        if not config.enabled():
            return 'disabled'
        if not proof or not proof.get('resource_version') or not producer_tokens_dead({}, proof):
            return 'state_changed'
        if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
            return 'not_batch_owned'
        if row.get('record_audio_closed') and not row.get('record_audio_partial'):
            return 'already_closed'
        if row.get('status') != 'completed':
            return 'not_completed'
        if (
            row.get('deleted')
            or row.get('discarded')
            or row.get('uses_custom_stt')
            or not row.get('private_cloud_sync_enabled')
            or row.get('data_protection_level') not in {None, 'standard', 'enhanced'}
        ):
            return 'privacy_refused'
        finish = row.get('finished_at')
        if not isinstance(finish, datetime) or finish.tzinfo is None or now - finish.timestamp() < config.WAIT_SECONDS:
            return 'not_aged'
        if row.get('record_upload_sessions') and not producer_tokens_dead(
            row['record_upload_sessions'], proof, uid=uid, row=row, job=job
        ):
            observation['would'] = leases_would_release(row['record_upload_sessions'], proof, uid=uid, row=row, job=job)
            return 'upload_pending'
        if job and (job.get('state') not in {'record_pending', 'partial_retired'} or not job.get('record_content_id')):
            return 'not_pending'
        if not job:
            if register is None or row.get('record_lane_owner') != 'batch_live_v1':
                return 'not_pending'
            job = register(tx, uid, cid, row)
        if (job.get('policy') or {}).get('provider_reason') == 'byok':
            return 'byok_refused'
        tx.check_privacy(uid, (cid,), expected_generation=job['privacy_generation'])
        mark = row.get('record_audio_partial') or {}
        aged_retry = retry_aged and repair_config.jobs_enabled()
        if config.partial_barrier(row) and job.get('partial_coordinator'):
            if not (
                aged_retry and job.get('state') in {'record_pending', 'partial_retired'} and config.repair_due(row, now)
            ):
                return 'already_partial'
        if preview:
            return 'partial_eligible'
        mark = {
            'version': 1,
            'reason': mark.get('reason', reason),
            'finished_at': finish,
            'upload_revision': row.get('record_upload_revision'),
            'generation': mark.get('generation', 0),
            'applied_generation': mark.get('applied_generation', 0),
            'finished_partial_at': mark.get('finished_partial_at', datetime.fromtimestamp(now, timezone.utc)),
        }
        if aged_retry:
            mark['repair_attempted_at'] = datetime.fromtimestamp(now, timezone.utc)
        # A changed upload revision or proof-gated aged retry reopens the
        # coordinator, preserving its existing coverage and barrier generations.
        job.update(state='record_pending', partial_coordinator=True, partial_reason=mark['reason'], available_at=now)
        if job.get('partial_run') and job['partial_run'].get('retired_at'):
            job['partial_run'] = {**job['partial_run'], 'inventory_changed_at': now, 'next_inventory_at': now}
            job['partial_run'].pop('retired_at')
        if aged_retry and job.get('partial_run'):
            job['partial_run'] = {**job['partial_run'], 'next_inventory_at': now}
        if not producer_tokens_dead({}, proof):
            return 'state_changed'
        observation['expired'] = lease.token_lease_serving(uid) and leases_would_release(
            row.get('record_upload_sessions'),
            proof,
            uid=uid,
            row=row,
            job=job,
        )
        tx.put('jobs', selected_segment, job)
        tx.flush()
        raw.update(row_ref, {'record_audio_closed': False, 'record_audio_partial': mark, 'record_upload_sessions': {}})
        return 'partial_finished'

    try:
        result = run_transactional(store.client, commit, transient=True)
        if result == 'partial_finished' and observation.get('expired'):
            lease_metrics.EXPIRED_SEALED.inc()
        if result == 'upload_pending' and observation.get('would'):
            lease_metrics.EXPIRED_WOULD.inc()
        if result == 'byok_refused':
            PAYER_REFUSALS.inc()
        return result
    except BatchPrivacyBlocked:
        return 'privacy_refused'


def update_run(store, pending, barrier, expected_run, run, *, now, applied=False):
    """CAS the coordinator and marker in one transaction; never overwrite text."""
    uid, cid, segment = pending['owner_id'], pending['conversation_id'], pending['segment_id']
    row_ref = store.client.collection('users').document(uid).collection('conversations').document(cid)

    @firestore.transactional
    def commit(raw):
        tx = FirestoreTransaction(store.client, store.namespace, raw)
        row = tx.get('conversations', f'{uid}/{cid}')
        job = tx.get('jobs', segment)
        if (
            not config.enabled()
            or job.get('state') != 'record_pending'
            or not job.get('partial_coordinator')
            or job.get('partial_run') != expected_run
        ):
            return False
        if row.get('discarded') or (job.get('policy') or {}).get('provider_reason') == 'byok':
            return False
        require_record_audio_barrier(row, expected=barrier)
        tx.check_privacy(uid, (cid,), expected_generation=pending['privacy_generation'])
        mark = dict(row['record_audio_partial'])
        mark['generation'] = run['generation']
        if applied:
            mark['applied_generation'] = run['generation']
        job.update(partial_run=run, available_at=run['next_inventory_at'] if run.get('complete') else now + 60)
        if run.get('retired_at'):
            job['state'] = 'partial_retired'
        # Attach the encrypted plan to the coordinator's normal audio outbox.
        if run.get('plan_uri'):
            job['audio_uri'] = run['plan_uri']
        tx.put('jobs', segment, job)
        tx.flush()
        raw.update(row_ref, {'record_audio_closed': False, 'record_audio_partial': mark})
        return True

    return run_transactional(store.client, commit, transient=True)
