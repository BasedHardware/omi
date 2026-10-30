"""Exact-job record seal repair. Plans stay private; public reports are aggregates."""

from collections import Counter
from datetime import datetime
import hashlib
import json

from google.cloud import firestore

from database._client import run_transactional
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.live import retained_record_units
from utils.batch_pipeline.record_barrier import validate_record_tail
from utils.other.storage import list_audio_chunks

ROW_FIELDS = (
    'record_lane_owner',
    'record_upload_failed',
    'record_upload_sessions',
    'record_audio_closed',
    'status',
    'deleted',
    'discarded',
    'private_cloud_sync_enabled',
    'data_protection_level',
    'started_at',
    'finished_at',
)


def _row_state(row):
    return {key: row.get(key) for key in ROW_FIELDS}


def _job_state(job):
    # The pending drainer advances this retry wake every minute. It grants no
    # seal authority and must not invalidate an otherwise identical approval.
    return {key: value for key, value in job.items() if key != 'available_at'}


def _digest(value):
    def encode(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError('unsupported plan value')

    return hashlib.sha256(json.dumps(value, sort_keys=True, default=encode, separators=(',', ':')).encode()).hexdigest()


def _refused(job, row):
    if job.get('state') != 'record_pending' or not job.get('record_content_id'):
        return 'not_pending'
    if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
        return 'not_batch_owned'
    if row.get('record_upload_failed'):
        return 'upload_failed'
    if row.get('record_upload_sessions'):
        return 'upload_pending'
    if row.get('record_audio_closed'):
        return 'already_closed'
    if row.get('status') != 'completed':
        return 'not_completed'
    if row.get('deleted') or row.get('discarded') or not row.get('private_cloud_sync_enabled'):
        return 'privacy_refused'
    return None


def plan_seals(store, job_ids, storage_client, artifacts):
    entries = []
    for job_id in sorted(job_ids):
        entry = {'job_id': job_id, 'disposition': 'unavailable'}
        try:
            job = _job_state(store.run(lambda tx: tx.get('jobs', job_id)))
            uid, cid = job.get('owner_id'), job.get('conversation_id')
            if not uid or not cid or '/' in uid or '/' in cid:
                entries.append(entry)
                continue
            row = store.run(lambda tx: tx.get('conversations', f'{uid}/{cid}'))
            entry.update(job=job, row=_row_state(row))
            refusal = _refused(job, row)
            if refusal:
                entry['disposition'] = refusal
            else:
                seed = WorkItem(
                    job_id,
                    uid,
                    0,
                    'record:pending',
                    1,
                    Priority.FRESH,
                    conversation_id=cid,
                    privacy_generation=job['privacy_generation'],
                )
                artifacts.authorize(seed)
                chunks = list_audio_chunks(uid, cid, max_count=4096, require_archive=True)
                units = []
                iterator = retained_record_units(uid, cid, chunks, storage_client, artifacts.key_for_owner(uid))
                try:
                    for unit in iterator:
                        units.append(unit)
                        if len(units) > 128:
                            raise ValueError('retained capture unit budget exceeded')
                finally:
                    iterator.close()
                # Require both the current finish and the pending admission's
                # frozen finish. No missing timestamp can certify an old tail.
                validate_record_tail(units, row.get('finished_at'), require_finish=True)
                validate_record_tail(units, (job.get('record_snapshot') or {}).get('finished_at'), require_finish=True)
                entry.update(disposition='eligible', proof_sha256=_digest(units))
        except BatchPrivacyBlocked:
            entry['disposition'] = 'privacy_refused'
        except (ValueError, TypeError, AttributeError, KeyError):
            entry['disposition'] = 'proof_refused'
        except Exception:
            entry['disposition'] = 'read_error'
        entries.append(entry)
    plan = {'version': 1, 'namespace': store.namespace, 'entries': entries}
    return {**plan, 'plan_sha256': _digest(plan)}


def apply_seals(store, plan, approved_digest):
    body = {key: plan[key] for key in ('version', 'namespace', 'entries')}
    if approved_digest != plan['plan_sha256'] or _digest(body) != approved_digest:
        raise ValueError('fresh dry-run plan approval required')
    if store.namespace != plan['namespace']:
        raise ValueError('plan namespace changed')
    outcomes = Counter()
    for entry in plan['entries']:
        if entry['disposition'] != 'eligible':
            outcomes[entry['disposition']] += 1
            continue
        job = entry['job']
        uid, cid = job['owner_id'], job['conversation_id']
        ref = store.client.collection('users').document(uid).collection('conversations').document(cid)
        job_ref = store.client.collection(f'{store.namespace}_jobs').document(entry['job_id'])

        @firestore.transactional
        def commit(tx):
            current_job = job_ref.get(transaction=tx).to_dict() or {}
            row = ref.get(transaction=tx).to_dict() or {}
            if _job_state(current_job) != job or _row_state(row) != entry['row']:
                return 'state_changed'
            refusal = _refused(current_job, row)
            if refusal:
                return refusal
            assert_batch_write_allowed(
                store.client, tx, uid, conversation_ids=(cid,), expected_generation=job['privacy_generation']
            )
            tx.update(ref, {'record_audio_closed': True})
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
