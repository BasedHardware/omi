"""Restrictive lease revocation for privacy-fenced work, without resurrection."""

from typing import Any
from google.cloud import firestore
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from database.batch_pipeline_shadow_hook import mirror_refresh

# A provider-STT unit (C8) has no lease to revoke; its fenced release also clears merge_pending so
# OrderedMerge stops holding the owner's later captures behind it (no purge follows every fence).
PROVIDER_STATES = frozenset({'provider_pending', 'provider_running', 'vendor_held'})


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
        if job.get('state') not in {'leased', 'retry', 'allowance_held'} | PROVIDER_STATES:
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
            update = {'state': 'privacy_blocked', 'token': '', 'lease_until': 0.0, 'privacy_blocked_at': now}
            if job['state'] in PROVIDER_STATES:
                update['merge_pending'] = False
            transaction.update(reference, update)
            return True
        return False

    revoked = revoke(client.transaction())
    if revoked:
        mirror_refresh(namespace, [('jobs', segment_id)])  # A2 shadow: no-op unless shadow mode
    return revoked


# Drainer cause 2 (privacy-lane ruling faf00e, 2026-11-07): the ONLY fields a
# privacy-blocked record_pending defer may write. It touches no user data.
PRIVACY_DEFER_FIELDS = frozenset({'available_at'})


def _check_privacy_defer_fields(update: dict) -> dict:
    if not update or set(update) - PRIVACY_DEFER_FIELDS:
        raise ValueError('privacy defer may change available_at only')
    return update


def privacy_defer_update(until: float) -> dict:
    return _check_privacy_defer_fields({'available_at': float(until)})


def defer_privacy_blocked_record(client: Any, namespace: str, segment_id: str, until: float, now: float) -> bool:
    """Move a due, privacy-blocked record_pending row off the drain page until `until`.

    The record drainer's claim is a full job write, so the store flush privacy
    fence refuses it and the row stayed due forever, starving every row behind
    the oldest page. This write is exempt from that fence because it is an
    UPDATE of the existing job document (Firestore refuses an update of a
    missing document, so a purged job is never recreated) that changes
    available_at only. The fence is rechecked here: an allowed row is left to
    the normal claim, and erasure keeps ownership of a blocked one.
    """
    reference = client.collection(f'{namespace}_jobs').document(segment_id)

    @firestore.transactional
    def defer(transaction):
        snapshot = reference.get(transaction=transaction)
        if not snapshot.exists:
            return False
        job = snapshot.to_dict() or {}
        if job.get('state') != 'record_pending' or job.get('available_at', 0) > now:
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
            transaction.update(reference, _check_privacy_defer_fields(privacy_defer_update(until)))
            return True
        return False

    deferred = defer(client.transaction())
    if deferred:
        mirror_refresh(namespace, [('jobs', segment_id)])  # A2 shadow: no-op unless shadow mode
    return deferred
