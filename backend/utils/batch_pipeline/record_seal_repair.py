"""Exact-job record seal repair. Plans stay private; public reports are aggregates."""

from collections import Counter
from datetime import datetime
import hashlib
import json
from typing import Any

from google.cloud import firestore

from database._client import run_transactional
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.live import retained_record_units
from utils.batch_pipeline.record_barrier import validate_record_tail
from utils.batch_pipeline.record_producer_proof import producer_tokens_dead
from utils.other.storage import list_audio_chunks

ROW_FIELDS = (
    'record_lane_owner',
    'record_upload_failed',
    'record_upload_sessions',
    'record_upload_revision',
    'record_audio_closed',
    'status',
    'deleted',
    'discarded',
    'private_cloud_sync_enabled',
    'data_protection_level',
    'started_at',
    'finished_at',
)


def seal_row_state(row):
    return {key: row.get(key) for key in ROW_FIELDS}


def _job_state(job):
    # The pending drainer advances this retry wake every minute. It grants no
    # seal authority and must not invalidate an otherwise identical approval.
    return {key: value for key, value in job.items() if key != 'available_at'}


def plan_digest(value):
    def encode(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError('unsupported plan value')

    return hashlib.sha256(json.dumps(value, sort_keys=True, default=encode, separators=(',', ':')).encode()).hexdigest()


def seal_refusal(job, row, *, producer_proof=None, producers_stopped=False):
    if job.get('state') != 'record_pending' or not job.get('record_content_id'):
        return 'not_pending'
    if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
        return 'not_batch_owned'
    if row.get('record_upload_failed'):
        return 'upload_failed'
    if row.get('record_upload_sessions') and not producer_tokens_dead(
        row['record_upload_sessions'], producer_proof, producers_stopped=producers_stopped
    ):
        return 'upload_pending'
    if row.get('record_audio_closed'):
        return 'already_closed'
    if row.get('status') != 'completed':
        return 'not_completed'
    if row.get('deleted') or row.get('discarded') or not row.get('private_cloud_sync_enabled'):
        return 'privacy_refused'
    return None


def retained_tail_proof(job, row, storage_client, artifacts, *, check_budget=lambda: None):
    """Shared retained-object and frozen/current-finish proof for operator seals."""
    uid, cid = job['owner_id'], job['conversation_id']
    seed = WorkItem(
        job['segment_id'],
        uid,
        0,
        'record:pending',
        1,
        Priority.FRESH,
        conversation_id=cid,
        privacy_generation=job['privacy_generation'],
    )
    check_budget()
    artifacts.authorize(seed)
    check_budget()
    chunks = list_audio_chunks(uid, cid, max_count=4096, require_archive=True)
    check_budget()
    units = []
    iterator = retained_record_units(uid, cid, chunks, storage_client, artifacts.key_for_owner(uid))
    try:
        for unit in iterator:
            check_budget()
            units.append(unit)
            if len(units) > 128:
                raise ValueError('retained capture unit budget exceeded')
    finally:
        iterator.close()
    validate_record_tail(units, row.get('finished_at'), require_finish=True)
    validate_record_tail(units, (job.get('record_snapshot') or {}).get('finished_at'), require_finish=True)
    check_budget()
    return plan_digest(units)


def plan_seals(
    store,
    job_ids,
    storage_client,
    artifacts,
    *,
    producer_proof=None,
    producers_stopped=False,
    check_budget=lambda: None,
):
    entries = []
    for job_id in sorted(job_ids):
        check_budget()
        entry = {'job_id': job_id, 'disposition': 'unavailable'}
        try:
            job = _job_state(store.run(lambda tx: tx.get('jobs', job_id)))
            check_budget()
            uid, cid = job.get('owner_id'), job.get('conversation_id')
            if not uid or not cid or '/' in uid or '/' in cid:
                entries.append(entry)
                continue
            row = store.run(lambda tx: tx.get('conversations', f'{uid}/{cid}'))
            check_budget()
            entry.update(job=job, row=seal_row_state(row))
            refusal = seal_refusal(job, row, producer_proof=producer_proof, producers_stopped=producers_stopped)
            if refusal:
                entry['disposition'] = refusal
            else:
                proof = retained_tail_proof(
                    {**job, 'segment_id': job_id}, row, storage_client, artifacts, check_budget=check_budget
                )
                entry.update(disposition='eligible', proof_sha256=proof)
        except BatchPrivacyBlocked:
            entry['disposition'] = 'privacy_refused'
        except (ValueError, TypeError, AttributeError, KeyError):
            entry['disposition'] = 'proof_refused'
        except Exception:
            entry['disposition'] = 'read_error'
        entries.append(entry)
    check_budget()
    plan = {
        'version': 1,
        'namespace': store.namespace,
        'entries': entries,
        'producer_proof': producer_proof,
        'producers_stopped': producers_stopped,
    }
    return {**plan, 'plan_sha256': plan_digest(plan)}


def apply_seals(store, plan, approved_digest, *, check_budget=lambda: None, outcomes=None):
    body = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if approved_digest != plan['plan_sha256'] or plan_digest(body) != approved_digest:
        raise ValueError('fresh dry-run plan approval required')
    if store.namespace != plan['namespace']:
        raise ValueError('plan namespace changed')
    outcomes = Counter() if outcomes is None else outcomes
    for entry in plan['entries']:
        check_budget()
        if entry['disposition'] != 'eligible':
            outcomes[entry['disposition']] += 1
            continue
        job = entry['job']
        uid, cid = job['owner_id'], job['conversation_id']
        ref = store.client.collection('users').document(uid).collection('conversations').document(cid)
        job_ref = store.client.collection(f'{store.namespace}_jobs').document(entry['job_id'])

        @firestore.transactional
        def commit(tx):
            check_budget()
            current_job = job_ref.get(transaction=tx).to_dict() or {}
            row = ref.get(transaction=tx).to_dict() or {}
            if _job_state(current_job) != job or seal_row_state(row) != entry['row']:
                return 'state_changed'
            refusal = seal_refusal(
                current_job, row, producer_proof=plan['producer_proof'], producers_stopped=plan['producers_stopped']
            )
            if refusal:
                return refusal
            assert_batch_write_allowed(
                store.client, tx, uid, conversation_ids=(cid,), expected_generation=job['privacy_generation']
            )
            patch: dict[str, Any] = {'record_audio_closed': True}
            if row.get('record_upload_sessions'):
                patch['record_upload_sessions'] = {}  # Only the exact proven-dead map.
            check_budget()
            tx.update(ref, patch)
            return 'sealed'

        try:
            outcomes[run_transactional(store.client, commit, transient=True)] += 1
        except BatchPrivacyBlocked:
            outcomes['privacy_refused'] += 1
        except Exception:
            outcomes['write_error'] += 1
    return dict(sorted(outcomes.items()))


def plan_summary(plan):
    return {
        'operation': 'record-seal-repair-v1',
        'plan_sha256': plan['plan_sha256'],
        'count': len(plan['entries']),
        'dispositions': dict(sorted(Counter(e['disposition'] for e in plan['entries']).items())),
    }
