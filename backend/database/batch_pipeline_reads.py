"""Caller-budgeted, single-attempt read-only batch reference snapshots."""

from concurrent.futures import CancelledError
from contextlib import contextmanager
import time

from google.api_core.exceptions import Cancelled, DeadlineExceeded, GoogleAPICallError
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


def read_snapshot(store, body, budget, *, on_rpc=None):
    return _snapshot(store, body, budget, write=False, on_rpc=on_rpc)


def write_snapshot(store, body, budget, *, on_rpc=None, before_commit=None):
    """Single bounded CAS. An uncertain commit is resolved by the next caller."""
    return _snapshot(store, body, budget, write=True, on_rpc=on_rpc, before_commit=before_commit)


@contextmanager
def observe_rpc(on_rpc, stage):
    if on_rpc is None:
        yield
        return
    on_rpc(stage, 'attempt')
    try:
        yield
    except (Cancelled, CancelledError):
        on_rpc(stage, 'cancelled')
        raise
    except DeadlineExceeded:
        on_rpc(stage, 'deadline')
        raise
    except Exception:
        on_rpc(stage, 'error')
        raise
    else:
        on_rpc(stage, 'success')


def _snapshot(store, body, budget, *, write, on_rpc, before_commit=None):
    client = store.client
    transaction = BudgetedSnapshot(client, max_attempts=1, read_only=not write)
    try:
        # The SDK transactional decorator does not expose timeout/retry options
        # for begin/commit/rollback. Bound these RPCs explicitly; the SDK's read
        # helpers still use the resulting transaction ID and snapshot normally.
        timeout = budget.timeout(10)
        with observe_rpc(on_rpc, 'begin'):
            response = client._firestore_api.begin_transaction(
                request={'database': client._database_string, 'options': {'read_write' if write else 'read_only': {}}},
                metadata=client._rpc_metadata,
                timeout=timeout,
                retry=None,
            )
        transaction.bind_snapshot(response.transaction)
        view = FirestoreTransaction(client, store.namespace, transaction, read_budget=budget)
        result = body(view)
        if write and (view.writes or view.patches or view.external):
            view.flush()
            timeout = budget.timeout(10)
            if before_commit is not None:
                before_commit()
            with observe_rpc(on_rpc, 'commit'):
                transaction.commit_snapshot(client, timeout)
            return result
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
                    with observe_rpc(on_rpc, 'rollback'):
                        client._firestore_api.rollback(
                            request={'database': client._database_string, 'transaction': transaction.id},
                            metadata=client._rpc_metadata,
                            timeout=min(1, remaining),
                            retry=None,
                        )
                except GoogleAPICallError:
                    pass
            elif transaction.id and on_rpc is not None:
                on_rpc('rollback', 'expired_before_attempt')
        finally:
            transaction.clear_snapshot()
