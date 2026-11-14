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
import hashlib
from typing import Any, Callable, TypeVar

from config.batch_pipeline import held_poll_skip_enabled, MERGE_POLL_TERMINAL_STATES
from database.batch_pipeline_projection_finish_backfill import BACKFILL_KEY, backfill_marker_complete

from database.batch_pipeline_privacy import (
    PRIVACY_COLLECTION,
    BatchPrivacyBlocked,
    assert_batch_write_allowed,
    privacy_owner_key,
)

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from database.batch_pipeline_store import (
    ADMISSIBLE_READY_SCAN_LIMIT,
    OLDEST_POLICY_HOLD_SCAN_LIMIT,
    PROJECTION_DISCOVERY_STATES,
    PROJECTION_OBLIGATION_STATES,
    is_admissible_ready,
    is_policy_hold,
    is_queue_dispositioned,
)

# Mirrors the recovery protocol's state names without binding to its enum.
# The shared queue predicate import creates no Firestore client.
PROVIDER_STATES = frozenset({'provider_pending', 'provider_running', 'vendor_held'})

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

    def defer_set(self, ref: Any, value: dict) -> None:
        # Same surface as FirestoreTransaction.defer_set; the sim has no Firestore document to join.
        raise NotImplementedError('joining Firestore documents need the Firestore transaction')

    def first_pending(self, owner_key: str) -> dict | None:
        return self.store.first_pending(owner_key)

    def fresh_first_pending(self, owner_key: str) -> dict | None:
        return self._fresh_first(owner_key, ready=False)

    def fresh_first_ready_pending(self, owner_key: str) -> dict | None:
        return self._fresh_first(owner_key, ready=True)

    def _fresh_first(self, owner_key: str, *, ready: bool) -> dict | None:
        # Filter borrowed rows before copying: a held owner can retain hundreds of
        # backlog jobs, and neither fresh query needs to materialize their payloads.
        rows = (
            self.writes.get(('jobs', segment), self.store.rows.get(('jobs', segment), {}))
            for segment in self.store._pending_by_owner.get(owner_key, ())
        )
        rows = [
            row
            for row in rows
            if row.get('merge_pending')
            and row.get('fresh_capture') is True
            and (not ready or row.get('state') == 'result_ready')
        ]
        return deepcopy(min(rows, key=lambda row: (row['capture_at'], row['segment_id']))) if rows else None

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
    def allowance_owners(self, now: float, limit: int) -> list[str]:
        rows = sorted(
            (row['check_at'], key)
            for (table, key), row in self.rows.items()
            if table == 'allowance_holds' and row.get('active') and row['check_at'] <= now
        )
        return [key for _, key in rows[: max(1, min(limit, 100))]]

    def allowance_page(self, owner_key: str | None, after, limit: int) -> list[str]:
        rows = sorted(
            (row['capture_at'], key)
            for (table, key), row in self.rows.items()
            if table == 'jobs'
            and row.get('state') == 'allowance_held'
            and (owner_key is None or row['owner_key'] == owner_key)
            and (after is None or (row['capture_at'], key) > tuple(after))
        )
        return [key for _, key in rows[: max(1, min(limit, 100))]]

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
        if ready_only:
            values = [
                row['enqueued_at']
                for (table, _), row in self.rows.items()
                if table == 'jobs' and row.get('priority') == priority and row.get('state') == 'ready'
            ]
            return min(values) if values else None
        # Mirrors database.batch_pipeline_store.oldest: a bounded FIFO prefix walked past policy holds.
        rows = sorted(
            (row['enqueued_at'], key, row)
            for (table, key), row in self.rows.items()
            if table == 'jobs' and row.get('priority') == priority and row.get('merge_pending')
        )
        for enqueued_at, _, row in rows[:OLDEST_POLICY_HOLD_SCAN_LIMIT]:
            if not is_queue_dispositioned(row) and not is_policy_hold(row):
                return enqueued_at
        return float('nan') if len(rows) > OLDEST_POLICY_HOLD_SCAN_LIMIT else None

    def ready_for_capacity(self, priority: int, now: float) -> int:
        """Mirrors database.batch_pipeline_store.ready_for_capacity."""
        return sum(
            1
            for segment_id in self._by_state.get('ready', ())
            if (row := self.rows[('jobs', segment_id)]).get('priority') == priority
            and row.get('merge_pending') is True
            and (row.get('compute_decision') or {}).get('outcome') in {'unattempted', 'allowed'}
            and row.get('available_at', float('inf')) <= now
        )

    def oldest_admissible_ready(self, priority: int, now: float) -> float | None:
        """Mirrors database.batch_pipeline_store.oldest_admissible_ready."""
        rows = sorted(
            (row['enqueued_at'], segment_id, row)
            for segment_id in self._by_state.get('ready', ())
            if (row := self.rows[('jobs', segment_id)]).get('priority') == priority
        )
        for enqueued_at, _, row in rows[:ADMISSIBLE_READY_SCAN_LIMIT]:
            if is_admissible_ready(row, now):
                return enqueued_at
        return None

    def oldest_retry(self, priority: int) -> float | None:
        rows = sorted(
            (row['retry_started_at'], key, row)
            for (table, key), row in self.rows.items()
            if table == 'jobs' and row.get('priority') == priority and 'retry_started_at' in row
        )
        for started, _, row in rows[:OLDEST_POLICY_HOLD_SCAN_LIMIT]:
            if not is_queue_dispositioned(row) and not is_policy_hold(row):
                return started
        return float('nan') if len(rows) > OLDEST_POLICY_HOLD_SCAN_LIMIT else None

    def acquire_pull_claim(self, shard: str, token: str, now: float, ttl: float) -> bool:
        if self.rows.get(('pull_claims', shard), {}).get('expires_at', 0) > now:
            return False
        self.rows['pull_claims', shard] = {'token': token, 'expires_at': now + ttl}
        return True

    def control_candidate(self, priority: int, pool: str, now: float, *, worker_id: str = '', exclude=()) -> str | None:
        return next(
            (key for key in self.control_candidates(priority, pool, now, worker_id=worker_id) if key not in exclude),
            None,
        )

    def control_candidates(
        self, priority: int, pool: str, now: float, *, worker_id: str = '', fanout: int | None = None
    ) -> list[str]:
        from config.batch_pipeline import control_candidate_fanout

        if priority not in (0, 1, 2) or pool not in {'batch', 'live'}:
            raise ValueError('bounded priority and pool required')
        prefix = f'p{priority}_'
        rows = [(self.rows['control', key], key) for key in self._controls]
        rows = [
            (row, key)
            for row, key in rows
            if row.get(prefix + 'active')
            and row.get(prefix + 'service', -1) >= 0
            and row.get(prefix + pool + '_available_at', float('inf')) <= now
        ]
        rows.sort(key=lambda v: (v[0][prefix + 'service'], v[0][prefix + pool + '_available_at'], v[1]))
        rows = rows[: control_candidate_fanout(fanout) if worker_id else 1]
        if worker_id:
            rows.sort(key=lambda v: (v[0][prefix + 'service'], hashlib.sha256(f'{worker_id}:{v[1]}'.encode()).digest()))
        return [key for _, key in rows]

    def quarantine_fenced(self, segment_id: str, now: float) -> bool:
        """Model of database/batch_pipeline_recovery.quarantine_fenced (fence recheck, revoke only)."""
        job = self.rows.get(('jobs', segment_id), {})
        if job.get('state') not in {'leased', 'retry', 'allowance_held'} | PROVIDER_STATES:
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

    def cancel_fenced_recovery(self, segment_id: str) -> bool:
        """Model of cancel_fenced_recovery: revocation-only write allowed after privacy rejects ordinary writes."""
        from database.batch_pipeline_projection_protocol import normalized_binding

        job = self.rows.get(('jobs', segment_id), {})
        if not job or not job.get('recovery'):
            return False
        binding = normalized_binding(job['projection_binding'])
        ids = [value for value in (job.get('conversation_id'), binding.target_conversation_id) if value]
        ids.extend(job.get('conversation_ids') or [])
        if self.customer.blocked(binding.owner_id, ids, binding.privacy_generation):
            self.apply(
                ('jobs', segment_id),
                {**job, 'recovery_state': 'cancelled'},
            )
            return True
        return False

    def defer_privacy_blocked_record(self, segment_id: str, until: float, now: float) -> bool:
        """Model of database/batch_pipeline_recovery.defer_privacy_blocked_record (available_at only)."""
        job = self.rows.get(('jobs', segment_id))
        if not job or job.get('state') != 'record_pending' or job.get('available_at', 0) > now:
            return False
        if not self.customer.blocked(
            job['owner_id'],
            (job['conversation_id'],) if job.get('conversation_id') else (),
            job.get('privacy_generation'),
        ):
            return False
        self.apply(('jobs', segment_id), {**job, 'available_at': float(until)})
        return True

    # -- Query helpers --------------------------------------------------
    def first_pending(self, owner_key: str, *, ready_only: bool = False, skip_terminal: bool = True) -> dict | None:
        skip = not ready_only and skip_terminal and held_poll_skip_enabled()
        best = None
        for segment_id in self._pending_by_owner.get(owner_key, ()):
            row = self.rows[('jobs', segment_id)]
            if skip and row.get('state') in (None, *MERGE_POLL_TERMINAL_STATES):
                continue
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

    def projection_finish_backfill_complete(self) -> bool:
        return backfill_marker_complete(self.run(lambda tx: tx.get('control', BACKFILL_KEY)))

    def projection_successor(self, owner_key: str, previous: str | None) -> str | None:
        """The owner's result committed directly after ``previous``; two matches fail closed (Firestore hint)."""
        matches = sorted(
            key
            for (table, key), row in self.rows.items()
            if table == 'results'
            and row.get('owner_key') == owner_key
            and 'previous_segment_id' in row  # Firestore equality never matches a missing field
            and row['previous_segment_id'] == previous
        )
        return matches[0] if len(matches) == 1 else None

    def projection_page(
        self,
        limit: int = 100,
        *,
        after: tuple | None = None,
        states: tuple[str, ...] = PROJECTION_DISCOVERY_STATES,
        due_before: float | None = None,
    ) -> tuple[list[str], Any]:
        """Mirror Firestore's legacy or due-clock keyset scan, including inclusive seed cursors."""
        if not states or not set(states) <= set(PROJECTION_OBLIGATION_STATES):
            raise ValueError('projection discovery states must be drain states')
        wanted = set(states)
        ordered = sorted(
            (
                (row['committed_at'], key)
                if due_before is None
                else (row['projection_finish_due_at'], row['committed_at'], key)
            )
            for (table, key), row in self.rows.items()
            if table == 'results'
            and row.get('projection_state') in wanted
            and 'committed_at' in row
            and (
                due_before is None
                or row.get('projection_finish_due_at') is not None
                and row['projection_finish_due_at'] <= float(due_before)
            )
        )
        if after is not None:
            if due_before is not None and len(after) != 3 or due_before is None and after[1] == '':
                ordered = [entry for entry in ordered if entry[0] >= after[0]]
            else:
                ordered = [entry for entry in ordered if entry > after]
        size = max(1, min(limit, 200))
        page = ordered[:size]
        cursor = page[-1] if len(page) == size else None
        return [entry[-1] for entry in page], cursor

    def longest_ready_pending(self, owner_key: str) -> dict | None:
        # Firestore excludes rows without the ordered field, and orders ties by document name.
        rows = [
            (row['ready_at'], segment_id)
            for segment_id in self._pending_by_owner.get(owner_key, ())
            if (row := self.rows[('jobs', segment_id)]).get('state') == 'result_ready' and 'ready_at' in row
        ]
        return deepcopy(self.rows[('jobs', min(rows)[1])]) if rows else None

    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]:
        skip = held_poll_skip_enabled()
        rows = sorted(
            (row['capture_at'], segment_id)
            for segment_id in self._pending_by_owner.get(owner_key, ())
            if (row := self.rows[('jobs', segment_id)]).get('fresh_capture') is True
            and (not skip or row.get('state') not in (None, *MERGE_POLL_TERMINAL_STATES))
        )
        return [deepcopy(self.rows[('jobs', segment_id)]) for _, segment_id in rows[:limit]]

    def ready_owners(
        self, after_owner_key: str | None, limit: int, *, ceiling_owner_key: str | None = None, descending: bool = False
    ) -> list[tuple[str, str | None]]:
        owners = {
            row['owner_key']: row.get('owner_id')
            for (table, _), row in self.rows.items()
            if table == 'jobs'
            and row.get('state') == 'result_ready'
            and row.get('merge_pending')
            and (after_owner_key is None or row['owner_key'] > after_owner_key)
            and (ceiling_owner_key is None or row['owner_key'] <= ceiling_owner_key)
        }
        return sorted(owners.items(), reverse=descending)[: max(1, min(limit, 100))]

    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]:
        keys = sorted(
            key
            for (table, key), row in self.rows.items()
            if table == 'merge_holds' and row.get('held') and (after is None or key > after)
        )
        owners = []
        for key in keys[:limit]:
            job = self.first_pending(key, skip_terminal=False)
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
        for table, segment_id in sorted(self.rows):
            # Earlier deletions may repair this row's next pointer. Production
            # _delete_job re-reads its snapshot inside each transaction too.
            job = self.rows.get((table, segment_id), {})
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
