"""Field-masked adapter to the existing batch privacy authority for operator IO."""

from __future__ import annotations

from collections import Counter
from typing import Any

from google.cloud import firestore

from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from utils.conversations.empty_capture_recovery import AuthorityBlocked, Observed, ROW_FIELDS

MASKS = {
    'account_deletions': ('wipe_status',),
    'users': ('data_protection_level', 'migration_status', 'private_cloud_sync_enabled'),
    'batch_pipeline_privacy': ('generation', 'blocked', 'purging'),
    'deleted_conversations': (),
    'conversations': ROW_FIELDS,
    'conversation_finalization_jobs': ('uid', 'conversation_id', 'status', 'requires_byok'),
}


class MaskedReference:
    def __init__(self, reference: Any, owner: MaskedClient):
        self.reference, self.owner = reference, owner

    @property
    def path(self):
        return self.reference.path

    def collection(self, name):
        return MaskedCollection(self.reference.collection(name), self.owner)

    def get(self, *, transaction=None, field_paths=None, **kwargs):
        collection = self.path.split('/')[-2]
        if collection not in MASKS:
            raise AuthorityBlocked()
        mask = MASKS[collection] if field_paths is None else field_paths
        self.owner.reads[self.owner.category] += 1
        kwargs.setdefault('timeout', 30)
        kwargs.setdefault('retry', None)
        snapshot = self.reference.get(field_paths=mask, transaction=transaction, **kwargs)
        self.owner.snapshots[self.path] = snapshot
        return snapshot


class MaskedCollection:
    def __init__(self, collection, owner):
        self.collection, self.owner = collection, owner

    def document(self, key):
        return MaskedReference(self.collection.document(key), self.owner)


class MaskedClient:
    def __init__(self, client: Any, reads: Counter, category='privacy'):
        self.client, self.reads, self.category = client, reads, category
        self.snapshots = {}

    def collection(self, name):
        return MaskedCollection(self.client.collection(name), self)

    def document(self, path):
        return MaskedReference(self.client.document(path), self)


class Privacy:
    def __init__(self, client, reads):
        self.client, self.reads = client, reads

    def check(self, observed: Observed, transaction=None, *, match_revision=True):
        try:
            snapshots = {}
            client = MaskedClient(self.client, self.reads)
            generation = assert_batch_write_allowed(
                client,
                transaction,
                observed.uid,
                conversation_ids=(observed.conversation_id,),
                expected_generation=observed.privacy_generation,
                snapshots=snapshots,
            )
            row = snapshots.get('conversations', {}).get(observed.conversation_id) or {}
            source = client.snapshots.get(f'users/{observed.uid}/conversations/{observed.conversation_id}')
            if (
                source is None
                or not source.exists
                or (match_revision and source.update_time != observed.revision)
                or row.get('is_locked')
                or row.get('record_lane_owner')
                or row.get('uses_custom_stt')
                or row.get('listen_finalization_requires_byok')
                or row.get('deleted')
                or row.get('sync_merged_into')
                or row.get('data_protection_level') not in {'standard', 'enhanced'}
            ):
                raise AuthorityBlocked()
            # The job is the admission-time payer authority. Never promote an
            # unknown/abandoned BYOK obligation to an Omi-managed recognizer.
            if observed.requires_byok is not False:
                raise AuthorityBlocked()
            if len(observed.recovery_jobs) > 16:
                raise AuthorityBlocked()
            for job_id in observed.recovery_jobs:
                snapshot = (
                    MaskedClient(self.client, self.reads, 'authority')
                    .collection('conversation_finalization_jobs')
                    .document(job_id)
                    .get(transaction=transaction)
                )
                job = snapshot.to_dict() or {}
                if (
                    not snapshot.exists
                    or job.get('uid') != observed.uid
                    or job.get('conversation_id') != observed.conversation_id
                    or job.get('status') != 'dead_letter'
                    or job.get('requires_byok') is not False
                ):
                    raise AuthorityBlocked()
            observed.privacy_generation = generation
        except BatchPrivacyBlocked:
            raise AuthorityBlocked() from None


def marker_blocks(snapshot):
    return account_deletion_marker_blocks_access(
        marker_exists=snapshot.exists, raw_status=(snapshot.to_dict() or {}).get('wipe_status')
    )


def atomic_write(client, operation):
    """Use the commit receipt, never a later row read, as the new CAS revision."""
    transaction = client.transaction(max_attempts=1)
    firestore.transactional(operation)(transaction)
    results = transaction.write_results
    if not results or len(results) != 1:
        raise RuntimeError('write_receipt_unproven')
    return results[0].update_time
