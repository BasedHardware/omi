"""Bounded, digest-approved recovery of stale batch-live in-progress captures.

Private plans stay in memory. Reports contain aggregate counts and audio seconds.
No storage deletion is performed; uncertain custody exits by operator re-run.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import time
import hashlib
import json
import math

from google.cloud import firestore

from config.refactor_modes import batch_live_orphan_repair_enabled
from config.server_batch import owned, proven_empty
from database._client import run_transactional
from database import conversation_finalization_jobs as jobs_db
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from database.batch_pipeline_store import FirestoreTransaction
from utils.batch_pipeline.live import record_identity, retained_record_units
from utils.batch_pipeline.record_seal_nojob import (
    conversation_path,
    discover as discover,
    registration,
    validate_server_flags,
)
from utils.batch_pipeline.record_seal_repair import plan_digest
from utils.conversations.lifecycle import delete_empty_recording_conversation, complete_orphan_batch_capture
from utils.other.storage import list_audio_chunks

OPERATION = 'batch-live-inprogress-orphan-repair-v1'
CAPTURE_PRIVACY_FIELDS = ('uses_custom_stt', 'private_cloud_sync_enabled', 'data_protection_level')
EXITS = {
    'register': 'normal_batch_pipeline',
    'registered': 'normal_batch_pipeline',
    'already_registered': 'normal_batch_pipeline',
    'delete_empty': 'expired_lease_empty_cleanup',
    'empty_deleted': 'noise_discard_terminal',
    'upload_pending': 'producer_token_lease_repair',
    'privacy_skipped': 'operator_rerun_after_consent',
    'not_candidate': 'existing_lifecycle_owner',
    'barrier_mismatch': 'operator_review',
    'lease_unknown': 'operator_review',
    'lease_active': 'quiet_check_after_lease',
    'storage_empty_received': 'operator_rerun',
    'storage_has_audio': 'operator_rerun',
    'proof_refused': 'operator_rerun',
    'read_error': 'operator_rerun',
    'state_changed': 'operator_rerun',
    'write_error': 'operator_rerun',
    'disabled': 'operator_rerun_after_enablement',
}


def row_state(row):
    # Bind the full snapshot: a content/custody/registration change must invalidate
    # approval, including encrypted content and future producer metadata.
    def encode(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, bytes):
            return {'bytes_sha256': hashlib.sha256(value).hexdigest()}
        raise TypeError('unsupported row value')

    return hashlib.sha256(json.dumps(row, sort_keys=True, default=encode, separators=(',', ':')).encode()).hexdigest()


def capture_privacy_refused(row):
    return (
        row.get('uses_custom_stt')
        or not row.get('private_cloud_sync_enabled')
        or row.get('data_protection_level') not in {None, 'standard', 'enhanced'}
    )


def candidate_refusal(row, now):
    created = row.get('created_at')
    if not isinstance(created, datetime):
        return 'not_candidate'
    created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
    if (
        row.get('record_lane_owner') != 'batch_live_v1'
        or row.get('status') != 'in_progress'
        or created > now - timedelta(hours=2)
        or any(row.get(k) for k in ('deleted', 'discarded', 'is_locked', 'sync_merged_into', 'finalization_job_id'))
    ):
        return 'not_candidate'
    if not owned(row):
        return 'barrier_mismatch'
    if capture_privacy_refused(row):
        return 'privacy_skipped'
    if row.get('record_upload_sessions'):
        return 'upload_pending'
    if row.get('record_upload_failed') or row.get('record_audio_partial'):
        return 'barrier_mismatch'
    return None


def owner_privacy_read(tx, uid, expected_generation=None):
    snapshots = {}
    generation = assert_batch_write_allowed(
        tx.client, tx.transaction, uid, expected_generation=expected_generation, snapshots=snapshots
    )
    if not snapshots['user'].get('private_cloud_sync_enabled', True):
        raise BatchPrivacyBlocked('recording_privacy_changed')
    return generation


def privacy_read(tx, uid, conversation_ids=(), expected_generation=None):
    owner_privacy_read(tx, uid, expected_generation)
    conversation_ids = tuple(conversation_ids)
    for cid in conversation_ids:
        if not capture_privacy_read(tx, uid, cid):
            raise BatchPrivacyBlocked('conversation_deleted', conversation_id=cid)
    # Full snapshots force the live authority walk: dry-run must not mint a
    # privacy-cache token even when generation memoization is serving.
    snapshots = {}
    generation = assert_batch_write_allowed(
        tx.client,
        tx.transaction,
        uid,
        conversation_ids=conversation_ids,
        expected_generation=expected_generation,
        snapshots=snapshots,
    )
    return generation


def capture_privacy_read(tx, uid, cid):
    # Call only after owner authority. Never load content or a job for a capture
    # whose projected privacy fields refuse processing; keep this uncached so
    # every authorizing transaction observes changes in capture consent.
    snapshot = (
        tx.client.collection('users')
        .document(uid)
        .collection('conversations')
        .document(cid)
        .get(transaction=tx.transaction, field_paths=list(CAPTURE_PRIVACY_FIELDS))
    )
    if not snapshot.exists:
        return False
    if capture_privacy_refused(snapshot.to_dict() or {}):
        raise BatchPrivacyBlocked('recording_privacy_changed', conversation_id=cid)
    return True


class RegistrationReads:
    """Read-only canonical registration adapter, including live privacy reads."""

    def __init__(self, tx, uid, cid):
        owner_privacy_read(tx, uid)
        if not capture_privacy_read(tx, uid, cid):
            raise BatchPrivacyBlocked('conversation_deleted', conversation_id=cid)
        self.tx = tx

    def get(self, *args):
        return self.tx.get(*args)

    def check_privacy(self, *args, **kwargs):
        return privacy_read(self.tx, *args, **kwargs)


def read_candidate(tx, uid, cid, now):
    owner_privacy_read(tx, uid)
    if not capture_privacy_read(tx, uid, cid):
        return {}, None, 'not_candidate'
    row = tx.get('conversations', f'{uid}/{cid}')
    _, job_id = record_identity(uid, cid)
    # exists, rather than truthiness: even an empty job cannot be overwritten.
    job = tx.client.collection(f'{tx.namespace}_jobs').document(job_id).get(transaction=tx.transaction)
    if job.exists:
        return row, None, 'already_registered'
    reason = candidate_refusal(row, now)
    if reason:
        return row, None, reason
    generation = privacy_read(tx, uid, (cid,))
    # Closed, received custody exits by registration even after old session
    # metadata expires. Only destructive empty cleanup needs the lease fence.
    if row.get('server_batch_audio_received') is True:
        if row.get('record_audio_closed') is not True or row.get('server_batch_audio_closed') is not True:
            return row, None, 'barrier_mismatch'
        return row, generation, None
    if not proven_empty(row):
        return row, None, 'barrier_mismatch'
    ref = tx.client.collection('users').document(uid)
    expiry = jobs_db.recording_session_lease_expiry(
        tx.transaction, ref.collection('recording_sessions'), uid, cid, row, now
    )
    if expiry is None:
        return row, None, 'lease_unknown'
    if expiry > now:
        return row, None, 'lease_active'
    return row, generation, None


def retained_proof(store, uid, cid, generation, storage_client, artifacts):
    store.run(lambda tx: privacy_read(tx, uid, (cid,), expected_generation=generation))
    chunks = list_audio_chunks(
        uid, cid, max_count=4096, require_archive=True, include_raw=True, client=storage_client, source_metadata=True
    )
    if not chunks:
        return {'sha256': plan_digest([]), 'audio_seconds': 0.0, 'stt_seconds': 0.0}
    units = []
    iterator = retained_record_units(uid, cid, chunks, storage_client, artifacts.key_for_owner(uid))
    try:
        for start, duration, refs in iterator:
            if not (type(start) in (int, float) and type(duration) in (int, float)):
                raise ValueError('invalid retained span')
            units.append((start, duration, refs))
            if len(units) > 128:
                raise ValueError('retained unit budget exceeded')
    finally:
        iterator.close()
    if not units or any(not math.isfinite(s + d) or d <= 0 for s, d, _ in units):
        raise ValueError('invalid retained span')
    frames = [ref['frames'] for _, _, refs in units for ref in refs]
    if not frames or any(type(value) is not int or value <= 0 for value in frames):
        raise ValueError('retained sample spans required')
    return {
        'sha256': plan_digest(units),
        'audio_seconds': sum(frames) / 16000,
        'stt_seconds': sum(d for _, d, _ in units),
        'start': min(s for s, _, _ in units),
        'end': max(s + d for s, d, _ in units),
    }


def window_patch(proof):
    return {
        'server_batch_audio_start': proof['start'],
        'server_batch_audio_end': proof['end'],
        'started_at': datetime.fromtimestamp(proof['start'], timezone.utc),
        'finished_at': datetime.fromtimestamp(proof['end'], timezone.utc),
        'has_content': True,
        'server_batch_audio_received': True,
    }


def disposition(row, proof):
    if row.get('server_batch_audio_received') is True:
        if row.get('record_audio_closed') is not True or row.get('server_batch_audio_closed') is not True:
            return 'barrier_mismatch'
        return 'register' if proof['audio_seconds'] else 'storage_empty_received'
    if proof['audio_seconds']:
        return 'storage_has_audio'
    if (
        proven_empty(row)
        and not row.get('has_content')
        and not row.get('audio_files')
        and row.get('server_batch_audio_start') is None
        and row.get('server_batch_audio_end') is None
    ):
        return 'delete_empty'
    return 'barrier_mismatch'


def plan_repair(store, paths, storage_client, artifacts, *, server_flags, now=None):
    validate_server_flags(server_flags)
    if len(paths) > 128 or len(set(paths)) != len(paths):
        raise ValueError('bounded unique discovery page required')
    now = now or datetime.now(timezone.utc)
    entries = []
    for path in sorted(paths):
        entry = {'path': path, 'disposition': 'read_error'}
        try:
            uid, cid = conversation_path(path)
            row, generation, reason = store.run(lambda tx: read_candidate(tx, uid, cid, now))
            if reason:
                entry['disposition'] = reason
            else:
                proof = retained_proof(store, uid, cid, generation, storage_client, artifacts)
                action = disposition(row, proof)
                entry.update(disposition=action)
                if (
                    row.get('server_batch_audio_received') is True
                    and row.get('record_audio_closed') is True
                    and row.get('server_batch_audio_closed') is True
                ):
                    entry['audio_seconds'] = proof['audio_seconds']
                    entry['stt_seconds'] = proof['stt_seconds']
                if action in {'register', 'delete_empty'}:
                    entry.update(row_sha256=row_state(row), privacy_generation=generation, proof=proof)
                    if action == 'register':
                        entry['job'] = store.run(
                            lambda tx: registration(
                                RegistrationReads(tx, uid, cid), uid, cid, {**row, **window_patch(proof)}, server_flags
                            )
                        )
        except BatchPrivacyBlocked:
            entry['disposition'] = 'privacy_skipped'
        except (ValueError, TypeError, KeyError):
            entry['disposition'] = 'proof_refused'
        except Exception:
            entry['disposition'] = 'read_error'
        entry.update(exit=EXITS[entry['disposition']])
        if entry['disposition'] not in {'register', 'delete_empty', 'already_registered', 'not_candidate'}:
            entry['last_failure_code'] = entry['disposition']
        entries.append(entry)
    body = {'operation': OPERATION, 'namespace': store.namespace, 'server_flags': server_flags, 'entries': entries}
    return {**body, 'plan_sha256': plan_digest(body)}


class RepairRefused(ValueError):
    pass


def apply_repair(store, plan, approved_digest, storage_client, artifacts):
    body = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if approved_digest != plan['plan_sha256'] or plan_digest(body) != approved_digest:
        raise ValueError('fresh dry-run plan approval required')
    if plan['operation'] != OPERATION or plan['namespace'] != store.namespace or len(plan['entries']) > 128:
        raise ValueError('plan target changed')
    outcomes = Counter()
    for entry in plan['entries']:
        action = entry['disposition']
        if action not in {'register', 'delete_empty'}:
            outcomes[action] += 1
            continue
        if not batch_live_orphan_repair_enabled():
            outcomes['disabled'] += 1
            continue
        uid, cid = conversation_path(entry['path'])
        try:
            # Reauthorize before storage, then re-prove the exact immutable spans.
            row, generation, reason = store.run(lambda tx: read_candidate(tx, uid, cid, datetime.now(timezone.utc)))
            if reason:
                outcomes[reason] += 1
                continue
            if row_state(row) != entry['row_sha256'] or generation != entry['privacy_generation']:
                outcomes['state_changed'] += 1
                continue
            if retained_proof(store, uid, cid, generation, storage_client, artifacts) != entry['proof']:
                outcomes['state_changed'] += 1
                continue

            def guard(raw, current):
                tx = FirestoreTransaction(store.client, store.namespace, raw)
                fresh, gen, why = read_candidate(tx, uid, cid, datetime.now(timezone.utc))
                if not batch_live_orphan_repair_enabled():
                    raise RepairRefused('disabled')
                if why:
                    raise RepairRefused(why)
                if (
                    row_state(fresh) != entry['row_sha256']
                    or gen != generation
                    or disposition(fresh, entry['proof']) != action
                ):
                    raise RepairRefused('state_changed')
                return tx

            if action == 'delete_empty':
                deleted = delete_empty_recording_conversation(
                    uid,
                    cid,
                    (row.get('external_data') or {}).get('recording_session_id'),
                    recovery_cutoff=datetime.now(timezone.utc) - timedelta(hours=2),
                    require_expired_recording_lease=True,
                    firestore_client=store.client,
                    allow_empty_server_batch=True,
                    transaction_guard=guard,
                )
                result = 'empty_deleted' if deleted else 'state_changed'
            else:

                @firestore.transactional
                def commit(raw):
                    tx = guard(raw, row)
                    patch = window_patch(entry['proof'])
                    job = registration(
                        RegistrationReads(tx, uid, cid), uid, cid, {**row, **patch}, plan['server_flags']
                    )
                    if job != entry['job']:
                        return 'state_changed'
                    now = time.time()
                    tx.put('jobs', job['segment_id'], {**job, 'enqueued_at': now, 'available_at': now})
                    tx.flush()  # Complete every privacy read before the first write.
                    complete_orphan_batch_capture(
                        raw,
                        store.client.collection('users').document(uid).collection('conversations').document(cid),
                        row,
                        patch,
                        now=datetime.fromtimestamp(now, timezone.utc),
                    )
                    return 'registered'

                result = run_transactional(store.client, commit, transient=True)
            outcomes[result] += 1
        except BatchPrivacyBlocked:
            outcomes['privacy_skipped'] += 1
        except RepairRefused as error:
            outcomes[str(error)] += 1
        except Exception:
            outcomes['write_error'] += 1
    return dict(sorted(outcomes.items()))


def summary(plan):
    counts = Counter(entry['disposition'] for entry in plan['entries'])
    return {
        'operation': OPERATION,
        'plan_sha256': plan['plan_sha256'],
        'count': len(plan['entries']),
        'dispositions': dict(sorted(counts.items())),
        'exits': {key: EXITS[key] for key in sorted(counts)},
        'skipped': sum(n for key, n in counts.items() if key not in {'register', 'delete_empty'}),
        'sealed_received_audio_seconds': sum(entry.get('audio_seconds', 0.0) for entry in plan['entries']),
        'sealed_received_stt_seconds': sum(entry.get('stt_seconds', 0.0) for entry in plan['entries']),
    }
