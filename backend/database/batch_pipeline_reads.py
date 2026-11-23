"""Caller-budgeted, single-attempt read-only batch reference snapshots."""

import time

from google.api_core.exceptions import DeadlineExceeded, GoogleAPICallError
from google.cloud import firestore

from database.batch_pipeline_store import FirestoreTransaction
from utils.batch_pipeline.artifact_reads import ArtifactReadLimit


class BudgetedSnapshot(firestore.Transaction):
    """Public lifecycle access for the SDK's budgeted, manually begun transaction."""

    def bind_snapshot(self, transaction_id: bytes) -> None:
        self._id = transaction_id

    def clear_snapshot(self) -> None:
        self._clean_up()

    def commit_snapshot(self, client, timeout):
        client._firestore_api.commit(
            request={
                'database': client._database_string,
                'transaction': self.id,
                'writes': self._write_pbs,
            },
            metadata=client._rpc_metadata,
            timeout=timeout,
            retry=None,
        )
        self.clear_snapshot()


def read_snapshot(store, body, budget):
    return _snapshot(store, body, budget, write=False)


def write_snapshot(store, body, budget):
    """Single bounded CAS. An uncertain commit is resolved by the next caller."""
    return _snapshot(store, body, budget, write=True)


def _snapshot(store, body, budget, *, write):
    client = store.client
    transaction = BudgetedSnapshot(client, max_attempts=1, read_only=not write)
    try:
        # The SDK transactional decorator does not expose timeout/retry options
        # for begin/commit/rollback. Bound these RPCs explicitly; the SDK's read
        # helpers still use the resulting transaction ID and snapshot normally.
        response = client._firestore_api.begin_transaction(
            request={'database': client._database_string, 'options': {'read_write' if write else 'read_only': {}}},
            metadata=client._rpc_metadata,
            timeout=budget.timeout(10),
            retry=None,
        )
        transaction.bind_snapshot(response.transaction)
        view = FirestoreTransaction(client, store.namespace, transaction, read_budget=budget)
        result = body(view)
        if write and (view.writes or view.patches or view.external):
            view.flush()
            transaction.commit_snapshot(client, budget.timeout(10))
        budget.timeout(10)
        return result
    except DeadlineExceeded as error:
        raise ArtifactReadLimit('artifact read deadline') from error
    finally:
        try:
            # Release an uncommitted snapshot while time
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
