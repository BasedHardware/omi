"""Transactional WAL storage reservations, shared by both stage namespaces.

Reservations precede object writes and never expire: a crashed request may own
an original even without a receipt. Only completed privacy erasure releases it.
"""

from google.cloud import firestore

from config.batch_pipeline_record_wal_handoff import pending_limits
from database._client import run_transactional
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_store import FirestoreTransaction
from database.firestore_read_origin import read_origin

NAMESPACE = 'batch_pipeline_prod'
SCHEMA = 'record_wal_capacity_v1'
RESERVATION_KIND = 'record_wal_reservation'
ENCRYPTION_OVERHEAD = 32  # length prefix + nonce + AES-GCM authentication tag


class CapacityExceeded(RuntimeError):
    def __init__(self, scope):
        super().__init__('WAL pending capacity exhausted')
        self.scope = scope  # Closed vocabulary: owner or global.


def _refs(client, uid):
    return (
        FirestoreTransaction.intake_reference(client, NAMESPACE, 'wal_capacity_global_v1'),
        FirestoreTransaction.intake_reference(client, NAMESPACE, 'wal_capacity_owner_' + privacy_owner_key(uid)),
    )


def _counts(data):
    if not data:
        return {'bytes': 0, 'files': 0}
    if data.get('schema') != SCHEMA or any(type(data.get(k)) is not int or data[k] < 0 for k in ('bytes', 'files')):
        raise ValueError('invalid WAL capacity ledger')
    return {k: data[k] for k in ('bytes', 'files')}


def reserve(client, tx, uid, entries):
    """Called after all file reads, before any writes in the admitting transaction."""
    if not entries:
        return  # Existing reservations/rebundles spend no additional capacity.
    limits = pending_limits()
    refs = _refs(client, uid)
    counts = [_counts(ref.get(transaction=tx).to_dict()) for ref in refs]
    added = {'bytes': sum(entry['size'] + ENCRYPTION_OVERHEAD for entry in entries), 'files': len(entries)}
    for scope, count in zip(('global', 'owner'), counts):
        if any(count[k] + added[k] > limits[scope + '_' + k] for k in added):
            raise CapacityExceeded(scope)
    for ref, count in zip(refs, counts):
        tx.set(ref, {'schema': SCHEMA, **{k: count[k] + added[k] for k in added}})


@read_origin('job:record_wal_handoff:capacity_sample')
def sample(client):
    """Exact reserved volume, including object-only crashes; no owner labels."""
    ref, _ = _refs(client, '_global_sample')
    return _counts(ref.get().to_dict())


def erase_file(client, reference, uid, *, fence=None):
    """Release once, atomically with metadata deletion, after media erasure.

    The caller owns the deletion tombstone/account gate and has swept originals
    (including crash orphans). Quota rows have no owner_key and generic purge
    discovery cannot erase their accounting before this transaction.
    """

    @firestore.transactional
    def erase(tx):
        if fence is not None:
            fence(tx)
        row = reference.get(transaction=tx).to_dict() or {}
        if not row:
            return
        if row.get('owner_id') != uid:
            raise ValueError('WAL reservation erase owner mismatch')
        charge = row.get('quota_bytes')
        if charge is None:  # Reader compatibility with pre-budget receipts.
            tx.delete(reference)
            return
        if type(charge) is not int or charge <= 0:
            raise ValueError('invalid WAL reservation charge')
        refs = _refs(client, uid)
        counts = [_counts(ref.get(transaction=tx).to_dict()) for ref in refs]
        if any(count['bytes'] < charge or count['files'] < 1 for count in counts):
            raise ValueError('WAL capacity ledger underflow')
        for ref, count in zip(refs, counts):
            remaining = {'bytes': count['bytes'] - charge, 'files': count['files'] - 1}
            if remaining['files']:
                tx.set(ref, {'schema': SCHEMA, **remaining})
            elif remaining['bytes']:
                raise ValueError('WAL capacity ledger imbalance')
            else:
                tx.delete(ref)
        tx.delete(reference)

    return run_transactional(client, erase, transient=True)
