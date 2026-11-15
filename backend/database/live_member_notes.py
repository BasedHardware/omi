"""One automatic live-member fallback attempt per finalization/content revision.

The permit is consumed before paid work. A crash or provider failure cannot buy
it again; episode closure or explicit user processing exits this extra budget.
"""

from datetime import datetime, timezone

from google.cloud import firestore

from database._client import get_firestore_client


def _claim(transaction, job_ref, conversation_ref, fence, revision, now):
    job = job_ref.get(transaction=transaction).to_dict() or {}
    row = conversation_ref.get(transaction=transaction).to_dict() or {}
    identity = {'finalization': job.get('finalization_revision'), 'content': revision}
    if (
        job.get('status') != 'leased'
        or (job.get('dispatch_generation'), job.get('lease_epoch')) != fence[1:]
        or not job.get('lease_expires_at')
        or job['lease_expires_at'] <= now
        or job.get('uid') != conversation_ref.parent.parent.id
        or job.get('conversation_id') != conversation_ref.id
        or row.get('finalization_job_id') != fence[0]
        or row.get('finalization_revision') != identity['finalization']
        or row.get('sync_content_revision') != revision
        or row.get('status') != 'processing'
        or any(row.get(k) for k in ('deleted', 'discarded', 'sync_merged_into'))
        or row.get('live_member_notes_fallback_revision') == identity
    ):
        return False
    transaction.update(conversation_ref, {'live_member_notes_fallback_revision': identity})
    return True


def claim(uid, conversation_id, fence, revision, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return firestore.transactional(_claim)(
        client.transaction(),
        client.collection('conversation_finalization_jobs').document(fence[0]),
        client.collection('users').document(uid).collection('conversations').document(conversation_id),
        fence,
        revision,
        datetime.now(timezone.utc),
    )
