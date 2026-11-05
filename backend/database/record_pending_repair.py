"""Revocation-only exit for aged pending records whose conversation is absent."""

import math

from google.cloud import firestore

from config import record_seal_repair as config
from config.record_audio import record_identity
from database._client import run_transactional
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed


def cancel_missing(store, uid, cid, *, now, preview=False):
    """Re-read absence, identity, age and privacy in one transaction; retain audio.

    Like cancel_fenced_recovery, a privacy rejection permits only revocation of
    work. Erasure retains ownership of deleting documents and stored artifacts.
    """
    content, segment = record_identity(uid, cid)
    ref = store.client.collection(f'{store.namespace}_jobs').document(segment)
    row_ref = store.client.collection('users').document(uid).collection('conversations').document(cid)

    @firestore.transactional
    def cancel(transaction):
        job = ref.get(transaction=transaction).to_dict() or {}
        row = row_ref.get(transaction=transaction)
        if not config.jobs_enabled():
            return 'disabled'
        if row.exists or job.get('state') != 'record_pending':
            return 'state_changed'
        if job.get('owner_id') != uid or job.get('conversation_id') != cid or job.get('record_content_id') != content:
            return 'state_changed'
        enqueued = job.get('enqueued_at')
        if (
            not isinstance(enqueued, (int, float))
            or isinstance(enqueued, bool)
            or not math.isfinite(enqueued)
            or now - enqueued < config.MISSING_CONVERSATION_SECONDS
        ):
            return 'not_aged'
        fenced = False
        try:
            assert_batch_write_allowed(
                store.client, transaction, uid, conversation_ids=(cid,), expected_generation=job['privacy_generation']
            )
        except BatchPrivacyBlocked:
            fenced = True
        if preview:
            return 'missing_cancel_eligible'
        # No receipt, projection, TTL or content write: cancellation is not a
        # claim of no speech and must never race erasure by recreating the row.
        transaction.update(ref, {'state': 'cancelled', 'merge_pending': False})
        return 'missing_cancelled_fenced' if fenced else 'missing_cancelled'

    result = run_transactional(store.client, cancel, transient=True)
    if result in {'missing_cancelled', 'missing_cancelled_fenced'}:
        from database.batch_pipeline_shadow_hook import mirror_refresh

        mirror_refresh(store.namespace, [('jobs', segment)])
    return result
