"""Per-unit handoff; ordinary worker tokens and upload ownership never transfer."""

from dataclasses import asdict
from typing import Any
from uuid import uuid4

from database.batch_pipeline_projection_protocol import ProjectionBlocked, normalized_binding
from database.sync_ledger import batch_projection_ledger_owner_matches
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.scheduler import owner_key


class RecoveryStore:
    def __init__(self, store: Any):
        self.store = store

    def checked(self, tx, segment_id):
        job = tx.get('jobs', segment_id)
        if not job or not job.get('projection_binding'):
            raise ProjectionBlocked('recovery intake binding required')
        binding = normalized_binding(job['projection_binding'])
        ids = set(job.get('conversation_ids') or [])
        ids.update(value for value in (job.get('conversation_id'), binding.target_conversation_id) if value)
        tx.check_privacy(binding.owner_id, ids, binding.privacy_generation)
        ledger = tx.get('content', f'{binding.owner_id}/{binding.content_id}')
        if (
            job.get('owner_id') != binding.owner_id
            or job.get('privacy_generation') != binding.privacy_generation
            or (job.get('recovery') and job['recovery'].get('privacy_generation') != binding.privacy_generation)
            or segment_id not in binding.segment_ids
            or ledger.get('dispatch_protocol') != 'batch_v1'
            or ledger.get('batch_pipeline')
            != {'protocol_version': 1, 'namespace': self.store.namespace, 'segment_ids': list(binding.segment_ids)}
            or not batch_projection_ledger_owner_matches(ledger, binding.job_id, binding.run_token, binding.run_epoch)
        ):
            raise ProjectionBlocked('recovery content owner lost')
        return job, binding

    def prepare(self, segment_id, owner_id, now):
        # Generated outside the retryable transaction; a lost reply is reconciled
        # by rereading this same intent, never by issuing a second provider call.
        token = uuid4().hex

        def commit(tx):
            job, binding = self.checked(tx, segment_id)
            result = tx.get('results', segment_id)
            if (
                binding.owner_id != owner_id
                or job.get('state') != 'quarantined'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
                or job.get('result')
                or result
            ):
                return None
            if job.get('recovery_state') == 'held' and not job.get('recovery'):
                job['recovery'] = {
                    'token': token,
                    'epoch': 1,
                    'privacy_generation': binding.privacy_generation,
                    'prepared_at': now,
                }
                job['recovery_state'] = 'prepared'
                tx.put('jobs', segment_id, job)
            return job if job.get('recovery_state') in {'prepared', 'running'} else None

        return self.store.run(commit)

    def start(self, segment_id, token, now):
        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            result = tx.get('results', segment_id)
            if (
                job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'prepared'
                or job.get('recovery', {}).get('token') != token
                or job.get('result')
                or result
                or job.get('token')
                or job.get('lease_until', 0) > now
            ):
                return False
            job['recovery_state'] = 'running'
            job['recovery']['started_at'] = now
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def settle(self, segment_id, token, now, result_uri=None):
        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            if (
                job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'running'
                or job.get('recovery', {}).get('token') != token
                or job.get('result')
                or existing
            ):
                return False
            if result_uri is None:
                job.update(recovery_state='failed_held')
            else:
                owner = tx.get('owners', owner_key(job['owner_id']))
                job.update(
                    result=asdict(WorkResult(segment_id, result_uri)),
                    state='result_ready',
                    merge_pending=True,
                    recovery_state='recovered',
                )
                owner['revision'] = owner.get('revision', 0) + 1
                tx.put('owners', owner_key(job['owner_id']), owner)
            job['recovery']['settled_at'] = now
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)


def recovery_candidates(client, namespace: str, owner_id: str, limit: int = 10):
    """Only unattempted or reconcilable units; failed STT never hot-loops."""
    return [
        doc.id
        for doc in (
            client.collection(f'{namespace}_jobs')
            .where('owner_id', '==', owner_id)
            .where('recovery_state', 'in', ['held', 'prepared', 'running'])
            .limit(max(1, min(limit, 10)))
            .stream()
        )
    ]


def cancel_fenced_recovery(store, segment_id):
    """Revocation-only write, allowed after privacy rejects ordinary job writes."""
    from google.cloud import firestore
    from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed

    ref = store.client.collection(f'{store.namespace}_jobs').document(segment_id)

    @firestore.transactional
    def cancel(transaction):
        job = ref.get(transaction=transaction).to_dict() or {}
        if not job or not job.get('recovery'):
            return False
        binding = normalized_binding(job['projection_binding'])
        ids = [value for value in (job.get('conversation_id'), binding.target_conversation_id) if value]
        ids.extend(job.get('conversation_ids') or [])
        try:
            assert_batch_write_allowed(
                store.client,
                transaction,
                binding.owner_id,
                conversation_ids=ids,
                expected_generation=binding.privacy_generation,
            )
        except BatchPrivacyBlocked:
            transaction.update(ref, {'recovery_state': 'cancelled'})
            return True
        return False

    return cancel(store.client.transaction())
