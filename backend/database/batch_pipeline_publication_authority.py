"""Firestore authorities shared by the bounded oversized publication adapter.

The adapter's authority is owner-scoped so an absent pointer conflicts with
its creation, including when a writer would create an absent canonical ID.
"""

import os
from dataclasses import dataclass
from hashlib import sha256

from google.cloud import firestore
from google.cloud.firestore_v1.types import CommitRequest

from database.batch_pipeline_projection_protocol import ProjectionBlocked


MAX_ACTIVATION_READS = 276
MAX_ACTIVATION_WRITES = 12
MAX_ACTIVATION_BYTES = 8 * 1024 * 1024


def routing_ref(client, owner_id):
    return client.collection('batch_publication_routing').document(sha256(owner_id.encode()).hexdigest())


def publication_writer_fence_enabled(owner_id):
    # Deployment-scoped fencing only. This setting does not enable activation.
    return owner_id == os.getenv('BATCH_PUBLICATION_PILOT_OWNER') and bool(owner_id)


def assert_writer_unblocked(client, transaction, owner_id):
    """Conservatively fence the owner's whole write set in the write transaction."""
    if transaction is None or not transaction.in_progress:
        raise ValueError('publication writer fence requires a live transaction')
    route = routing_ref(client, owner_id).get(transaction=transaction).to_dict() or {}
    if route.get('active_publication') is not None:
        raise ProjectionBlocked('owner publication must drain before conflicting writes')


@dataclass
class ActivationOperations:
    reads: int = 0
    buffered_writes: int = 0
    committed: bool = False


class ActivationAttempt:
    """Point reads and hook-expanded writes of a single SDK transaction attempt."""

    def __init__(self, transaction):
        self.transaction = transaction
        self.operations = ActivationOperations()
        self._snapshots = {}

    def read(self, ref):
        if ref.path not in self._snapshots:
            if self.operations.reads >= MAX_ACTIVATION_READS:
                raise ProjectionBlocked('publication activation exceeds point-read budget')
            self.operations.reads += 1
            self._snapshots[ref.path] = ref.get(transaction=self.transaction, retry=None)
        return self._snapshots[ref.path]

    def validate_commit(self):
        from database.batch_privacy_write_fence import augment_commit as augment_privacy
        from database.memory_change_head import augment_commit as augment_memory

        request, _ = augment_privacy(
            CommitRequest(
                database=self.transaction._client._database_string,
                transaction=self.transaction.id,
                writes=self.transaction._write_pbs,
            )
        )
        request, _ = augment_memory(request)
        self.operations.buffered_writes = len(request.writes)
        if (
            self.operations.buffered_writes > MAX_ACTIVATION_WRITES
            or len(CommitRequest.serialize(request)) > MAX_ACTIVATION_BYTES
        ):
            raise ProjectionBlocked('publication activation exceeds native commit budget')


def run_activation_transaction(client, body, attempts):
    """Run bounded activation work and retain counts even on a refused commit."""
    @firestore.transactional
    def run(transaction):
        attempt = ActivationAttempt(transaction)
        attempts.append(attempt.operations)
        result = body(attempt)
        attempt.validate_commit()
        return result

    result = run(client.transaction(max_attempts=3))
    attempts[-1].committed = True
    return result


def record_oversized_row_custody(client, job_ref, *, owner_id, artifact):
    """Attach the refusal to the exact staged job while retaining its result.

    The caller passes the artifact reference from its authenticated staging
    plan after checking the size of the encoded canonical row.
    """
    @firestore.transactional
    def record(transaction):
        job = job_ref.get(transaction=transaction).to_dict() or {}
        if (
            not artifact
            or job.get('owner_id') != owner_id
            or job.get('state') != 'result_ready'
            or job.get('result') != artifact
        ):
            raise ProjectionBlocked('oversized publication custody lost its staged result binding')
        custody = job.get('publication_custody') or {}
        if custody.get('reason') == 'canonical_row_too_large' and custody.get('artifact') == artifact:
            return
        transaction.update(
            job_ref,
            {
                'publication_custody': {
                    'reason': 'canonical_row_too_large',
                    'artifact': artifact,
                    'recorded_at': firestore.SERVER_TIMESTAMP,
                }
            },
        )

    record(client.transaction(max_attempts=3))
