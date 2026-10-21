"""Restrictive lease revocation for privacy-fenced work, without resurrection."""

from typing import Any
from google.cloud import firestore
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed


def quarantine_fenced(client: Any, namespace: str, segment_id: str, now: float) -> bool:
    """Remove only fenced detached leases/retries from recovery scans.

    Rechecks the fence in this transaction. It cannot clear the privacy fence,
    requeue content, change its immutable identity or publish any result.
    D's erasure outbox retains ownership of audio and ordered-log cleanup.
    """
    reference = client.collection(f'{namespace}_jobs').document(segment_id)

    @firestore.transactional
    def revoke(transaction):
        job = reference.get(transaction=transaction).to_dict() or {}
        if job.get('state') not in {'leased', 'retry'}:
            return False
        try:
            assert_batch_write_allowed(
                client,
                transaction,
                job['owner_id'],
                conversation_ids=(job['conversation_id'],) if job.get('conversation_id') else (),
                expected_generation=job.get('privacy_generation'),
            )
        except BatchPrivacyBlocked:
            transaction.update(
                reference,
                {
                    'state': 'privacy_blocked',
                    'token': '',
                    'lease_until': 0.0,
                    'privacy_blocked_at': now,
                },
            )
            return True
        return False

    return revoke(client.transaction())
