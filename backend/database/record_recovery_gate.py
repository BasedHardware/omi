"""Park late-audio recovery outside the states understood by old workers."""

from google.cloud import firestore

from config.record_audio import record_identity
from database._client import run_transactional
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked
from utils.sync.stage import collection_name

WAITING_STATE = 'record_recovery_waiting'
RECHECK_SECONDS = 60


def publication_ready(client, tx, namespace, uid, cid, original_job):
    """Read the original publication authorities before exposing runnable work."""
    content, _ = record_identity(uid, cid)
    intake = client.collection(namespace + '_intakes').document('bp_' + content).get(transaction=tx)
    if intake.exists:
        ledger = (
            client.collection('users')
            .document(uid)
            .collection(collection_name('sync_content_ledger'))
            .document(content)
            .get(transaction=tx)
            .to_dict()
            or {}
        )
        return ledger.get('status') == 'completed'
    return not original_job or original_job.get('state') == 'committed'


def promote(client, namespace, segment, now):
    """CAS once original output is settled; deliberately independent of lease mode.

    Old images query record_pending only. They cannot run this parked obligation
    during rollback; a current worker resumes promotion even with mode off.
    """
    ref = client.collection(namespace + '_jobs').document(segment)

    @firestore.transactional
    def commit(tx):
        job = ref.get(transaction=tx).to_dict() or {}
        if job.get('state') != WAITING_STATE or not job.get('lease_recovery') or job.get('available_at', 0) > now:
            return False
        uid, cid = job['owner_id'], job['conversation_id']
        _, original = record_identity(uid, cid)
        previous = client.collection(namespace + '_jobs').document(original).get(transaction=tx).to_dict() or {}
        ready = publication_ready(client, tx, namespace, uid, cid, previous)
        try:
            assert_batch_write_allowed(
                client, tx, uid, conversation_ids=(cid,), expected_generation=job['privacy_generation']
            )
        except BatchPrivacyBlocked:
            tx.update(ref, {'state': 'privacy_blocked'})
            return False
        tx.update(
            ref,
            {
                'state': 'record_pending' if ready else WAITING_STATE,
                'available_at': now if ready else now + RECHECK_SECONDS,
            },
        )
        return ready

    return run_transactional(client, commit, transient=True)
