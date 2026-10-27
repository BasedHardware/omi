"""Transactional document store for batch scheduling; lazy, explicitly namespaced.

Writes are buffered until the body returns so all Firestore reads precede writes.
The transaction callback must be pure; it may be retried by Firestore.
"""

from copy import deepcopy
import os
import re
from typing import Any, Callable, Protocol, TypeVar

from google.cloud import firestore

from config.firestore_read_levers import lever_enabled
from database._client import get_data_plane_firestore_client
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyMemo
from database.batch_pipeline_recovery import quarantine_fenced
from utils.sync.stage import collection_name

# Every state an obligation can drain from. Assignment needs only ``pending``;
# completion of persisted/ready rows has its own page. All share one index.
PROJECTION_DISCOVERY_STATES = ('pending', 'persisted', 'ready')
PROJECTION_OBLIGATION_STATES = (*PROJECTION_DISCOVERY_STATES, 'quarantine_held')
PROJECTION_ASSIGNMENT_STATES = ('pending',)
PROJECTION_FINISH_STATES = ('persisted', 'ready')

T = TypeVar('T')


class Transaction(Protocol):
    def get(self, table: str, key: str) -> dict: ...
    def put(self, table: str, key: str, value: dict) -> None: ...
    def patch(self, table: str, key: str, fields: dict) -> None: ...
    def first_pending(self, owner_key: str) -> dict | None: ...
    def first_ready_pending(self, owner_key: str) -> dict | None: ...
    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None: ...
    def service_frontier(self, priority: int) -> float: ...
    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int: ...


class Store(Protocol):
    def run(self, body: Callable[[Transaction], T]) -> T: ...
    def due(self, state: str, now: float, limit: int) -> list[str]: ...
    def oldest(self, priority: int, *, ready_only: bool) -> float | None: ...
    def oldest_retry(self, priority: int) -> float | None: ...
    def control_candidate(self, priority: int, pool: str, now: float) -> str | None: ...
    def quarantine_fenced(self, segment_id: str, now: float) -> bool: ...
    def longest_ready_pending(self, owner_key: str) -> dict | None: ...
    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]: ...
    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]: ...


class FirestoreTransaction:
    def __init__(self, client: Any, namespace: str, transaction: Any):
        self.client = client
        self.namespace = namespace
        self.transaction = transaction
        self.cache: dict[tuple[str, str], dict] = {}
        self.writes: dict[tuple[str, str], dict] = {}
        self.patches: dict[tuple[str, str], dict] = {}

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
            snapshot = self._ref(table, key).get(transaction=self.transaction)
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

    def first_pending(self, owner_key: str) -> dict | None:
        return first_pending(self.client, self.namespace, owner_key, transaction=self.transaction)

    def first_ready_pending(self, owner_key: str) -> dict | None:
        return first_ready_pending(self.client, self.namespace, owner_key, transaction=self.transaction)

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        return ready_predecessor(
            self.client, self.namespace, owner_key, priority, segment_id, transaction=self.transaction
        )

    def service_frontier(self, priority: int) -> float:
        return service_frontier(self.client, self.namespace, priority, transaction=self.transaction)

    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        options = {}
        if lever_enabled('batch_privacy_memoize', uid):
            # FirestoreStore.run creates this view anew on every callback retry.
            if not hasattr(self, '_privacy_memo'):
                self._privacy_memo = BatchPrivacyMemo(self.client, self.transaction)
            options['memo'] = self._privacy_memo
        return assert_batch_write_allowed(
            self.client,
            self.transaction,
            uid,
            conversation_ids=conversation_ids,
            expected_generation=expected_generation,
            **options,
        )

    def flush(self):
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
                conversation_ids=(job['conversation_id'],) if job.get('conversation_id') else (),
                expected_generation=job.get('privacy_generation'),
            )
            if table == 'jobs' and value.get('privacy_generation') is None:
                value['privacy_generation'] = generation
        for (table, key), value in self.writes.items():
            self.transaction.set(self._ref(table, key), value)
        for (table, key), fields in self.patches.items():
            self.transaction.update(self._ref(table, key), fields)


class FirestoreStore:
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
        @firestore.transactional
        def commit(transaction):
            view = FirestoreTransaction(self.client, self.namespace, transaction)
            result = body(view)
            view.flush()
            return result

        return commit(self.client.transaction())

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        return due(self.client, self.namespace, state, now, limit)

    def oldest(self, priority: int, *, ready_only: bool = False) -> float | None:
        return oldest(self.client, self.namespace, priority, ready_only=ready_only)

    def control_candidate(self, priority: int, pool: str, now: float) -> str | None:
        return control_candidate(self.client, self.namespace, priority, pool, now)

    def oldest_retry(self, priority: int) -> float | None:
        return oldest_retry(self.client, self.namespace, priority)

    def quarantine_fenced(self, segment_id: str, now: float) -> bool:
        return quarantine_fenced(self.client, self.namespace, segment_id, now)

    def longest_ready_pending(self, owner_key: str) -> dict | None:
        # A hint read outside any transaction; the bypass transaction re-verifies it.
        return longest_ready_pending(self.client, self.namespace, owner_key)

    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]:
        # A hint read outside any transaction; the fresh-first transaction re-verifies it.
        return fresh_pending(self.client, self.namespace, owner_key, limit)

    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]:
        return held_merge_owners(self.client, self.namespace, limit, after=after)

    def projection_pending(self, limit: int = 100) -> list[str]:
        return projection_pending(self.client, self.namespace, limit)

    def projection_page(
        self, limit: int = 100, *, after=None, states: tuple[str, ...] = PROJECTION_DISCOVERY_STATES
    ) -> tuple[list[str], Any]:
        return projection_page(self.client, self.namespace, limit, after=after, states=states)

    def projection_successor(self, owner_key: str, previous: str | None) -> str | None:
        return projection_successor(self.client, self.namespace, owner_key, previous)


def projection_pending(client: Any, namespace: str, limit: int = 100) -> list[str]:
    return projection_page(client, namespace, limit)[0]


def projection_page(
    client: Any,
    namespace: str,
    limit: int = 100,
    *,
    after=None,
    states: tuple[str, ...] = PROJECTION_DISCOVERY_STATES,
) -> tuple[list[str], Any]:
    """Stable keyset page; the cursor survives removal of its source row.

    __name__ breaks committed_at ties (including siblings committed together).
    Cursor values are discovery hints, never authorization or ordering fences.
    ``states`` narrows the same ``in`` filter to a subset of the drain states.
    """
    if not states or not set(states) <= set(PROJECTION_OBLIGATION_STATES):
        raise ValueError('projection discovery states must be drain states')
    collection = client.collection(f'{namespace}_results')
    query = collection.where('projection_state', 'in', list(states)).order_by('committed_at').order_by('__name__')
    if after is not None:
        query = query.start_after({'committed_at': after[0], '__name__': collection.document(after[1])})
    size = max(1, min(limit, 100))
    docs = list(query.limit(size).stream())
    # Wrap even when blocked rows remain. Rows inserted behind the cursor are
    # revisited on the next cycle; no durable obligation is skipped or mutated.
    cursor = (docs[-1].to_dict()['committed_at'], docs[-1].id) if len(docs) == size else None
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


def first_pending(client: Any, namespace: str, owner_key: str, *, transaction: Any = None) -> dict | None:
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .order_by('capture_at')
        .order_by('segment_id')
        .limit(1)
        .stream(transaction=transaction)
    )
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
        job = first_pending(client, namespace, mark.id)
        owners.append((mark.id, job.get('owner_id') if job else None))
    return owners


def fresh_pending(client: Any, namespace: str, owner_key: str, limit: int) -> list[dict]:
    """The owner's earliest-captured pending fresh rows, ready or not (fresh-first merge).

    Non-transactional discovery hint: it takes no transactional query lock.
    """
    docs = (
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .where('fresh_capture', '==', True)
        .order_by('capture_at')
        .order_by('segment_id')
        .limit(max(1, min(limit, 32)))
        .stream()
    )
    return [doc.to_dict() for doc in docs]


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


def due(client: Any, namespace: str, state: str, now: float, limit: int = 100) -> list[str]:
    if state not in {'leased', 'retry', 'result_ready', 'record_pending'}:
        raise ValueError('only recoverable states may be scanned')
    field = {
        'leased': 'lease_until',
        'retry': 'available_at',
        'result_ready': 'enqueued_at',
        'record_pending': 'available_at',
    }[state]
    docs = (
        client.collection(f'{namespace}_jobs')
        .where('state', '==', state)
        .where(field, '<=', now)
        .order_by(field)
        .limit(max(1, min(limit, 100)))
        .stream()
    )
    return [doc.id for doc in docs]


# Bounded FIFO prefix the uncommitted-age proxy walks past policy holds. A
# hold population that fills the entire prefix fails the proxy toward tripping
# on the oldest hold's age (an unmeasured commitment may sit beyond the bound);
# retiring the holds themselves stays with the custody track.
OLDEST_POLICY_HOLD_SCAN_LIMIT = 500


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


def oldest(client: Any, namespace: str, priority: int, *, ready_only: bool = False) -> float | None:
    query = client.collection(f'{namespace}_jobs').where('priority', '==', priority)
    if ready_only:
        docs = list(query.where('state', '==', 'ready').order_by('enqueued_at').limit(1).stream())
        return docs[0].to_dict()['enqueued_at'] if docs else None
    # The uncommitted-age proxy must measure the oldest real commitment: walk a
    # bounded prefix of the FIFO and skip allowance policy holds. Early return
    # keeps the healthy case a one-document read; a sentinel row beyond the
    # bound (limit + 1) distinguishes truncation from a FIFO that happens to be
    # exactly as long as the bound.
    docs = iter(
        query.where('merge_pending', '==', True)
        .order_by('enqueued_at')
        .limit(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)
        .stream()
    )
    oldest_hold: float | None = None
    scanned = 0
    for doc in docs:
        scanned += 1
        if scanned > OLDEST_POLICY_HOLD_SCAN_LIMIT:
            break  # the sentinel row exists: the scan was truncated
        job = doc.to_dict()
        if is_allowance_policy_hold(job):
            oldest_hold = oldest_hold if oldest_hold is not None else job['enqueued_at']
            continue
        return job['enqueued_at']
    if scanned > OLDEST_POLICY_HOLD_SCAN_LIMIT and oldest_hold is not None:
        # An unmeasured commitment may exist beyond the bound, so fail toward
        # tripping on the oldest hold's age instead of publishing a false fresh
        # zero.
        return oldest_hold
    return None


def control_candidate(client: Any, namespace: str, priority: int, pool: str, now: float) -> str | None:
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
        .limit(1)
        .stream()
    )
    return docs[0].id if docs else None


def oldest_retry(client: Any, namespace: str, priority: int) -> float | None:
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('priority', '==', priority)
        .where('retry_started_at', '>=', 0)
        .order_by('retry_started_at')
        .limit(1)
        .stream()
    )
    return docs[0].to_dict()['retry_started_at'] if docs else None


def service_frontier(client: Any, namespace: str, priority: int, *, transaction: Any = None) -> float:
    if priority not in (0, 1, 2):
        raise ValueError('bounded priority required')
    name = f'p{priority}_service'
    docs = list(
        client.collection(f'{namespace}_control')
        .order_by(name, direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream(transaction=transaction)
    )
    return docs[0].to_dict()[name] if docs else 0.0
