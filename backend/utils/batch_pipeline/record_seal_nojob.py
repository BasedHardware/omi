"""One-time, digest-approved seal and registration of completed no-job captures.

Plans contain private identities in memory only. Public reports are aggregates.
Discovery scans at most 128 batch-live rows per page, including refused rows.
"""

from collections import Counter
import math
import time

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database._client import run_transactional
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreTransaction
from utils.batch_pipeline.live import record_identity, register_recording
from utils.batch_pipeline.record_seal_repair import plan_digest, seal_refusal, seal_row_state, retained_tail_proof

OPERATION = 'record-seal-nojob-v1'
REGISTRATION_FIELDS = ('source', 'language', 'client_device_id', 'client_platform', 'uses_custom_stt', 'external_data')


def validate_server_flags(flags):
    if not isinstance(flags, dict) or any(not isinstance(value, str) for value in flags.values()):
        raise ValueError('explicit serving-role flags required')
    if not (flags.get('K_SERVICE', '').strip() or flags.get('OMI_SYNC_STACK_ROLE', '').strip()):
        raise ValueError('explicit serving-role flags required')
    try:
        batch = float(flags['BATCH_PIPELINE_PERCENT'])
        retire = float(flags['BATCH_LIVE_STT_RETIRE_PERCENT'])
    except (KeyError, ValueError, TypeError):
        raise ValueError('explicit current serving ramps required') from None
    if not math.isfinite(batch) or not math.isfinite(retire) or not 0 <= retire <= batch <= 100:
        raise ValueError('explicit current serving ramps required')


def row_state(row):
    return {**seal_row_state(row), **{key: row.get(key) for key in REGISTRATION_FIELDS}}


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
    # End of a pass resets the private cursor. Continued bounded invocations
    # revisit matches that appeared behind the previous keyset cursor.
    return paths, paths[-1] if paths else None


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
    if row.get('uses_custom_stt') or row.get('data_protection_level') not in {None, 'standard', 'enhanced'}:
        return 'privacy_refused'
    tokens = row.get('record_upload_sessions')
    if tokens and (not isinstance(tokens, dict) or len(tokens) > 128):
        return 'upload_pending'
    # Never offer a producers-stopped escape hatch: token rows need pod proof.
    return seal_refusal(
        {'state': 'record_pending', 'record_content_id': 'candidate'}, row, producer_proof=producer_proof
    )


def registration(tx, uid, cid, row, server_flags):
    capture = RegistrationPlan(tx)
    if (
        not register_recording(
            uid,
            {**row, 'id': cid},
            now=0,
            transaction=capture,
            server_flags=server_flags,
        )
        or capture.job is None
    ):
        raise ValueError('registration refused')
    return capture.job


def plan_backfill(store, paths, storage_client, artifacts, *, server_flags, producer_proof=None):
    validate_server_flags(server_flags)
    if len(paths) > 128 or len(set(paths)) != len(paths):
        raise ValueError('bounded unique discovery page required')
    entries = []
    for path in sorted(paths):
        entry = {'path': path, 'disposition': 'unavailable'}
        try:
            uid, cid = conversation_path(path)
            _, job_id = record_identity(uid, cid)
            job_ref = store.client.collection(f'{store.namespace}_jobs').document(job_id)

            def read(tx):
                row = tx.get('conversations', f'{uid}/{cid}')
                if job_ref.get(transaction=tx.transaction).exists:
                    return row, None, 'already_registered'
                reason = refusal(row, producer_proof)
                if reason:
                    return row, None, reason
                return row, registration(tx, uid, cid, row, server_flags), None

            row, job, reason = store.run(read)
            if reason:
                entry['disposition'] = reason
            else:
                proof = retained_tail_proof(job, row, storage_client, artifacts)
                # Refusals grant no write authority. Do not bind their volatile
                # upload revisions into approval for unrelated completed rows.
                entry.update(row=row_state(row), job=job, disposition='eligible', proof_sha256=proof)
        except BatchPrivacyBlocked:
            entry['disposition'] = 'privacy_refused'
        except (ValueError, TypeError, AttributeError, KeyError):
            entry['disposition'] = 'proof_refused'
        except Exception:
            entry['disposition'] = 'read_error'
        entries.append(entry)
    body = {
        'operation': OPERATION,
        'namespace': store.namespace,
        'entries': entries,
        'producer_proof': producer_proof,
        'server_flags': server_flags,
    }
    return {**body, 'plan_sha256': plan_digest(body)}


def apply_backfill(store, plan, approved_digest):
    body = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if approved_digest != plan['plan_sha256'] or plan_digest(body) != approved_digest:
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
        job_ref = store.client.collection(f'{store.namespace}_jobs').document(job_id)
        row_ref = store.client.collection('users').document(uid).collection('conversations').document(cid)
        now = time.time()

        @firestore.transactional
        def commit(raw):
            tx = FirestoreTransaction(store.client, store.namespace, raw)
            row = tx.get('conversations', f'{uid}/{cid}')
            if job_ref.get(transaction=raw).exists:
                return 'already_registered'
            if row_state(row) != entry['row']:
                return 'state_changed'
            reason = refusal(row, plan['producer_proof'])
            if reason:
                return reason
            tx.check_privacy(uid, (cid,), expected_generation=entry['job']['privacy_generation'])
            job = registration(tx, uid, cid, row, plan['server_flags'])
            if job != entry['job']:
                return 'state_changed'
            tx.put('jobs', job_id, {**job, 'enqueued_at': now, 'available_at': now})
            tx.flush()  # Includes the canonical privacy fence, before any writes.
            raw.update(
                row_ref,
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
