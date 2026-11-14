"""Transactional document store for batch scheduling; lazy, explicitly namespaced.

Writes are buffered until the body returns so all Firestore reads precede writes.
The transaction callback must be pure; it may be retried by Firestore.
"""

from copy import deepcopy
import hashlib
import logging
import math
import os
import re
import time
from typing import Any, Callable, Protocol, TypeVar

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists, FailedPrecondition, Aborted, InvalidArgument

from config.firestore_read_levers import lever_enabled
from config.batch_pipeline import (
    contention_retry_enabled,
    control_candidate_fanout,
    held_poll_skip_enabled,
    MERGE_POLL_TERMINAL_STATES,
)
from database.batch_pipeline_projection_finish import (
    PROJECTION_FINISH_DUE_FIELD,
    PROJECTION_FINISH_STATES as PROJECTION_FINISH_STATES,
)
from database.batch_pipeline_projection_finish_backfill import backfill_complete
from database.firestore_read_origin import read_origin
from database._client import get_data_plane_firestore_client
from database import record_recovery_gate
from database.batch_pipeline_privacy import assert_batch_write_allowed
from config.firestore_read_levers import lever_enabled
from database.batch_pipeline_recovery import defer_privacy_blocked_record, quarantine_fenced
from database.firestore_transaction_retry import FirestoreContentionExhausted, run_with_transaction_contention_retry
from database.batch_pipeline_transaction_labels import (
    current_operation,
    pull_operation as pull_operation,
)
from utils.sync.stage import collection_name
from utils.batch_pipeline.input_retention import held_input_leg, invalid_staged_clock, staged_enqueue

# Every state an obligation can drain from. Assignment needs only ``pending``;
# completion of persisted/ready rows has its own page. All share one index.
PROJECTION_DISCOVERY_STATES = ('pending', 'persisted', 'ready')
PROJECTION_OBLIGATION_STATES = (*PROJECTION_DISCOVERY_STATES, 'quarantine_held')
PROJECTION_ASSIGNMENT_STATES = ('pending',)


T = TypeVar('T')
logger = logging.getLogger(__name__)


class Transaction(Protocol):
    def get(self, table: str, key: str) -> dict: ...
    def put(self, table: str, key: str, value: dict) -> None: ...
    def patch(self, table: str, key: str, fields: dict) -> None: ...
    def first_pending(self, owner_key: str) -> dict | None: ...
    def first_ready_pending(self, owner_key: str) -> dict | None: ...
    def fresh_first_pending(self, owner_key: str) -> dict | None: ...
    def fresh_first_ready_pending(self, owner_key: str) -> dict | None: ...
    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None: ...
    def service_frontier(self, priority: int) -> float: ...
    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int: ...


class Store(Protocol):
    def run(self, body: Callable[[Transaction], T]) -> T: ...
    def projection_finish_backfill_complete(self) -> bool: ...
    def due(self, state: str, now: float, limit: int) -> list[str]: ...
    def oldest(self, priority: int, *, ready_only: bool) -> float | None: ...
    def oldest_retry(self, priority: int) -> float | None: ...
    def ready_for_capacity(self, priority: int, now: float) -> int: ...
    def control_candidate(
        self, priority: int, pool: str, now: float, *, worker_id: str = '', exclude=()
    ) -> str | None: ...
    def control_candidates(
        self, priority: int, pool: str, now: float, *, worker_id: str = '', fanout: int | None = None
    ) -> list[str]: ...
    def acquire_pull_claim(self, shard: str, token: str, now: float, ttl: float) -> bool: ...
    def quarantine_fenced(self, segment_id: str, now: float) -> bool: ...
    def cancel_fenced_recovery(self, segment_id: str) -> bool: ...

    def defer_privacy_blocked_record(self, segment_id: str, until: float, now: float) -> bool: ...
    def longest_ready_pending(self, owner_key: str) -> dict | None: ...
    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]: ...
    def ready_owners(
        self, after_owner_key: str | None, limit: int, *, ceiling_owner_key: str | None = None, descending: bool = False
    ) -> list[tuple[str, str | None]]: ...
    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]: ...
    def allowance_owners(self, now: float, limit: int) -> list[str]: ...
    def allowance_page(self, owner_key: str | None, after, limit: int) -> list[str]: ...


# Reads that bypass the view cache and go through the raw transaction, by kind.
_DIRECT_READ_KINDS = {
    'first_pending': 'jobs_query',
    'first_ready_pending': 'jobs_query',
    'fresh_first_pending': 'jobs_query',
    'fresh_first_ready_pending': 'jobs_query',
    'ready_predecessor': 'jobs_query',
    'service_frontier': 'control_query',
    'check_privacy': 'privacy',
}


def _note_direct_reads(view: 'FirestoreTransaction') -> None:
    """Record, per attempt, which kinds of direct reads ran, so contention logs can name them.

    Wraps the bound methods on this one view; the class methods stay untouched.
    """
    for name, kind in _DIRECT_READ_KINDS.items():
        method = getattr(view, name)

        def noted(*args, _method=method, _kind=kind, **kwargs):
            view.direct_reads.add(_kind)
            return _method(*args, **kwargs)

        setattr(view, name, noted)


def contention_tables(view: 'FirestoreTransaction') -> tuple[str, str]:
    """Sorted table names a transaction attempt read and wrote. Table names only, never keys."""
    read = sorted({table for table, _ in view.cache} | view.direct_reads)
    wrote = {table for table, _ in (*view.writes, *view.patches)}
    if view.external:
        wrote.add('external')
    if any(table == 'conversations' for table, _ in view.patches):
        # The commit-boundary privacy fence writes one token per owner for conversation patches.
        wrote.add('privacy_fence')
    wrote = sorted(wrote)
    return ','.join(read) or 'none', ','.join(wrote) or 'none'


class FirestoreTransaction:
    def __init__(self, client: Any, namespace: str, transaction: Any, *, read_budget=None):
        self.client = client
        self.namespace = namespace
        self.transaction = transaction
        self.read_budget = read_budget
        self.cache: dict[tuple[str, str], dict] = {}
        self.writes: dict[tuple[str, str], dict] = {}
        self.patches: dict[tuple[str, str], dict] = {}
        # Documents outside the batch tables that join this transaction (the provider-STT outbox row).
        self.external: dict[Any, tuple[Any, dict]] = {}
        # Reads that go through the raw transaction instead of the cache (queries, privacy state):
        # their kind only, so contention logs can name them.
        self.direct_reads: set[str] = set()
        # (control key, priority) activated from a non-transactional frontier hint; the store
        # re-seeds each one after this transaction commits (reseed_hinted_activation).
        self.hinted_activations: set[tuple[str, int]] = set()

    def _note_hinted_activation(self, key: str, priority: int) -> None:
        self.hinted_activations.add((key, int(priority)))

    def _ref(self, table: str, key: str):
        if table == 'conversations':
            uid, conversation_id = key.split('/', 1)
            return self.client.collection('users').document(uid).collection('conversations').document(conversation_id)
        if table == 'content':
            uid, content_id = key.split('/', 1)
            return (
                self.client.collection('users')
                .document(uid)
                .collection(collection_name('sync_content_ledger'))
                .document(content_id)
            )
        return self.client.collection(f'{self.namespace}_{table}').document(key)

    def get(self, table: str, key: str) -> dict:
        address = (table, key)
        if address not in self.cache:
            options = {}
            if self.read_budget is not None:
                options = dict(timeout=self.read_budget.timeout(10), retry=None)
            snapshot = self._ref(table, key).get(transaction=self.transaction, **options)
            self.cache[address] = (snapshot.to_dict() or {}) if snapshot.exists else {}
        return deepcopy({**self.writes.get(address, self.cache[address]), **self.patches.get(address, {})})

    def put(self, table: str, key: str, value: dict) -> None:
        if table == 'conversations':
            raise ValueError('conversation admission requires a field patch, never a document set')
        self.writes[(table, key)] = deepcopy(value)

    def patch(self, table: str, key: str, fields: dict) -> None:
        if table != 'conversations' or set(fields) != {'record_lane_owner'}:
            raise ValueError('only the conversation route owner may be patched by admission')
        self.patches.setdefault((table, key), {}).update(deepcopy(fields))

    def defer_set(self, ref: Any, value: dict) -> None:
        """Set a document outside the batch tables at flush, after every read of this transaction.

        Firestore refuses any transactional read after the first write, and flush itself reads
        privacy state. A joining writer that set its document on the raw transaction mid-body made
        every later read fail (ReadAfterWriteError: staging 11-01, every provider-route upload 503).
        """
        self.external[ref.path] = (ref, deepcopy(value))

    def first_pending(self, owner_key: str) -> dict | None:
        return first_pending(self.client, self.namespace, owner_key, transaction=self.transaction)

    def first_ready_pending(self, owner_key: str) -> dict | None:
        return first_ready_pending(self.client, self.namespace, owner_key, transaction=self.transaction)

    def fresh_first_pending(self, owner_key: str) -> dict | None:
        return fresh_first_pending(self.client, self.namespace, owner_key, ready=False, transaction=self.transaction)

    def fresh_first_ready_pending(self, owner_key: str) -> dict | None:
        return fresh_first_pending(self.client, self.namespace, owner_key, ready=True, transaction=self.transaction)

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        return ready_predecessor(
            self.client, self.namespace, owner_key, priority, segment_id, transaction=self.transaction
        )

    def service_frontier(self, priority: int) -> float:
        # A transactional query locks the top control doc, which workers advance constantly,
        # so every owner (re)activation conflicted with worker control writes and admission
        # exhausted its retries (sync uploads 503 sync_batch_unavailable, 2026-11-07). The
        # frontier only seeds a rejoining owner's credit via max(own, frontier), so a
        # non-transactional hint is enough. Lever 'admission_frontier_hint' 0 restores the query.
        if lever_enabled('admission_frontier_hint'):
            # Outside the transaction: do not report it as a contended transactional read.
            self.direct_reads.discard('control_query')
            return service_frontier(self.client, self.namespace, priority)
        return service_frontier(self.client, self.namespace, priority, transaction=self.transaction)

    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        options = {}
        if self.read_budget is not None:
            options['read_budget'] = self.read_budget
        return assert_batch_write_allowed(
            self.client,
            self.transaction,
            uid,
            conversation_ids=conversation_ids,
            expected_generation=expected_generation,
            **options,
        )

    def flush(self):
        # Conversation patches set record_lane_owner, a batch-privacy authority
        # field, so the commit-boundary fence appends one token write per owner.
        fence_tokens = len({key.split('/', 1)[0] for table, key in self.patches if table == 'conversations'})
        if len(self.writes) + len(self.patches) + len(self.external) + fence_tokens > 450:
            raise RuntimeError('batch transaction write budget exceeded')
        guarded = set()
        for (table, key), value in self.writes.items():
            if table not in {'jobs', 'results', 'coalesce_groups', 'coalesce_sources', 'coalesce_heads'}:
                continue
            job = self.get('jobs', key) if table == 'results' else value
            identity = (job['owner_id'], job.get('conversation_id'), job.get('privacy_generation'))
            if identity in guarded:
                continue
            guarded.add(identity)
            generation = self.check_privacy(
                job['owner_id'],
                conversation_ids=(job['conversation_id'],) if job.get('conversation_id') else (),
                expected_generation=job.get('privacy_generation'),
            )
            if table == 'jobs' and value.get('privacy_generation') is None:
                value['privacy_generation'] = generation
        for (table, key), value in self.writes.items():
            self.transaction.set(self._ref(table, key), value)
        for (table, key), fields in self.patches.items():
            self.transaction.update(self._ref(table, key), fields)
        for ref, value in self.external.values():
            self.transaction.set(ref, value)


class FirestoreStore:
    def allowance_owners(self, now: float, limit: int) -> list[str]:
        return [
            doc.id
            for doc in self.client.collection(f'{self.namespace}_allowance_holds')
            .where('active', '==', True)
            .where('check_at', '<=', now)
            .order_by('check_at')
            .limit(max(1, min(limit, 100)))
            .stream()
        ]

    def allowance_page(self, owner_key: str | None, after, limit: int) -> list[str]:
        query = self.client.collection(f'{self.namespace}_jobs').where('state', '==', 'allowance_held')
        if owner_key is not None:
            query = query.where('owner_key', '==', owner_key)
        query = query.order_by('capture_at').order_by('segment_id')
        if after is not None:
            query = query.start_after({'capture_at': after[0], 'segment_id': after[1]})
        return [doc.id for doc in query.limit(max(1, min(limit, 100))).stream()]

    def __init__(self, namespace: str, *, firestore_client: Any = None):
        # Require a stage-qualified name; never infer dev from the customer project.
        if namespace not in {'batch_pipeline_prod', 'batch_pipeline_dev'} and not re.fullmatch(
            r'batch_pipeline_test_[a-z0-9_]{1,40}', namespace
        ):
            raise ValueError('explicit batch_pipeline_{prod,dev,test_<id>} namespace required')
        self.namespace = namespace
        self._client = firestore_client
        self._require_stage()

    def _require_stage(self):
        if self.namespace.startswith('batch_pipeline_test_'):
            host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
            if not host.startswith(('127.0.0.1:', 'localhost:')):
                raise RuntimeError('test namespace requires a loopback emulator; no cloud fallback')
            if self._client is not None and getattr(self._client, '_emulator_host', None) != host:
                raise RuntimeError('injected test client must be bound to the loopback emulator')
        else:
            stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
            if stage not in {'prod', 'dev'} or self.namespace != f'batch_pipeline_{stage}':
                raise RuntimeError('batch namespace must match explicit runtime stage')

    @property
    def client(self):
        self._require_stage()
        return self._client if self._client is not None else get_data_plane_firestore_client()

    def run(self, body):
        client = self.client
        last_view: list[FirestoreTransaction] = []

        @firestore.transactional
        def commit(transaction):
            view = FirestoreTransaction(client, self.namespace, transaction)
            _note_direct_reads(view)
            last_view[:] = [view]
            result = body(view)
            view.flush()
            return result

        result = self._run_committed(client, commit, last_view)
        for key, priority in sorted(last_view[0].hinted_activations) if last_view else ():
            try:
                reseed_hinted_activation(client, self.namespace, key, priority)
            except Exception as error:  # Best effort: the admission already committed.
                logger.warning(
                    'event=batch_frontier_reseed outcome=failed priority=%s exception_type=%s',
                    priority,
                    type(error).__name__,
                )
        return result

    def _run_committed(self, client, commit, last_view):
        if not contention_retry_enabled():
            return commit(client.transaction())
        # The outer budget owns fresh transaction IDs and all retries. The
        # SDK's same-ID commit loop would multiply the contention window.
        operation = current_operation()
        try:
            return run_with_transaction_contention_retry(
                lambda: client.transaction(max_attempts=1),
                commit,
                operation_name=operation,
            )
        except FirestoreContentionExhausted as error:
            # Name the document kinds the last attempt read and wrote, never keys,
            # so the contended document is visible without exposing owners.
            read, wrote = contention_tables(last_view[0]) if last_view else ('none', 'none')
            error.store_tables = f'read={read} wrote={wrote}'  # type: ignore[attr-defined]
            logger.warning(
                'event=batch_store_contention operation=%s reason=%s read_tables=%s write_tables=%s',
                operation,
                error.reason,
                read,
                wrote,
            )
            raise

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        return due(self.client, self.namespace, state, now, limit)

    def oldest(self, priority: int, *, ready_only: bool = False) -> float | None:
        return oldest(self.client, self.namespace, priority, ready_only=ready_only)

    def ready_for_capacity(self, priority: int, now: float) -> int:
        return ready_for_capacity(self.client, self.namespace, priority, now)

    def oldest_admissible_ready(self, priority: int, now: float) -> float | None:
        return oldest_admissible_ready(self.client, self.namespace, priority, now)

    def control_candidate(self, priority: int, pool: str, now: float, *, worker_id: str = '', exclude=()) -> str | None:
        return control_candidate(self.client, self.namespace, priority, pool, now, worker_id=worker_id, exclude=exclude)

    def control_candidates(
        self, priority: int, pool: str, now: float, *, worker_id: str = '', fanout: int | None = None
    ) -> list[str]:
        return control_candidates(self.client, self.namespace, priority, pool, now, worker_id=worker_id, fanout=fanout)

    def acquire_pull_claim(self, shard: str, token: str, now: float, ttl: float) -> bool:
        # One conditional write, no transaction or retrying read set. A stale
        # hint can only lose the CAS, never authorize two simultaneous owners.
        with pull_operation('claim', shard):
            ref = self.client.collection(f'{self.namespace}_pull_claims').document(shard)
            snapshot = ref.get()
            if (snapshot.to_dict() or {}).get('expires_at', 0) > now:
                return False
            value = {'token': token, 'expires_at': now + ttl}
            try:
                if snapshot.exists:
                    ref.update(value, option=firestore.LastUpdateOption(snapshot.update_time), retry=None)
                else:
                    ref.create(value, retry=None)
            except (AlreadyExists, FailedPrecondition, Aborted):
                logger.info('event=batch_shard_contention operation=batch_claim shard=%s outcome=busy', shard)
                return False
            return True

    def oldest_retry(self, priority: int) -> float | None:
        return oldest_retry(self.client, self.namespace, priority)

    def quarantine_fenced(self, segment_id: str, now: float) -> bool:
        return quarantine_fenced(self.client, self.namespace, segment_id, now)

    def cancel_fenced_recovery(self, segment_id: str) -> bool:
        """Revocation-only write, allowed after privacy rejects ordinary job writes."""
        from database.batch_pipeline_privacy import BatchPrivacyBlocked
        from database.batch_pipeline_projection_protocol import normalized_binding

        ref = self.client.collection(f'{self.namespace}_jobs').document(segment_id)

        @firestore.transactional
        def cancel(transaction):
            job = ref.get(transaction=transaction).to_dict() or {}
            if not job or not job.get('recovery'):
                return False
            binding = normalized_binding(job['projection_binding'])
            ids = [value for value in (job.get('conversation_id'), binding.target_conversation_id) if value]
            ids.extend(job.get('conversation_ids') or [])
            try:
                assert_batch_write_allowed(
                    self.client,
                    transaction,
                    binding.owner_id,
                    conversation_ids=ids,
                    expected_generation=binding.privacy_generation,
                )
            except BatchPrivacyBlocked:
                transaction.update(ref, {'recovery_state': 'cancelled'})
                return True
            return False

        cancelled = cancel(self.client.transaction())
        if cancelled:
            from database.batch_pipeline_shadow_hook import mirror_refresh

            mirror_refresh(self.namespace, [('jobs', segment_id)])  # A2 shadow: no-op unless shadow mode
        return cancelled

    def defer_privacy_blocked_record(self, segment_id: str, until: float, now: float) -> bool:
        return defer_privacy_blocked_record(self.client, self.namespace, segment_id, until, now)

    def longest_ready_pending(self, owner_key: str) -> dict | None:
        # A hint read outside any transaction; the bypass transaction re-verifies it.
        return longest_ready_pending(self.client, self.namespace, owner_key)

    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]:
        # A hint read outside any transaction; the fresh-first transaction re-verifies it.
        return fresh_pending(self.client, self.namespace, owner_key, limit)

    def ready_owners(
        self, after_owner_key: str | None, limit: int, *, ceiling_owner_key: str | None = None, descending: bool = False
    ) -> list[tuple[str, str | None]]:
        return ready_owners(
            self.client,
            self.namespace,
            after_owner_key,
            limit,
            ceiling_owner_key=ceiling_owner_key,
            descending=descending,
        )

    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]:
        return held_merge_owners(self.client, self.namespace, limit, after=after)

    def projection_finish_backfill_complete(self) -> bool:
        return backfill_complete(self.client, self.namespace)

    def projection_pending(self, limit: int = 100) -> list[str]:
        return projection_pending(self.client, self.namespace, limit)

    def projection_page(
        self,
        limit: int = 100,
        *,
        after: tuple | None = None,
        states: tuple[str, ...] = PROJECTION_DISCOVERY_STATES,
        due_before: float | None = None,
    ) -> tuple[list[str], Any]:
        return projection_page(self.client, self.namespace, limit, after=after, states=states, due_before=due_before)

    def projection_successor(self, owner_key: str, previous: str | None) -> str | None:
        return projection_successor(self.client, self.namespace, owner_key, previous)


def projection_pending(client: Any, namespace: str, limit: int = 100) -> list[str]:
    return projection_page(client, namespace, limit)[0]


def projection_page(
    client: Any,
    namespace: str,
    limit: int = 100,
    *,
    after: tuple | None = None,
    states: tuple[str, ...] = PROJECTION_DISCOVERY_STATES,
    due_before: float | None = None,
) -> tuple[list[str], Any]:
    """Stable keyset page; the cursor survives removal of its source row.

    __name__ breaks committed_at ties (including siblings committed together).
    Cursor values are discovery hints, never authorization or ordering fences.
    ``states`` narrows the same ``in`` filter to a subset of the drain states.
    A seed cursor ``(committed_at, '')`` starts at that time, before every key
    (the follow-up desync offset); keys are never empty.

    ``due_before`` adds the dark finish-backoff range filter: only rows whose
    ``projection_finish_due_at`` has passed. That field leads the ordering
    because Firestore serves a range filter on the first ordered field only, so
    the cursor becomes ``(due_at, committed_at, key)`` and a seed
    ``(due_at,)`` starts at that clock.
    """
    if not states or not set(states) <= set(PROJECTION_OBLIGATION_STATES):
        raise ValueError('projection discovery states must be drain states')
    collection = client.collection(f'{namespace}_results')
    if due_before is None:
        query = collection.where('projection_state', 'in', list(states)).order_by('committed_at').order_by('__name__')
    else:
        query = (
            collection.where('projection_state', 'in', list(states))
            .where(PROJECTION_FINISH_DUE_FIELD, '<=', float(due_before))
            .order_by(PROJECTION_FINISH_DUE_FIELD)
            .order_by('committed_at')
            .order_by('__name__')
        )
    seeded = after is not None and len(after) == 2 and after[1] == ''
    if due_before is not None:
        if after is not None and len(after) == 3:
            query = query.start_after(
                {
                    PROJECTION_FINISH_DUE_FIELD: after[0],
                    'committed_at': after[1],
                    '__name__': collection.document(after[2]),
                }
            )
        elif after is not None:
            query = query.start_at({PROJECTION_FINISH_DUE_FIELD: after[0]})
    elif after is not None and seeded:
        query = query.start_at({'committed_at': after[0]})
    elif after is not None:
        query = query.start_after({'committed_at': after[0], '__name__': collection.document(after[-1])})
    size = max(1, min(limit, 200))
    docs = list(query.limit(size).stream())
    # Wrap even when blocked rows remain. Rows inserted behind the cursor are
    # revisited on the next cycle; no durable obligation is skipped or mutated.
    if len(docs) == size:
        last = docs[-1].to_dict()
        if due_before is None:
            cursor = (last['committed_at'], docs[-1].id)
        else:
            cursor = (last[PROJECTION_FINISH_DUE_FIELD], last['committed_at'], docs[-1].id)
    else:
        cursor = None
    return [doc.id for doc in docs], cursor


def projection_successor(client: Any, namespace: str, owner_key: str, previous: str | None) -> str | None:
    """The owner's result committed directly after ``previous`` in its log.

    The result log is a per-owner singly linked list; two matches fail closed.
    A discovery hint only: the transactional predecessor check still decides.
    """
    docs = list(
        client.collection(f'{namespace}_results')
        .where('owner_key', '==', owner_key)
        .where('previous_segment_id', '==', previous)
        .order_by('__name__')
        .limit(2)
        .stream()
    )
    return docs[0].id if len(docs) == 1 else None


def first_pending(
    client: Any, namespace: str, owner_key: str, *, transaction: Any = None, skip_terminal: bool = True
) -> dict | None:
    query = (
        client.collection(f'{namespace}_jobs').where('owner_key', '==', owner_key).where('merge_pending', '==', True)
    )
    base = query
    skip = skip_terminal and held_poll_skip_enabled()
    if skip:
        query = query.where('state', 'not-in', list(MERGE_POLL_TERMINAL_STATES))
    try:
        docs = list(query.order_by('capture_at').order_by('segment_id').limit(1).stream(transaction=transaction))
    except (FailedPrecondition, InvalidArgument):
        if not skip:
            raise
        docs = list(base.order_by('capture_at').order_by('segment_id').limit(1).stream(transaction=transaction))
    return docs[0].to_dict() if docs else None


def first_ready_pending(client: Any, namespace: str, owner_key: str, *, transaction: Any = None) -> dict | None:
    """The owner's earliest-captured pending row that already has a result (bounded head wait)."""
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .where('state', '==', 'result_ready')
        .order_by('capture_at')
        .order_by('segment_id')
        .limit(1)
        .stream(transaction=transaction)
    )
    return docs[0].to_dict() if docs else None


def longest_ready_pending(client: Any, namespace: str, owner_key: str) -> dict | None:
    """The owner's pending result that has waited longest; rows without ``ready_at`` never match.

    Non-transactional discovery hint: it takes no transactional query lock.
    """
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .where('state', '==', 'result_ready')
        .order_by('ready_at')
        .limit(1)
        .stream()
    )
    return docs[0].to_dict() if docs else None


def ready_owners(
    client: Any,
    namespace: str,
    after_owner_key: str | None,
    limit: int,
    *,
    ceiling_owner_key: str | None = None,
    descending: bool = False,
) -> list[tuple[str, str | None]]:
    # Seek past the entire owner, never through its potentially huge block.
    query = (
        client.collection(f'{namespace}_jobs')
        .where('state', '==', 'result_ready')
        .where('merge_pending', '==', True)
        .order_by('owner_key', direction='DESCENDING' if descending else 'ASCENDING')
    )
    if ceiling_owner_key is not None:
        query = query.where('owner_key', '<=', ceiling_owner_key)
    owners = []
    for _ in range(max(1, min(limit, 100))):
        page = query if after_owner_key is None else query.where('owner_key', '>', after_owner_key)
        docs = list(page.limit(1).stream())
        if not docs:
            break
        row = docs[0].to_dict()
        after_owner_key = row['owner_key']
        owners.append((after_owner_key, row.get('owner_id')))
    return owners


def held_merge_owners(
    client: Any, namespace: str, limit: int, *, after: str | None = None
) -> list[tuple[str, str | None]]:
    """Owners whose catch-up commits are held for projection depth: (owner key, owner id or None).

    Ordered by owner key after ``after`` so callers can rotate through every
    marker. The marker stores no user ID; the owner's earliest pending job
    supplies it. None means nothing is pending, so the marker is stale.
    """
    collection = client.collection(f'{namespace}_merge_holds')
    query = collection.where('held', '==', True).order_by('__name__')
    if after is not None:
        query = query.start_after({'__name__': collection.document(after)})
    marks = query.limit(max(1, min(limit, 100))).stream()
    owners = []
    for mark in marks:
        job = first_pending(client, namespace, mark.id, skip_terminal=False)
        owners.append((mark.id, job.get('owner_id') if job else None))
    return owners


def fresh_first_pending(client: Any, namespace: str, owner_key: str, *, ready: bool, transaction: Any) -> dict | None:
    query = (
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .where('fresh_capture', '==', True)
    )
    if ready:
        query = query.where('state', '==', 'result_ready')
    return next(
        (
            doc.to_dict()
            for doc in query.order_by('capture_at').order_by('segment_id').limit(1).stream(transaction=transaction)
        ),
        None,
    )


def fresh_pending(client: Any, namespace: str, owner_key: str, limit: int) -> list[dict]:
    """The owner's earliest-captured pending fresh rows, ready or not (fresh-first merge).

    Non-transactional discovery hint: it takes no transactional query lock.
    """
    query = (
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .where('fresh_capture', '==', True)
    )
    base = query
    skip = held_poll_skip_enabled()
    if skip:
        query = query.where('state', 'not-in', list(MERGE_POLL_TERMINAL_STATES))
    try:
        return [
            doc.to_dict()
            for doc in query.order_by('capture_at').order_by('segment_id').limit(max(1, min(limit, 32))).stream()
        ]
    except (FailedPrecondition, InvalidArgument):
        if not skip:
            raise
        return [
            doc.to_dict()
            for doc in base.order_by('capture_at').order_by('segment_id').limit(max(1, min(limit, 32))).stream()
        ]


def ready_predecessor(
    client: Any, namespace: str, owner_key: str, priority: int, segment_id: str, *, transaction: Any = None
) -> dict | None:
    # Leased/completed rows retain stale next links. Only a ready row in this
    # owner's priority FIFO can be the live predecessor. Two matches fail closed.
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('priority', '==', priority)
        .where('state', '==', 'ready')
        .where('next', '==', segment_id)
        .order_by('__name__')
        .limit(2)
        .stream(transaction=transaction)
    )
    return docs[0].to_dict() if len(docs) == 1 else None


def promote_record_recoveries(client: Any, namespace: str, now: float, limit: int = 100, *, budget: Any = None) -> int:
    """Resume accepted bytes from the active repair path even after mode rollback."""
    if budget is not None:
        budget.check()
    promoted = 0
    for segment in due(client, namespace, record_recovery_gate.WAITING_STATE, now, limit):
        if budget is not None:
            budget.check()
        promoted += record_recovery_gate.promote(client, namespace, segment, now)
    return promoted


def due(client: Any, namespace: str, state: str, now: float, limit: int = 100) -> list[str]:
    if state not in {'leased', 'retry', 'result_ready', 'record_pending', record_recovery_gate.WAITING_STATE}:
        raise ValueError('only recoverable states may be scanned')
    field = {
        'leased': 'lease_until',
        'retry': 'available_at',
        'result_ready': 'enqueued_at',
        'record_pending': 'available_at',
        record_recovery_gate.WAITING_STATE: 'available_at',
    }[state]
    if state == 'record_pending':
        promote_record_recoveries(client, namespace, now, limit)
    docs = (
        client.collection(f'{namespace}_jobs')
        .where('state', '==', state)
        .where(field, '<=', now)
        .order_by(field)
        .limit(max(1, min(limit, 500 if state == 'record_pending' else 100)))
        .stream()
    )
    return [doc.id for doc in docs]


# Bounded FIFO prefix walked past policy holds and dispositioned rows. An
# exempt prefix with a sentinel exports NaN: an unmeasured commitment may sit
# beyond the bound. The observer and pager report that incomplete scan as
# blindness; retiring holds themselves stays with the custody track.
OLDEST_POLICY_HOLD_SCAN_LIMIT = 500


def allowance_held_count(client: Any, namespace: str) -> int:
    """Hourly leader census, outside the pending-work sample and never a row walk."""
    return int(client.collection(f'{namespace}_jobs').where('state', '==', 'allowance_held').count().get()[0][0].value)


def is_allowance_policy_hold(job: dict[str, Any]) -> bool:
    """A durable end-of-allowance hold parks the obligation outside compute.

    scheduler.defer records the decision on the job document; an
    allowance_exhausted hold is a policy parking state, not a compute
    commitment, so age-based safety proxies must not measure it (2026-10-25:
    131 such holds, ~26h old, kept the in-cluster guard's
    uncommitted_job_age_over_30m proxy tripped permanently and masked real
    wedges). An unevaluated re-evaluation clears the decision to BLIND without
    ending the hold; until an allow or another hold replaces it, the job's
    last_policy_hold still classifies it (2026-10-27: held jobs re-read as
    decisionless between evaluations flapped the proxy to ~54h).
    """
    decision = job.get('compute_decision')
    if not decision:
        return (job.get('last_policy_hold') or {}).get('reason') == 'allowance_exhausted'
    return decision.get('outcome') == 'held' and decision.get('reason') == 'allowance_exhausted'


def is_policy_hold(job: dict[str, Any], now: float | None = None) -> bool:
    """A parked obligation the uncommitted-age proxy must not measure: an allowance hold, or a live
    ``vendor_held`` provider unit (vendor_route_contracts.is_vendor_policy_hold). A vendor hold
    whose redrive is overdue past the stale grace is measured again, so a dead redrive surfaces.
    """
    if is_allowance_policy_hold(job):
        return True
    if job.get('state') != 'vendor_held':
        return False
    from config.batch_pipeline_vendor_failover import held_redrive_seconds, held_stale_grace_seconds
    from utils.batch_pipeline.vendor_route_contracts import is_vendor_policy_hold

    return is_vendor_policy_hold(
        job,
        time.time() if now is None else now,
        redrive_seconds=held_redrive_seconds(),
        stale_grace_seconds=held_stale_grace_seconds(),
    )


def ready_for_capacity(client: Any, namespace: str, priority: int, now: float) -> int:
    """Count work awaiting a first/re-authorized attempt, never held legacy debt.

    New admission explicitly records unattempted; existing workers already
    replace it with allowed/held or clear it on an unevaluated refusal. Reusing
    that authoritative state avoids a new eligibility bit that old workers
    would fail to clear during a mixed-version roll. Unmarked legacy jobs remain
    durable/drainable but cannot buy GPUs. This hint never grants paid compute.
    """
    query = (
        client.collection(f'{namespace}_jobs')
        .where('priority', '==', priority)
        .where('state', '==', 'ready')
        .where('merge_pending', '==', True)
        .where('compute_decision.outcome', 'in', ['unattempted', 'allowed'])
        .where('available_at', '<=', now)
    )
    count = query.count().get()[0][0].value
    # The pinned SDK decodes integer_value=0 through ``integer or double``,
    # yielding 0.0. Preserve that real empty result; do not coerce missing,
    # fractional, negative or otherwise malformed responses into capacity.
    if type(count) is float and count == 0.0:
        count = 0
    if type(count) is not int or count < 0:
        raise ValueError('nonnegative integer capacity count required')
    return count


# Bounded ready prefix the vendor-overflow backlog read walks (route selection, one read per
# refresh in the healthy case). Policy holds and deferred rows at the head are skipped.
ADMISSIBLE_READY_SCAN_LIMIT = 20


def is_admissible_ready(job: dict[str, Any], now: float) -> bool:
    """The ``ready_for_capacity`` predicate on one ready row: work a GPU would run if it had a lane."""
    decision = job.get('compute_decision')
    available_at = job.get('available_at')
    return (
        job.get('merge_pending') is True
        and isinstance(decision, dict)
        and decision.get('outcome') in ('unattempted', 'allowed')
        and isinstance(available_at, (int, float))
        and available_at <= now
        and not is_policy_hold(job, now)
    )


def oldest_admissible_ready(client: Any, namespace: str, priority: int, now: float) -> float | None:
    """Enqueue time of the oldest admissible ready unit, or None when the bounded prefix has none.

    Same index as ``oldest(ready_only=True)``. A due allowance hold back in ``ready`` carries an
    hours-old enqueue time, so it is skipped rather than read as GPU backlog. A prefix made only of
    skipped rows reads as no backlog: overflow then fails toward GPU, which is today's routing.
    """
    docs = (
        client.collection(f'{namespace}_jobs')
        .where('priority', '==', priority)
        .where('state', '==', 'ready')
        .order_by('enqueued_at')
        .limit(ADMISSIBLE_READY_SCAN_LIMIT)
        .stream()
    )
    for doc in docs:
        job = doc.to_dict()
        if is_admissible_ready(job, now):
            return job['enqueued_at']
    return None


def oldest(client: Any, namespace: str, priority: int, *, ready_only: bool = False) -> float | None:
    query = client.collection(f'{namespace}_jobs').where('priority', '==', priority)
    if ready_only:
        docs = list(query.where('state', '==', 'ready').order_by('enqueued_at').limit(1).stream())
        return docs[0].to_dict()['enqueued_at'] if docs else None
    # The uncommitted-age proxy must measure the oldest real commitment: walk a
    # bounded prefix of the FIFO and skip allowance and vendor policy holds. Early return
    # keeps the healthy case a one-document read; a sentinel row beyond the
    # bound (limit + 1) distinguishes truncation from a FIFO that happens to be
    # exactly as long as the bound.
    docs = iter(
        query.where('merge_pending', '==', True)
        .order_by('enqueued_at')
        .limit(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)
        .stream()
    )
    scanned = 0
    for doc in docs:
        scanned += 1
        if scanned > OLDEST_POLICY_HOLD_SCAN_LIMIT:
            break  # the sentinel row exists: the scan was truncated
        job = doc.to_dict()
        if is_queue_dispositioned(job) or is_policy_hold(job):
            continue
        return job['enqueued_at']
    if scanned > OLDEST_POLICY_HOLD_SCAN_LIMIT:
        # An unmeasured commitment may exist beyond the bound. NaN is an
        # incomplete measurement, never a hold misreported as late work or a
        # false fresh zero. The guard and alert route treat this as blindness.
        return float('nan')
    return None


def control_candidate(
    client: Any, namespace: str, priority: int, pool: str, now: float, *, worker_id: str = '', exclude=()
) -> str | None:
    candidates = control_candidates(client, namespace, priority, pool, now, worker_id=worker_id)
    return next((key for key in candidates if key not in exclude), None)


def control_candidates(
    client: Any, namespace: str, priority: int, pool: str, now: float, *, worker_id: str = '', fanout: int | None = None
) -> list[str]:
    if priority not in (0, 1, 2) or pool not in {'batch', 'live'}:
        raise ValueError('bounded priority and pool required')
    prefix = f'p{priority}_'
    service, available = prefix + 'service', prefix + pool + '_available_at'
    docs = list(
        client.collection(f'{namespace}_control')
        .where(prefix + 'active', '==', True)
        .where(service, '>=', 0)
        .where(available, '<=', now)
        .order_by(service)
        .order_by(available)
        .limit(control_candidate_fanout(fanout) if worker_id else 1)
        .stream()
    )
    if worker_id:
        # Service remains the primary fairness key. Only equal-service shards
        # use worker affinity, and a busy shard can be skipped without writes.
        docs.sort(key=lambda doc: (doc.to_dict()[service], hashlib.sha256(f'{worker_id}:{doc.id}'.encode()).digest()))
    return [doc.id for doc in docs]


def is_queue_dispositioned(job: dict[str, Any]) -> bool:
    """Custody has left the compute queue; recovery/projection have their own alarms.

    A completed terminal marker alone is insufficient: result_ready still owes
    its ordered commit. Unknown states remain measured, so schema drift fails closed.
    """
    return job.get('state') in {'dead', 'quarantined', 'committed', 'privacy_blocked'}


def oldest_retry(client: Any, namespace: str, priority: int) -> float | None:
    docs = iter(
        client.collection(f'{namespace}_jobs')
        .where('priority', '==', priority)
        .where('retry_started_at', '>=', 0)
        .order_by('retry_started_at')
        .limit(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)
        .stream()
    )
    for index, doc in enumerate(docs):
        if index == OLDEST_POLICY_HOLD_SCAN_LIMIT:
            return float('nan')
        job = doc.to_dict()
        if not is_queue_dispositioned(job) and not is_policy_hold(job):
            return job['retry_started_at']
    return None


# 2-hour timeliness alarm (David, 2026-11-02). Indexes: jobs (state, enqueued_at), the capacity index, jobs
# (priority, retry_started_at), jobs (state, recovery_state, enqueued_at) and results (projection_state, committed_at).
# provider_running is in-flight vendor work; provider_pending stays out (allowance holds park it for a
# day) and is exported by the provider-stage stock gauges instead.
TIMELINESS_ACTIVE_STATES = ('leased', 'provider_running', 'result_ready')
TIMELINESS_UNCOMMITTED_STATES = (*TIMELINESS_ACTIVE_STATES, 'ready', 'retry', 'vendor_held')
TIMELINESS_HOLD_SCAN_LIMIT = 20
TIMELINESS_PROJECTION_SCAN_LIMIT = 50
TIMELINESS_BACKLOG_COUNT_LIMIT = 10_000


def is_timeliness_hold(job: dict[str, Any], now: float) -> bool:
    """A deliberate admission refusal (allowance, budget, fair use, daily ceiling) or a live vendor hold."""
    return is_policy_hold(job, now) or (job.get('compute_decision') or {}).get('outcome') == 'held'


def is_terminal_empty(job: dict[str, Any]) -> bool:
    """Settled empty_asr, failed held, with no recoverable speech: measured held VAD speech exactly 0."""
    return (
        job.get('state') == 'quarantined'
        and job.get('recovery_state') == 'failed_held'
        and ((job.get('recovery') or {}).get('failure') or {}).get('reason') == 'empty_asr'
        and job.get('measured_held_vad_speech_seconds') == 0
    )


@read_origin('job:batch_pipeline_store:timeliness_sample')
def timeliness_sample(
    client: Any,
    namespace: str,
    epoch: float,
    now: float,
    sla: float,
    *,
    terminal_empty_processed: bool = False,
) -> dict[str, Any]:
    """Unpublished units by wait leg: oldest ``enqueued_at`` at or after ``epoch``, counts past ``sla`` for the
    new cohort, and backlog counts before ``epoch``. With ``batch_timeliness_leader`` on, each backlog
    count is capped at 10,000 index entries: values at the cap are lower bounds. The assignment-held
    backlog alert treats saturation as actionable stock, independently of its one-hour growth condition.
    Lever 0 restores the exact, unbounded historical counts. Post-epoch counts stay exact.

    All-time companion counts are not computed here; see ``timeliness_all_time_counts``.

    ``terminal_empty`` is always counted. With ``terminal_empty_processed`` those units leave the quarantined
    leg: its count subtracts them exactly, so a page of them can hide a younger unit but never a breach.

    Holds must never fill a bound: ``ready`` is read through the capacity index with the decision filtered in
    the query, admission holds park in ``retry`` without ``retry_started_at`` (compute-failure retries are read
    by that field), and live ``vendor_held`` units are walked apart from active work. Results carry no enqueue
    time, so the projection leg reads the jobs behind its oldest committed rows; its counts clock from
    ``committed_at``, a lower bound. ``truncated`` names a leg whose bounded prefix may hide an older unit.
    """
    jobs = client.collection(f'{namespace}_jobs')
    results = client.collection(f'{namespace}_results')
    due = now - sla
    invalid_staged_clocks: set[str] = set()
    unclocked_staged_inputs: set[str] = set()

    def first(query, field):
        docs = list(query.order_by(field).limit(1).stream())
        return docs[0].to_dict()[field] if docs else None

    def first_valid_clock(query, field, predicate=None, clock=None):
        # Metrics-only: a malformed clock must not mask a later dated held row.
        # Keep limit(1) on each RPC: valid stock still costs one document read.
        query = query.order_by(field).limit(1)
        examined = 0
        oldest = None
        while docs := list(query.stream()):
            # Do not publish a false healthy zero or run an unbounded fleet scan.
            # The existing sample-error/staleness path reports incomplete ages.
            examined += 1
            if predicate is not None and examined > 128:
                raise RuntimeError('staged input age scan incomplete')
            doc = docs[0]
            job = doc.to_dict()
            if clock is not None and held_input_leg(job) and invalid_staged_clock(job):
                invalid_staged_clocks.add(doc.id)
                if staged_enqueue(job) is None:
                    unclocked_staged_inputs.add(doc.id)
            started = job.get(field)
            if clock is not None and oldest is not None and isinstance(started, (int, float)) and started >= oldest:
                return oldest  # A restage cannot predate its admission; later admissions cannot win.
            if (
                isinstance(started, (int, float))
                and not isinstance(started, bool)
                and math.isfinite(started)
                and started > 0
                and (predicate is None or predicate(doc.to_dict()))
            ):
                if clock is None:
                    return started
                stamp = clock(doc.to_dict())
                if stamp is not None and stamp >= started:
                    oldest = min(oldest, stamp) if oldest is not None else stamp
                    if oldest == started:
                        return oldest
            query = query.start_after(doc)
        return oldest

    def count(query):
        return int(query.count().get()[0][0].value)

    def backlog_count(query):
        if lever_enabled('batch_timeliness_leader'):
            query = query.limit(TIMELINESS_BACKLOG_COUNT_LIMIT)
        return count(query)

    def walk(query, field):
        docs = [doc.to_dict() for doc in query.order_by(field).limit(TIMELINESS_HOLD_SCAN_LIMIT).stream()]
        admitted = [
            job['enqueued_at'] for job in docs if job['enqueued_at'] >= epoch and not is_timeliness_hold(job, now)
        ]
        full = len(docs) == TIMELINESS_HOLD_SCAN_LIMIT
        # Ordered by admission, the first unheld row is the oldest. Ordered by any other clock, a full page
        # may hide an older admission behind it.
        return min(admitted, default=None), full and (not admitted or field != 'enqueued_at')

    def committed_walk(query):
        rows = list(
            query.where('committed_at', '>=', epoch)
            .order_by('committed_at')
            .limit(TIMELINESS_PROJECTION_SCAN_LIMIT)
            .stream()
        )
        refs = [jobs.document(row.id) for row in rows]
        admitted = [
            started
            for snapshot in (client.get_all(refs, field_paths=['enqueued_at']) if refs else [])
            for started in [(snapshot.to_dict() or {}).get('enqueued_at')]
            if isinstance(started, (int, float)) and started >= epoch
        ]
        return min(admitted, default=None), len(rows) == TIMELINESS_PROJECTION_SCAN_LIMIT

    walks = [
        walk(
            jobs.where('state', 'in', list(TIMELINESS_ACTIVE_STATES)).where('enqueued_at', '>=', epoch), 'enqueued_at'
        ),
        walk(jobs.where('state', '==', 'vendor_held').where('enqueued_at', '>=', epoch), 'enqueued_at'),
    ]
    for priority in (0, 1, 2):
        ready = (
            jobs.where('priority', '==', priority)
            .where('state', '==', 'ready')
            .where('merge_pending', '==', True)
            .where('compute_decision.outcome', 'in', ['unattempted', 'allowed'])
            .where('available_at', '>=', epoch)
        )
        walks.append(walk(ready, 'available_at'))
        walks.append(
            walk(jobs.where('priority', '==', priority).where('retry_started_at', '>=', epoch), 'retry_started_at')
        )
    projection = results.where('projection_state', 'in', list(PROJECTION_DISCOVERY_STATES))
    projected, projection_truncated = committed_walk(projection)
    quarantined = jobs.where('state', '==', 'quarantined')
    legs = {
        'quarantined': (quarantined, 'enqueued_at'),
        # A quarantined projection receipt holds its committed job in the same transaction: the text never
        # reached the conversation.
        'assignment_held': (
            jobs.where('state', '==', 'committed').where('recovery_state', '==', 'held'),
            'enqueued_at',
        ),
        'projection': (projection, 'committed_at'),
        # Ready receipts already in the conversation plus assignment holds; only the ledger waits. Visible only.
        'quarantine_held_rows': (results.where('projection_state', '==', 'quarantine_held'), 'committed_at'),
        'held_expired_rows': (
            results.where('projection_state', '==', 'quarantine_held').where(
                'held_expired_reason', '==', 'held_expired'
            ),
            'committed_at',
        ),
        # A subset of quarantined, matching is_terminal_empty. Visible only.
        'terminal_empty': (
            quarantined.where('recovery_state', '==', 'failed_held')
            .where('recovery.failure.reason', '==', 'empty_asr')
            .where('measured_held_vad_speech_seconds', '==', 0),
            'enqueued_at',
        ),
    }
    over_sla = {
        leg: count(query.where(field, '>=', epoch).where(field, '<', due)) if due > epoch else 0
        for leg, (query, field) in legs.items()
    }
    if terminal_empty_processed:
        over_sla['quarantined'] -= over_sla['terminal_empty']
        docs = [
            doc.to_dict()
            for doc in quarantined.where('enqueued_at', '>=', epoch)
            .order_by('enqueued_at')
            .limit(TIMELINESS_HOLD_SCAN_LIMIT)
            .stream()
        ]
        kept = [job['enqueued_at'] for job in docs if not is_terminal_empty(job)]
        # Past a full page of exempt rows the exact count still names a breach, and the last row bounds its age.
        quarantined_oldest = kept[0] if kept else docs[-1]['enqueued_at'] if over_sla['quarantined'] and docs else None
    else:
        quarantined_oldest = first(quarantined.where('enqueued_at', '>=', epoch), 'enqueued_at')
    staged = [
        first_valid_clock(
            jobs.where('state', '==', state).where('recovery_state', 'in', ['held', 'failed_held']),
            'enqueued_at',
            lambda job: held_input_leg(job) is not None and staged_enqueue(job) is not None,
            clock=staged_enqueue,
        )
        for state in ('quarantined', 'committed')
    ]
    sample: dict[str, Any] = {
        # Bounded-prefix observations, not a distinct-row fleet census.
        'staged_input_clock_invalid': len(invalid_staged_clocks),
        # Alert-only stock ages: no epoch or rolling-cohort lower bound. Indexed oldest-first
        # reads stay exact even when the stock is larger than a scan page; held legs skip invalid clocks.
        'drain_oldest': first(projection, 'committed_at'),
        'held_oldest': {
            # Current restage time when stamped; admission proxy for legacy objects. Never GCS metadata.
            'staged_input': min((stamp for stamp in staged if stamp is not None), default=None),
            'quarantine_held': first_valid_clock(legs['quarantine_held_rows'][0], 'committed_at'),
            'held_expired': first_valid_clock(legs['held_expired_rows'][0], 'committed_at'),
            'assignment_held': first_valid_clock(legs['assignment_held'][0], 'enqueued_at'),
            'record_pending': first_valid_clock(jobs.where('state', '==', 'record_pending'), 'enqueued_at'),
        },
        'new_oldest': {
            'uncommitted': min((started for started, _ in walks if started is not None), default=None),
            'quarantined': quarantined_oldest,
            'assignment_held': first(legs['assignment_held'][0].where('enqueued_at', '>=', epoch), 'enqueued_at'),
            'projection': projected,
            'held_expired_rows': first(legs['held_expired_rows'][0].where('committed_at', '>=', epoch), 'committed_at'),
            'quarantine_held_rows': first(
                legs['quarantine_held_rows'][0].where('committed_at', '>=', epoch), 'committed_at'
            ),
        },
        'new_over_sla': over_sla,
        'backlog': {
            'uncommitted_incl_holds': backlog_count(
                jobs.where('state', 'in', list(TIMELINESS_UNCOMMITTED_STATES)).where('enqueued_at', '<', epoch)
            ),
            **{leg: backlog_count(query.where(field, '<', epoch)) for leg, (query, field) in legs.items()},
        },
        'truncated': {
            'uncommitted': any(truncated for _, truncated in walks),
            'projection': projection_truncated,
            'staged_input': bool(unclocked_staged_inputs),
        },
    }
    return sample


def timeliness_all_time_counts(client: Any, namespace: str) -> dict[str, int]:
    """Exact all-time counts for the companion legs, with no epoch filter and no document walk.

    Diagnostic only. Run by the metrics caller after the epoch gauges publish, never on scrape and
    never inside ``timeliness_sample``. Each leg fails alone: a failed COUNT logs and is omitted, so
    the caller clears that series rather than exporting a fake zero.
    """
    jobs = client.collection(f'{namespace}_jobs')
    results = client.collection(f'{namespace}_results')
    legs = {
        'quarantine_held_rows': results.where('projection_state', '==', 'quarantine_held'),
        'assignment_held': jobs.where('state', '==', 'committed').where('recovery_state', '==', 'held'),
        'projection': results.where('projection_state', 'in', list(PROJECTION_DISCOVERY_STATES)),
    }
    counts: dict[str, int] = {}
    for leg, query in legs.items():
        try:
            counts[leg] = int(query.count().get()[0][0].value)
        except Exception as error:
            logger.warning(
                'event=batch_timeliness_all_time_sample outcome=unavailable leg=%s exception_type=%s',
                leg,
                type(error).__name__,
            )
    return counts


def reseed_hinted_activation(client: Any, namespace: str, key: str, priority: int) -> bool:
    """Lift a just-activated shard to the frontier as of now, if no pull has reached it yet.

    Admission seeded the shard from a frontier read outside its transaction (lever
    admission_frontier_hint); pulls that committed meanwhile were unseen. This re-reads the
    frontier after that commit, again without a transaction, and lifts only while the
    activation marker is still set, in a transaction on this shard's own control doc. A pull
    that got there first consumed the marker, so waiting is never charged to the joiner.
    """
    service_key, marker = f'p{priority}_service', f'p{priority}_frontier_hint'
    # Runs before the upload is acknowledged: one attempt, short RPC deadlines, no retries.
    frontier = service_frontier(client, namespace, priority, timeout=RESEED_RPC_TIMEOUT_SECONDS)
    reference = client.collection(f'{namespace}_control').document(key)

    @firestore.transactional
    def lift(transaction):
        snapshot = reference.get(transaction=transaction, timeout=RESEED_RPC_TIMEOUT_SECONDS, retry=None)
        control = (snapshot.to_dict() or {}) if snapshot.exists else {}
        if not control.get(marker):
            return False
        transaction.update(
            reference, {service_key: max(control.get(service_key, 0.0), frontier), marker: firestore.DELETE_FIELD}
        )
        return True

    return lift(client.transaction(max_attempts=1))


RESEED_RPC_TIMEOUT_SECONDS = 1.5


def service_frontier(
    client: Any, namespace: str, priority: int, *, transaction: Any = None, timeout: float | None = None
) -> float:
    if priority not in (0, 1, 2):
        raise ValueError('bounded priority required')
    name = f'p{priority}_service'
    bounded = {'timeout': timeout, 'retry': None} if timeout is not None else {}
    docs = list(
        client.collection(f'{namespace}_control')
        .order_by(name, direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream(transaction=transaction, **bounded)
    )
    return docs[0].to_dict()[name] if docs else 0.0
