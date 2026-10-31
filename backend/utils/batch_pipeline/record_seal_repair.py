"""Exact-job record seal repair. Plans stay private; public reports are aggregates."""

from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from typing import Any

from google.cloud import firestore
from config.record_seal_rules import overlap_trim_enabled, upload_failed_repair_enabled

from database._client import run_transactional
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.live import retained_record_units
from utils.batch_pipeline.record_barrier import validate_record_tail
from utils.batch_pipeline.record_producer_proof import producer_tokens_dead
from utils.batch_pipeline.record_seal_reasons import proof_reason, proof_diagnostics, tail_gap_bucket, TailGapRefusal
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


def seal_refusal(job, row, *, producer_proof=None, producers_stopped=False, repair_upload_failed=False):
    if job.get('state') != 'record_pending' or not job.get('record_content_id'):
        return 'not_pending'
    if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
        return 'not_batch_owned'
    if row.get('record_upload_failed') and not (repair_upload_failed and upload_failed_repair_enabled()):
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


def retained_tail_proof(job, row, storage_client, artifacts, *, check_budget=lambda: None, diagnostics=None):
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
    key = artifacts.key_for_owner(uid)
    precheck_record_tail(uid, cid, chunks, storage_client, key, row, job, check_budget=check_budget)
    units = []
    options = {'diagnostics': diagnostics} if diagnostics is not None else {}
    iterator = retained_record_units(uid, cid, chunks, storage_client, key, **options)
    try:
        for unit in iterator:
            check_budget()
            units.append(unit)
            if len(units) > 128:
                raise ValueError('retained capture unit budget exceeded')
    finally:
        iterator.close()
    if not units:
        raise ValueError('retained capture not durable yet')
    validate_repair_tail(units, row.get('finished_at'))
    validate_repair_tail(units, (job.get('record_snapshot') or {}).get('finished_at'))
    check_budget()
    return plan_digest(units)


def validate_repair_tail(units, finish, *, diagnostic_end=None):
    """Keep validation unchanged; carry only a closed bucket on tail refusal."""
    try:
        validate_record_tail(units, finish, require_finish=True)
    except ValueError as error:
        if proof_reason(error) == 'tail_lagging':
            end = units[-1][0] + units[-1][1] if diagnostic_end is None else diagnostic_end
            raise TailGapRefusal(tail_gap_bucket(finish, end)) from None
        raise


def precheck_record_tail(uid, cid, chunks, storage_client, key, row, job, *, check_budget=lambda: None):
    """Refusal-only necessary condition; passing still requires the full walk.

    A contained final object can end before the union. Under earlier-wins
    trimming a singleton can refuse only a singleton listing; multi-object
    short tails require the full walk. Keep rounding uncertainty in the walk.
    """
    if not chunks:
        return
    tail = None
    iterator = retained_record_units(uid, cid, chunks[-1:], storage_client, key)
    try:
        for tail in iterator:
            check_budget()
    finally:
        iterator.close()
    if tail is None:
        return
    end = tail[0] + tail[1]
    if not math.isfinite(end):
        return
    # Be conservative about sample rounding and floating point addition in the
    # full walk. This can only send an uncertain case back to existing proof.
    ceiling = end + 1 / 16000 + 4 * math.ulp(end)
    for finish in (row.get('finished_at'), (job.get('record_snapshot') or {}).get('finished_at')):
        try:
            validate_record_tail([tail], finish, require_finish=True)
        except ValueError:
            # With earlier-wins trimming, the final object may be wholly
            # contained in an earlier, longer object. Its singleton end is no
            # longer an upper bound on the union. Only the full walk can refuse.
            if len(chunks) > 1 and overlap_trim_enabled():
                return
            # Diagnose the actual decoded end, never the conservative ceiling.
            validate_repair_tail([(ceiling, 0, [])], finish, diagnostic_end=end)


def plan_seals(
    store,
    job_ids,
    storage_client,
    artifacts,
    *,
    producer_proof=None,
    producers_stopped=False,
    check_budget=lambda: None,
    repair_upload_failed=False,
):
    entries = []
    for job_id in sorted(job_ids):
        check_budget()
        entry = {'job_id': job_id, 'disposition': 'unavailable'}
        diagnostics = {}
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
            refusal = seal_refusal(
                job,
                row,
                producer_proof=producer_proof,
                producers_stopped=producers_stopped,
                repair_upload_failed=repair_upload_failed,
            )
            if refusal:
                entry['disposition'] = refusal
            else:
                proof = retained_tail_proof(
                    {**job, 'segment_id': job_id},
                    row,
                    storage_client,
                    artifacts,
                    check_budget=check_budget,
                    diagnostics=diagnostics,
                )
                entry.update(disposition='eligible', proof_sha256=proof, **diagnostics)
        except BatchPrivacyBlocked:
            entry['disposition'] = 'privacy_refused'
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            entry['disposition'] = 'proof_refused'
            entry.update(proof_diagnostics(error))
        except Exception:
            entry['disposition'] = 'read_error'
        entry.update(diagnostics)
        entries.append(entry)
    check_budget()
    plan = {
        'version': 1,
        'namespace': store.namespace,
        'entries': entries,
        'producer_proof': producer_proof,
        'producers_stopped': producers_stopped,
        'repair_upload_failed': repair_upload_failed,
        'overlap_trim_enabled': overlap_trim_enabled(),
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
        if plan.get('overlap_trim_enabled') and not overlap_trim_enabled():
            outcomes['state_changed'] += 1
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
                current_job,
                row,
                producer_proof=plan['producer_proof'],
                producers_stopped=plan['producers_stopped'],
                repair_upload_failed=plan.get('repair_upload_failed', False),
            )
            if refusal:
                return refusal
            assert_batch_write_allowed(
                store.client, tx, uid, conversation_ids=(cid,), expected_generation=job['privacy_generation']
            )
            patch: dict[str, Any] = {'record_audio_closed': True}
            if row.get('record_upload_sessions'):
                patch['record_upload_sessions'] = {}  # Only the exact proven-dead map.
            if row.get('record_upload_failed'):
                patch['record_upload_failed'] = False
            check_budget()
            tx.update(ref, patch)
            return 'upload_failed_cleared' if row.get('record_upload_failed') else 'sealed'

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
