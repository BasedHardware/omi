"""One-time, digest-approved seal and registration of completed no-job captures.

Plans contain private identities in memory only. Public reports are aggregates.
Discovery scans at most 128 batch-live rows per page, including refused rows.
"""

from collections import Counter
import time

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database._client import run_transactional
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreTransaction
from utils.batch_pipeline.live import record_identity, register_recording
from utils.batch_pipeline.record_seal_repair import _digest, _refused, _row_state, retained_tail_proof

OPERATION = 'record-seal-nojob-v1'
REGISTRATION_FIELDS = ('source', 'language', 'client_device_id', 'client_platform', 'uses_custom_stt', 'external_data')


def row_state(row):
    return {**_row_state(row), **{key: row.get(key) for key in REGISTRATION_FIELDS}}


def conversation_path(value):
    parts = value.split('/') if isinstance(value, str) else []
    if len(parts) != 4 or parts[0] != 'users' or parts[2] != 'conversations' or not parts[1] or not parts[3]:
        raise ValueError('invalid conversation cursor')
    return parts[1], parts[3]


def discover(client, *, limit=128, after=None):
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('discovery limit must be 1..128')
    query = (
        client.collection_group('conversations')
        .where(filter=FieldFilter('record_lane_owner', '==', 'batch_live_v1'))
        .order_by('__name__')
        .select(())
        .limit(limit)
    )
    if after is not None:
        conversation_path(after)
        query = query.start_after({'__name__': client.document(after)})
    paths = [snapshot.reference.path for snapshot in query.stream()]
    for path in paths:
        conversation_path(path)
    return paths, paths[-1] if paths else after


class RegistrationPlan:
    """Run the canonical registration logic without buffering any write."""

    def __init__(self, transaction):
        self.transaction = transaction
        self.job = None

    def get(self, *args):
        return self.transaction.get(*args)

    def check_privacy(self, *args, **kwargs):
        return self.transaction.check_privacy(*args, **kwargs)

    def put(self, table, key, value):
        if table != 'jobs' or self.job is not None:
            raise ValueError('unexpected registration writes')
        self.job = value


def refusal(row, producer_proof):
    if row.get('record_lane_owner') != 'batch_live_v1':
        return 'not_batch_owned'
    if row.get('uses_custom_stt'):
        return 'privacy_refused'
    # Never offer a producers-stopped escape hatch: token rows need pod proof.
    return _refused({'state': 'record_pending', 'record_content_id': 'candidate'}, row, producer_proof=producer_proof)


def registration(tx, uid, cid, row):
    capture = RegistrationPlan(tx)
    if not register_recording(uid, {**row, 'id': cid}, now=0, transaction=capture) or capture.job is None:
        raise ValueError('registration refused')
    return capture.job


def plan_backfill(store, paths, storage_client, artifacts, *, producer_proof=None):
    if len(paths) > 128 or len(set(paths)) != len(paths):
        raise ValueError('bounded unique discovery page required')
    entries = []
    for path in sorted(paths):
        entry = {'path': path, 'disposition': 'unavailable'}
        try:
            uid, cid = conversation_path(path)
            _, job_id = record_identity(uid, cid)

            def read(tx):
                row = tx.get('conversations', f'{uid}/{cid}')
                if tx._ref('jobs', job_id).get(transaction=tx.transaction).exists:
                    return row, None, 'already_registered'
                reason = refusal(row, producer_proof)
                if reason:
                    return row, None, reason
                return row, registration(tx, uid, cid, row), None

            row, job, reason = store.run(read)
            entry['row'] = row_state(row)
            if reason:
                entry['disposition'] = reason
            else:
                proof = retained_tail_proof(job, row, storage_client, artifacts)
                entry.update(job=job, disposition='eligible', proof_sha256=proof)
        except BatchPrivacyBlocked:
            entry['disposition'] = 'privacy_refused'
        except (ValueError, TypeError, AttributeError, KeyError):
            entry['disposition'] = 'proof_refused'
        except Exception:
            entry['disposition'] = 'read_error'
        entries.append(entry)
    body = {'operation': OPERATION, 'namespace': store.namespace, 'entries': entries, 'producer_proof': producer_proof}
    return {**body, 'plan_sha256': _digest(body)}


def apply_backfill(store, plan, approved_digest):
    body = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if approved_digest != plan['plan_sha256'] or _digest(body) != approved_digest:
        raise ValueError('fresh dry-run plan approval required')
    if plan['namespace'] != store.namespace or plan['operation'] != OPERATION:
        raise ValueError('plan target changed')
    outcomes = Counter()
    for entry in plan['entries']:
        if entry['disposition'] != 'eligible':
            outcomes[entry['disposition']] += 1
            continue
        uid, cid = conversation_path(entry['path'])
        job_id = entry['job']['segment_id']
        now = time.time()

        @firestore.transactional
        def commit(raw):
            tx = FirestoreTransaction(store.client, store.namespace, raw)
            row = tx.get('conversations', f'{uid}/{cid}')
            if tx._ref('jobs', job_id).get(transaction=tx.transaction).exists:
                return 'already_registered'
            if row_state(row) != entry['row']:
                return 'state_changed'
            reason = refusal(row, plan['producer_proof'])
            if reason:
                return reason
            tx.check_privacy(uid, (cid,), expected_generation=entry['job']['privacy_generation'])
            job = registration(tx, uid, cid, row)
            if job != entry['job']:
                return 'state_changed'
            tx.put('jobs', job_id, {**job, 'enqueued_at': now, 'available_at': now})
            tx.flush()  # Includes the canonical privacy fence, before any writes.
            raw.update(
                tx._ref('conversations', f'{uid}/{cid}'),
                {
                    'record_upload_sessions': {},
                    'record_audio_closed': True,
                },
            )
            return 'sealed_registered'

        try:
            outcomes[run_transactional(store.client, commit, transient=True)] += 1
        except BatchPrivacyBlocked:
            outcomes['privacy_refused'] += 1
        except Exception:
            outcomes['write_error'] += 1
    return dict(sorted(outcomes.items()))


def summary(plan):
    return {
        'operation': OPERATION,
        'plan_sha256': plan['plan_sha256'],
        'count': len(plan['entries']),
        'dispositions': dict(sorted(Counter(entry['disposition'] for entry in plan['entries']).items())),
    }
