"""Caller-budgeted, single-attempt read-only batch reference snapshots."""

import time

from google.api_core.exceptions import DeadlineExceeded, GoogleAPICallError
from google.cloud import firestore

from database.batch_pipeline_store import FirestoreTransaction
from utils.batch_pipeline.artifact_reads import ArtifactReadLimit


class ReadOnlySnapshot(firestore.Transaction):
    """Public lifecycle access for the SDK's budgeted, manually begun snapshot."""

    def bind_snapshot(self, transaction_id: bytes) -> None:
        self._id = transaction_id

    def clear_snapshot(self) -> None:
        self._clean_up()


def read_snapshot(store, body, budget):
    client = store.client
    transaction = ReadOnlySnapshot(client, max_attempts=1, read_only=True)
    try:
        # The SDK transactional decorator does not expose timeout/retry options
        # for begin/commit/rollback. Bound these RPCs explicitly; the SDK's read
        # helpers still use the resulting transaction ID and snapshot normally.
        response = client._firestore_api.begin_transaction(
            request={'database': client._database_string, 'options': {'read_only': {}}},
            metadata=client._rpc_metadata,
            timeout=budget.timeout(10),
            retry=None,
        )
        transaction.bind_snapshot(response.transaction)
        result = body(FirestoreTransaction(client, store.namespace, transaction, read_budget=budget))
        budget.timeout(10)
        return result
    except DeadlineExceeded as error:
        raise ArtifactReadLimit('artifact read deadline') from error
    finally:
        try:
            # There are no writes to commit. Release the snapshot while time
            # remains; otherwise its server lease expires without retaining a
            # worker for cleanup. Cleanup cannot replace a reference refusal.
            remaining = budget.deadline - time.monotonic()
            if transaction.id and remaining > 0:
                try:
                    client._firestore_api.rollback(
                        request={'database': client._database_string, 'transaction': transaction.id},
                        metadata=client._rpc_metadata,
                        timeout=min(1, remaining),
                        retry=None,
                    )
                except GoogleAPICallError:
                    pass
        finally:
            transaction.clear_snapshot()
