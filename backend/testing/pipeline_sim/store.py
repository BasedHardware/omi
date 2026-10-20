"""Indexed in-memory implementation of the batch ``Store`` protocol.

Mirrors ``database.batch_pipeline_store.FirestoreTransaction`` /``FirestoreStore``
semantics that the real scheduler, merge, admission and recovery code relies on:

- reads see the transaction's own buffered writes; queries (``first_pending``,
  ``service_frontier``, ``due``, ``control_candidate``) see committed state only,
  exactly like a Firestore query issued inside a transaction;
- writes are buffered and applied atomically when the body returns; an exception
  discards them;
- ``flush`` repeats the production privacy guard: every written ``jobs`` /
  ``results`` row re-runs ``assert_batch_write_allowed`` for its owner,
  conversation and privacy generation before anything is applied.

The privacy authority is the REAL ``database.batch_pipeline_privacy.assert_batch_write_allowed``
running against ``tests.unit.fixtures.strict_firestore_transaction.StrictFirestore``
(customer documents: users, conversations, deleted_conversations, account
deletion markers and the privacy generation). Only the batch namespace
collections live in this indexed store; that split exists because
``StrictFirestore`` deliberately does not model ordered queries.

There is no contention, retry or partial-commit model: transactions are atomic
and serial (the simulation is single-threaded).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, TypeVar

from database.batch_pipeline_privacy import (
    PRIVACY_COLLECTION,
    BatchPrivacyBlocked,
    assert_batch_write_allowed,
    privacy_owner_key,
)

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

# Same set as database.batch_pipeline_recovery.PROVIDER_STATES (not imported: keep the model import-light).
PROVIDER_STATES = frozenset({'provider_pending', 'provider_running'})

T = TypeVar('T')

_DUE_FIELDS = {
    'leased': 'lease_until',
    'retry': 'available_at',
    'result_ready': 'enqueued_at',
    'record_pending': 'available_at',
}


class CustomerData:
    """Synthetic customer documents read by the real privacy fence."""

    def __init__(self):
        self.client = StrictFirestore()
        self.checks = 0

    def add_user(self, uid: str, *, protection: str = 'standard') -> None:
        self.client.rows[('users', uid)] = {'data_protection_level': protection, 'private_cloud_sync_enabled': True}

    def add_conversation(self, uid: str, conversation_id: str) -> None:
        self.client.rows[('users', uid, 'conversations', conversation_id)] = {'status': 'completed'}

    def merge_conversation(self, uid: str, source_id: str, target_id: str) -> None:
        """Server-owned redirect: the fence follows ``sync_merged_into`` to a live target."""
        self.add_conversation(uid, target_id)
        self.client.rows[('users', uid, 'conversations', source_id)] = {'deleted': True, 'sync_merged_into': target_id}

    def delete_conversation(self, uid: str, conversation_id: str) -> None:
        self.client.rows[('users', uid, 'deleted_conversations', conversation_id)] = {'deleted': True}

    def block_privacy(self, uid: str) -> None:
        """Advance the privacy generation and block, as ``advance_privacy_generation(blocked=True)`` does."""
        key = (PRIVACY_COLLECTION, privacy_owner_key(uid))
        previous = self.client.rows.get(key, {})
        self.client.rows[key] = {'generation': int(previous.get('generation', 0)) + 1, 'blocked': True, 'purging': True}

    def delete_account(self, uid: str) -> None:
        self.client.rows[('account_deletions', uid)] = {'wipe_status': 'pending'}

    def check(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        self.checks += 1
        transaction = self.client.transaction()
        try:
            return assert_batch_write_allowed(
                self.client,
                transaction,
                uid,
                conversation_ids=tuple(conversation_ids),
                expected_generation=expected_generation,
            )
        finally:
            # Each check is its own read-only transaction; do not retain them all.
            self.client.transactions.clear()

    def blocked(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> bool:
        try:
            self.check(uid, conversation_ids, expected_generation)
        except BatchPrivacyBlocked:
            return True
        return False


class SimTransaction:
    def __init__(self, store: 'SimStore'):
        self.store = store
        self.writes: dict[tuple[str, str], dict] = {}
        self.patches: dict[tuple[str, str], dict] = {}

    def get(self, table: str, key: str) -> dict:
        address = (table, key)
        base = self.writes.get(address)
        if base is None:
            base = self.store.rows.get(address, {})
        return deepcopy({**base, **self.patches.get(address, {})})

    def put(self, table: str, key: str, value: dict) -> None:
        # Same refusals as FirestoreTransaction.put/patch (conformance: tests/integration/test_store_conformance.py).
        if table == 'conversations':
            raise ValueError('conversation admission requires a field patch, never a document set')
        self.writes[(table, key)] = deepcopy(value)

    def patch(self, table: str, key: str, fields: dict) -> None:
        if table != 'conversations' or set(fields) != {'record_lane_owner'}:
            raise ValueError('only the conversation route owner may be patched by admission')
        self.patches.setdefault((table, key), {}).update(deepcopy(fields))

    def first_pending(self, owner_key: str) -> dict | None:
        return self.store.first_pending(owner_key)

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        return self.store.ready_predecessor(owner_key, priority, segment_id)

    def first_ready_pending(self, owner_key: str) -> dict | None:
        return self.store.first_pending(owner_key, ready_only=True)

    def service_frontier(self, priority: int) -> float:
        return self.store.service_frontier(priority)

    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        return self.store.customer.check(uid, conversation_ids, expected_generation)

    def flush(self) -> None:
        # Mirrors FirestoreTransaction.flush (database/batch_pipeline_store.py).
        if len(self.writes) + len(self.patches) > 450:
            raise RuntimeError('batch transaction write budget exceeded')
        guarded = set()
        for (table, key), value in self.writes.items():
            if table not in {'jobs', 'results'}:
                continue
            job = value if table == 'jobs' else self.get('jobs', key)
            identity = (job['owner_id'], job.get('conversation_id'), job.get('privacy_generation'))
            if identity in guarded:
                continue
            guarded.add(identity)
            generation = self.check_privacy(
                job['owner_id'],
                (job['conversation_id'],) if job.get('conversation_id') else (),
                job.get('privacy_generation'),
            )
            if table == 'jobs' and value.get('privacy_generation') is None:
                value['privacy_generation'] = generation
        for address, value in self.writes.items():
            self.store.apply(address, value)
        for address, fields in self.patches.items():
            row = deepcopy(self.store.rows.get(address, {}))
            row.update(fields)
            self.store.apply(address, row)


class SimStore:
    """Batch-namespace documents with the secondary indexes the real queries need."""

    def __init__(self, customer: CustomerData, *, namespace: str = 'batch_pipeline_dev'):
        self.customer = customer
        self.namespace = namespace
        self.client = None  # QuarantineRecovery.sweep passes this to the patched recovery_candidates model.
        self.rows: dict[tuple[str, str], dict] = {}
        self._by_state: dict[str, set[str]] = {}
        self._pending_by_owner: dict[str, set[str]] = {}
        self._controls: set[str] = set()
        self.transactions = 0
        self.observers: list[Callable[[tuple[str, str], dict, dict], None]] = []

    # -- Store protocol -------------------------------------------------
    def run(self, body: Callable[[SimTransaction], T]) -> T:
        self.transactions += 1
        tx = SimTransaction(self)
        result = body(tx)
        tx.flush()
        return result

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        if state not in _DUE_FIELDS:
            raise ValueError('only recoverable states may be scanned')
        field = _DUE_FIELDS[state]
        candidates = []
        for segment_id in self._by_state.get(state, ()):
            value = self.rows[('jobs', segment_id)].get(field)
            if value is not None and value <= now:
                candidates.append((value, segment_id))
        candidates.sort()
        return [segment_id for _, segment_id in candidates[: max(1, min(limit, 100))]]

    def oldest(self, priority: int, *, ready_only: bool = False) -> float | None:
        values = [
            row['enqueued_at']
            for (table, _), row in self.rows.items()
            if table == 'jobs'
            and row.get('priority') == priority
            and (row.get('state') == 'ready' if ready_only else row.get('merge_pending'))
        ]
        return min(values) if values else None

    def oldest_retry(self, priority: int) -> float | None:
        values = [
            row['retry_started_at']
            for (table, _), row in self.rows.items()
            if table == 'jobs' and row.get('priority') == priority and 'retry_started_at' in row
        ]
        return min(values) if values else None

    def control_candidate(self, priority: int, pool: str, now: float) -> str | None:
        if priority not in (0, 1, 2) or pool not in {'batch', 'live'}:
            raise ValueError('bounded priority and pool required')
        prefix = f'p{priority}_'
        best = None
        for key in self._controls:
            row = self.rows[('control', key)]
            if not row.get(prefix + 'active'):
                continue
            service = row.get(prefix + 'service')
            available = row.get(prefix + pool + '_available_at')
            if service is None or available is None or service < 0 or available > now:
                continue
            candidate = (service, available, key)
            if best is None or candidate < best:
                best = candidate
        return best[2] if best else None

    def quarantine_fenced(self, segment_id: str, now: float) -> bool:
        """Model of database/batch_pipeline_recovery.quarantine_fenced (fence recheck, revoke only)."""
        job = self.rows.get(('jobs', segment_id), {})
        if job.get('state') not in {'leased', 'retry'} | PROVIDER_STATES:
            return False
        if not self.customer.blocked(
            job['owner_id'],
            (job['conversation_id'],) if job.get('conversation_id') else (),
            job.get('privacy_generation'),
        ):
            return False
        revoked = {**job, 'state': 'privacy_blocked', 'token': '', 'lease_until': 0.0, 'privacy_blocked_at': now}
        if job['state'] in PROVIDER_STATES:
            revoked['merge_pending'] = False
        self.apply(('jobs', segment_id), revoked)
        return True

    # -- Query helpers --------------------------------------------------
    def first_pending(self, owner_key: str, *, ready_only: bool = False) -> dict | None:
        best = None
        for segment_id in self._pending_by_owner.get(owner_key, ()):
            row = self.rows[('jobs', segment_id)]
            if ready_only and row.get('state') != 'result_ready':
                continue
            candidate = (row['capture_at'], segment_id)
            if best is None or candidate < best:
                best = candidate
        return deepcopy(self.rows[('jobs', best[1])]) if best else None

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        """Only a ready row in this owner's priority FIFO can be the live predecessor; two matches fail closed."""
        matches = sorted(
            key
            for (table, key), row in self.rows.items()
            if table == 'jobs'
            and row.get('owner_key') == owner_key
            and row.get('priority') == priority
            and row.get('state') == 'ready'
            and row.get('next') == segment_id
        )
        return deepcopy(self.rows[('jobs', matches[0])]) if len(matches) == 1 else None

    def projection_pending(self, limit: int = 100) -> list[str]:
        return self.projection_page(limit)[0]

    def projection_page(self, limit: int = 100, *, after=None) -> tuple[list[str], Any]:
        """Keyset page over results awaiting projection, ordered (committed_at, key); mirrors the Firestore scan."""
        wanted = {'pending', 'persisted', 'ready'}
        ordered = sorted(
            (row['committed_at'], key)
            for (table, key), row in self.rows.items()
            if table == 'results' and row.get('projection_state') in wanted and 'committed_at' in row
        )
        if after is not None:
            ordered = [entry for entry in ordered if entry > (after[0], after[1])]
        size = max(1, min(limit, 100))
        page = ordered[:size]
        cursor = (page[-1][0], page[-1][1]) if len(page) == size else None
        return [key for _, key in page], cursor

    def longest_ready_pending(self, owner_key: str) -> dict | None:
        # Firestore excludes rows without the ordered field, and orders ties by document name.
        rows = [
            (row['ready_at'], segment_id)
            for segment_id in self._pending_by_owner.get(owner_key, ())
            if (row := self.rows[('jobs', segment_id)]).get('state') == 'result_ready' and 'ready_at' in row
        ]
        return deepcopy(self.rows[('jobs', min(rows)[1])]) if rows else None

    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]:
        rows = sorted(
            (row['capture_at'], segment_id)
            for segment_id in self._pending_by_owner.get(owner_key, ())
            if (row := self.rows[('jobs', segment_id)]).get('fresh_capture') is True
        )
        return [deepcopy(self.rows[('jobs', segment_id)]) for _, segment_id in rows[:limit]]

    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]:
        keys = sorted(
            key
            for (table, key), row in self.rows.items()
            if table == 'merge_holds' and row.get('held') and (after is None or key > after)
        )
        owners = []
        for key in keys[:limit]:
            job = self.first_pending(key)
            owners.append((key, job['owner_id'] if job else None))
        return owners

    def service_frontier(self, priority: int) -> float:
        if priority not in (0, 1, 2):
            raise ValueError('bounded priority required')
        name = f'p{priority}_service'
        values = [self.rows[('control', key)][name] for key in self._controls if name in self.rows[('control', key)]]
        return max(values) if values else 0.0

    def jobs(self) -> list[dict]:
        return [row for (table, _), row in self.rows.items() if table == 'jobs']

    def get(self, table: str, key: str) -> dict:
        return deepcopy(self.rows.get((table, key), {}))

    def jobs_in_state(self, state: str) -> list[str]:
        return sorted(self._by_state.get(state, ()))

    # -- Mutation + index maintenance -----------------------------------
    def apply(self, address: tuple[str, str], value: dict) -> None:
        table, key = address
        previous = self.rows.get(address)
        if table == 'jobs':
            if previous is not None:
                self._by_state.get(previous.get('state'), set()).discard(key)
                if previous.get('merge_pending'):
                    self._pending_by_owner.get(previous.get('owner_key'), set()).discard(key)
            self._by_state.setdefault(value.get('state'), set()).add(key)
            if value.get('merge_pending'):
                self._pending_by_owner.setdefault(value.get('owner_key'), set()).add(key)
        elif table == 'control':
            self._controls.add(key)
        self.rows[address] = value
        for observer in self.observers:
            observer(address, previous or {}, value)

    def delete(self, table: str, key: str) -> None:
        previous = self.rows.pop((table, key), None)
        if previous is None:
            return
        if table == 'jobs':
            self._by_state.get(previous.get('state'), set()).discard(key)
            self._pending_by_owner.get(previous.get('owner_key'), set()).discard(key)
        elif table == 'control':
            self._controls.discard(key)

    def purge(self, owner_id: str, conversation_id: str | None = None) -> int:
        """MODEL of database/batch_pipeline_purge.purge_batch_owner (+ _delete_job unlinking).

        Production calls it synchronously after writing the conversation
        tombstone (database/conversation_tombstones.py) or after advancing the
        privacy generation for an account. Matching jobs are unlinked from their
        owner queue and deleted; a conversation purge keeps an erased result
        placeholder (retain_ordering), an account purge deletes results.
        """
        from config.batch_pipeline import scheduler_control_key
        from utils.batch_pipeline.scheduler import owner_key as hash_owner
        from utils.sync.capture import chunk_identity

        key = hash_owner(owner_id)
        removed = 0
        touched: list[tuple[str, str]] = []  # production purge re-copies these to the A2 shadow after commit
        for (table, segment_id), job in sorted(self.rows.items()):
            if table != 'jobs' or job.get('owner_key') != key:
                continue
            binding = job.get('projection_binding') or {}
            identities = {job.get('conversation_id'), binding.get('target_conversation_id')}
            identities.update(job.get('conversation_ids') or [])
            if binding and 'capture_at' in job:
                identities.add(
                    chunk_identity(
                        owner_id,
                        binding.get('source', 'omi'),
                        binding.get('client_device_id'),
                        binding.get('is_locked', False),
                        job['capture_at'],
                    )
                )
            if conversation_id is not None and conversation_id not in identities:
                continue
            queue_key = f"{job['priority']}_{key}"
            queue = self.rows.get(('queues', queue_key))
            touched += [('jobs', segment_id), ('results', segment_id), ('queues', queue_key)]
            touched.append(('control', scheduler_control_key(key)))
            predecessors = [
                other_id
                for (other_table, other_id), other in sorted(self.rows.items())
                if other_table == 'jobs' and other.get('next') == segment_id and other.get('owner_key') == key
            ]
            if queue is not None:
                queue = dict(queue)
                if queue.get('head') == segment_id:
                    queue['head'] = job.get('next', '')
                if queue.get('tail') == segment_id:
                    queue['tail'] = predecessors[0] if predecessors else ''
                if not queue.get('head'):
                    control_key = scheduler_control_key(key)
                    control = deepcopy(self.rows.get(('control', control_key), {'rings': {}}))
                    for ring in control.get('rings', {}).values():
                        while queue_key in ring:
                            ring.remove(queue_key)
                    self.apply(('control', control_key), control)
                    self.delete('queues', queue_key)
                else:
                    self.apply(('queues', queue_key), queue)
            for predecessor in predecessors:
                self.mutate('jobs', predecessor, lambda row, nxt=job.get('next', ''): row.update(next=nxt))
                touched.append(('jobs', predecessor))
            self.delete('jobs', segment_id)
            if ('results', segment_id) in self.rows:
                if conversation_id is not None:
                    self.mutate('results', segment_id, lambda row: row.update(erased=True, projection_state='erased'))
                else:
                    self.delete('results', segment_id)
            removed += 1
        from database.batch_pipeline_shadow_hook import mirror_refresh

        mirror_refresh(self.namespace, touched)
        return removed

    def mutate(self, table: str, key: str, update: Callable[[dict[str, Any]], None]) -> None:
        """Harness-only direct edit (used by models of non-simulated writers)."""
        row = deepcopy(self.rows.get((table, key), {}))
        update(row)
        self.apply((table, key), row)
