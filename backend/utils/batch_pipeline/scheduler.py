"""Fenced, duration-fair pull scheduling over durable transactional documents."""

import hashlib
import math
import logging
import random
from threading import Lock
import uuid
from time import monotonic

from database.batch_pipeline_store import Store, Transaction, pull_operation
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_transaction_labels import store_operation
from database.firestore_transaction_retry import FirestoreContentionExhausted
from config.batch_pipeline import (
    FRESH_CAPTURE_LAG_SECONDS,
    SCHEDULER_SHARDS,
    control_candidate_fanout,
    control_steady_write_skip_enabled,
    fifo_array_link_enabled,
    maintenance_contention_continuation_enabled,
    pull_multi_lease_enabled,
    scheduler_control_key,
    shard_spread_enabled,
)
from config.policy import resolve_batch_policy
from config.stt_cap_dispatch import offline_admission_enabled as cap_dispatch_enabled
from database.batch_pipeline_policy import (
    flush_anchor_stage_pins,
    stage_in_transaction,
    record_policy_observations,
)
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import LeasedWork, Priority, WorkItem, WorkResult, PoolCapacity, attach_held_vad
from utils.batch_pipeline.capacity import within_unit_ceiling
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.control import activation_surface, activate, field, migrate_legacy, read_control
from utils.batch_pipeline.errors import (
    error_site_field,
    language_guard_redrive_failure,
    validate_worker_failure,
    validate_worker_failure_evidence,
)
from utils.batch_pipeline.retry_policy import quarantine_job, expire_lease, observe_recovery

QUANTUM_SECONDS = 30.0
LEASE_SECONDS = 120.0
RETRY_BACKOFF_CAP_SECONDS = 600
MAX_ACTIVE_OWNERS = 1024
MAX_VISITS = 128
# The queue-document FIFO array holds the owner's ordered segment ids. Segment
# ids are 64-char sha256 hex digests, so the bound keeps the queue document far
# below Firestore's 1 MiB limit; admission retries past it exactly like the
# active-owner capacity bound does.
FIFO_ARRAY_MAX_ITEMS = 2048
# Conversion and stray absorption walk a legacy chain only this deep; beyond
# the cap the queue stays legacy (conversion) or refuses (absorption) instead
# of guessing across an unverified gap.
FIFO_LINK_MIGRATION_WALK_CAP = 512
# A vetoed conversion re-probes at most once a minute, so a deep backlog never
# pays the migration walk on every append.
FIFO_LINK_PROBE_BACKOFF_SECONDS = 60.0
# The walk visits another queue only below this many buffered writes (flush
# refuses 450); a stop commits the rotations so far and the next pull resumes.
PULL_WRITE_HEADROOM = 300
HEAD_OWNER_BUDGET = 64
CONTENTION_BACKOFF_CAP_SECONDS = 30.0
PULL_CLAIM_SECONDS = 30.0
logger = logging.getLogger(__name__)


def _admission_retry_delay(value: object, streak: int) -> float:
    minimum = min(300, 30 * 2 ** (streak - 1))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return minimum
    if isinstance(value, float) and not math.isfinite(value):
        return minimum
    return max(minimum, min(86400, value))


def owner_key(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode()).hexdigest()


def rejoin_frontiers(store: Store, priorities) -> dict[int, float]:
    """Advisory rejoin fairness seeds keyed by priority, read outside any transaction.

    The seed only biases least-service-first scheduling for a shard rejoining a
    priority (``control.activate``); a failed or stale read degrades to ``0.0``
    instead of failing admission — the seed is never authorization, custody or
    ordering. Every entry point reads its map once before ``store.run`` so the
    transactional body stays free of the hottest control read (the argmax
    shard's document, rewritten by every lease of the winning shard).
    """
    seeds: dict[int, float] = {}
    for priority in sorted({int(p) for p in priorities}):
        try:
            seeds[priority] = float(store.service_frontier_hint(priority))
        except Exception as error:
            logger.warning(
                'event=batch_frontier_hint outcome=degraded priority=%d exception_type=%s',
                priority,
                type(error).__name__,
            )
            seeds[priority] = 0.0
    return seeds


def _fifo_read_chain(tx: Transaction, queue: dict) -> list[str] | None:
    """Read a legacy ``head -> next`` chain for conversion; ``None`` vetoes conversion.

    The chain must be fully walkable (no purged rows, no cycles, within the
    migration cap) and end exactly at the mirrored tail, or the queue stays
    legacy: a guessed prefix would reorder the owner's FIFO.
    """
    head = queue.get('head', '')
    if not head:
        return [] if not queue.get('tail') else None
    chain: list[str] = []
    seen: set[str] = set()
    cursor: str | None = head
    while cursor:
        if cursor in seen or len(chain) >= FIFO_LINK_MIGRATION_WALK_CAP:
            return None
        job = tx.get('jobs', cursor)
        if not job:
            return None
        chain.append(cursor)
        seen.add(cursor)
        cursor = job.get('next') or ''
    tail = queue.get('tail', '')
    if tail and chain and chain[-1] != tail:
        return None
    return chain


def _fifo_absorb_strays(tx: Transaction, queue: dict) -> bool:
    """Fold legacy chain stragglers into the array; True when the queue changed.

    Stragglers exist only while an older binary is still rolling: it seeds a
    chain beside an empty array, or chains on from the array's tail and moves
    the tail mirror to the straggler. Both foldings are bounded, verified row
    by row, and end exactly at the mirrored tail before anything is folded.
    A chain deeper than the migration cap refuses the whole append: a partial
    fold would strand the remainder behind a moved tail mirror.
    """
    items = queue.setdefault('items', [])
    head = queue.get('head', '')
    if not items and head:
        chain = _fifo_read_chain(tx, queue)
        if chain is None or (queue.get('tail') and chain and chain[-1] != queue['tail']):
            return False
        queue['items'] = chain
        queue['head'] = chain[0] if chain else ''
        return True
    tail = queue.get('tail', '')
    if not items or not tail or tail in items:
        return False
    absorbed: list[str] = []
    cursor = (tx.get('jobs', items[-1]) or {}).get('next') or ''
    while cursor and len(absorbed) < FIFO_LINK_MIGRATION_WALK_CAP:
        if cursor in items or cursor in absorbed:
            cursor = ''
            break
        job = tx.get('jobs', cursor)
        if not job:
            cursor = ''
            break
        absorbed.append(cursor)
        cursor = job.get('next') or ''
    if cursor or (absorbed and absorbed[-1] != tail):
        # Deeper than the cap, or the chain does not end at the mirrored tail:
        # half-folded queues strand the remainder behind a moved tail mirror,
        # so the whole append refuses and retries after the roll completes.
        raise RuntimeError('fifo link migration chain overflow; admission must retry')
    if absorbed:
        queue['items'] = items + absorbed
        queue['tail'] = absorbed[-1]
        return True
    return False


def _append_fifo_array(
    tx: Transaction, queue: dict, queue_key: str, control: dict, job: dict, now: float, frontier: float
) -> bool:
    """Append through the queue-document FIFO; False falls back to the legacy chain.

    Conversion happens here, at the only writer that must see it: a whole
    legacy chain converts while it fits the bounded migration walk, and a
    vetoed conversion stamps ``link_probe_at`` so a deep backlog does not pay
    the walk on every append. The job document never joins the write set.
    ``frontier`` is the advisory rejoin seed read outside the transaction.
    """
    # The control write below is decided, not unconditional: a warm append
    # (queue already in the ring, priority already active, availability
    # floors at or below this job's available_at) changes none of the
    # fields this path can touch, so the snapshot pair skips a
    # byte-identical write that only joined the abort set.
    before = activation_surface(control, job['priority'], queue_key)
    if queue.get('link_mode') != 'fifo_array':
        probe_at = queue.get('link_probe_at')
        if probe_at is not None and now - probe_at < FIFO_LINK_PROBE_BACKOFF_SECONDS:
            return False
        chain = _fifo_read_chain(tx, queue)
        if chain is None:
            queue['link_probe_at'] = now
            tx.put('queues', queue_key, queue)
            return False
        queue['items'] = chain
        queue['link_mode'] = 'fifo_array'
    else:
        _fifo_absorb_strays(tx, queue)
    items = queue.setdefault('items', [])
    if len(items) >= FIFO_ARRAY_MAX_ITEMS:
        raise RuntimeError('fifo array capacity exceeded; admission must retry')
    items.append(job['segment_id'])
    queue['items'] = items
    job['next'] = ''
    ring = control['rings'][str(job['priority'])]
    if not queue.get('head'):
        if len(ring) >= MAX_ACTIVE_OWNERS:
            raise RuntimeError('active owner capacity exceeded; admission must retry')
        if queue_key not in ring:
            ring.append(queue_key)
        queue['head'] = job['segment_id']
        queue['deficit'] = 0.0
        queue['continuing'] = False
    queue['tail'] = job['segment_id']
    activate(tx, control, job['priority'], job['available_at'], frontier)
    if not control_steady_write_skip_enabled() or activation_surface(control, job['priority'], queue_key) != before:
        tx.put('control', scheduler_control_key(job['owner_key']), control)
    tx.put('queues', queue_key, queue)
    return True


def _append(tx: Transaction, control: dict, job: dict, now: float, frontier: float) -> None:
    """Append one admitted job to its owner's FIFO; ``frontier`` is the advisory
    rejoin seed for the shard's priority, read outside the transaction by the
    entry point (``rejoin_frontiers``) so the activation never joins the
    argmax shard's abort set."""
    queue_key = f"{job['priority']}_{job['owner_key']}"
    queue = tx.get('queues', queue_key) or {'head': '', 'tail': '', 'deficit': 0.0, 'continuing': False}
    if fifo_array_link_enabled() and _append_fifo_array(tx, queue, queue_key, control, job, now, frontier):
        return
    # Same decided write as the fifo-array path: snapshot before the ring
    # membership or activation mutations so a warm append can skip the
    # byte-identical control write.
    before = activation_surface(control, job['priority'], queue_key)
    ring = control['rings'][str(job['priority'])]
    if not queue['head']:
        if len(ring) >= MAX_ACTIVE_OWNERS:
            raise RuntimeError('active owner capacity exceeded; admission must retry')
        if queue_key not in ring:
            ring.append(queue_key)
        queue['head'] = job['segment_id']
        queue['deficit'] = 0.0
        queue['continuing'] = False
    else:
        tail = tx.get('jobs', queue['tail'])
        tail['next'] = job['segment_id']
        tx.put('jobs', tail['segment_id'], tail)
    queue['tail'] = job['segment_id']
    job['next'] = ''
    tx.put('queues', queue_key, queue)
    activate(tx, control, job['priority'], job['available_at'], frontier)
    if not control_steady_write_skip_enabled() or activation_surface(control, job['priority'], queue_key) != before:
        tx.put('control', scheduler_control_key(job['owner_key']), control)


def _pool_allows(job: dict, max_seconds: float, shared_gpu: bool) -> bool:
    return within_unit_ceiling(job['duration_seconds'], max_seconds) and not (
        shared_gpu and job.get('unit_kind', 'conversation') != 'capture_span'
    )


def _park_reason(job: dict, max_seconds: float, shared_gpu: bool) -> str:
    """Bounded label for a head this pull cannot lease; privacy is labeled by the caller."""
    if not within_unit_ceiling(job['duration_seconds'], max_seconds):
        return 'pool_duration'
    if shared_gpu and job.get('unit_kind', 'conversation') != 'capture_span':
        return 'pool_unit_kind'
    return 'shared_live_policy'


class _OwnWrites:
    """A pull transaction whose index queries see the jobs it already wrote.

    Firestore and Postgres transactions buffer writes until commit, and their
    index queries read the snapshot. Once one transaction leases or splices
    several units, a later query must not return those units as still ready.
    """

    def __init__(self, tx: Transaction):
        self._tx, self._jobs, self._written = tx, set(), set()

    def __getattr__(self, name):
        return getattr(self._tx, name)  # Store-specific helpers pass through unchanged.

    def get(self, table: str, key: str) -> dict:
        return self._tx.get(table, key)

    def put(self, table: str, key: str, value: dict) -> None:
        if table == 'jobs':
            self._jobs.add(key)
        self._written.add((table, key))
        self._tx.put(table, key, value)

    def buffered_writes(self) -> int:
        return len(self._written)

    def patch(self, table: str, key: str, fields: dict) -> None:
        self._tx.patch(table, key, fields)

    def _own(self, job: dict | None) -> dict | None:
        return self._tx.get('jobs', job['segment_id']) if job and job['segment_id'] in self._jobs else job

    def first_pending(self, owner_key: str) -> dict | None:
        return self._own(self._tx.first_pending(owner_key))

    def first_ready_pending(self, owner_key: str) -> dict | None:
        return self._own(self._tx.first_ready_pending(owner_key))

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        return self._own(self._tx.ready_predecessor(owner_key, priority, segment_id))

    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        return self._tx.check_privacy(uid, conversation_ids, expected_generation)


def _prefer_merge_head(
    tx: Transaction,
    queue: dict,
    job: dict,
    budget: list[int],
    observations: list,
    *,
    now: float,
    max_seconds: float,
    shared_gpu: bool,
    candidates=None,
    pins: list | None = None,
) -> dict:
    """Promote an indexed capture head with O(1) queries, independent of FIFO depth.

    The budget bounds owners visited, not positions within an owner's backlog.
    An ordinary FIFO remains valid with head priority disabled. Compute can run
    concurrently for an owner; OrderedMerge alone enforces pending predecessors.
    """
    if budget[0] <= 0:
        observations.append(('budget_exhausted', None))
        return job
    budget[0] -= 1
    head = tx.first_pending(job['owner_key'])
    if not head:
        observations.append(('head_not_found', None))
        return job
    if head['state'] == 'ready':
        observations.append(('ready_age', max(0.0, now - head['available_at'])))
    if (
        head['segment_id'] == job['segment_id']
        or head['state'] != 'ready'
        or head['priority'] != job['priority']
        or not _pool_allows(head, max_seconds, shared_gpu)
    ):
        return job
    previous = tx.ready_predecessor(job['owner_key'], job['priority'], head['segment_id'])
    if (
        not previous
        or previous.get('state') != 'ready'
        or (queue.get('link_mode') != 'fifo_array' and previous.get('next') != head['segment_id'])
    ):
        # The array-backed FIFO carries its own ordering authority; the legacy
        # chain additionally verifies the predecessor's next pointer, which an
        # array queue never writes.
        observations.append(('head_not_found', None))
        return job
    try:
        for linked in (previous, head):
            tx.check_privacy(
                linked['owner_id'],
                (linked['conversation_id'],) if linked.get('conversation_id') else (),
                linked.get('privacy_generation'),
            )
    except BatchPrivacyBlocked:
        return job
    if not stage_in_transaction(
        tx, head, 'scheduler', observations=observations, candidates=candidates, pins=pins
    ).head_priority:
        return job
    if queue.get('link_mode') == 'fifo_array':
        # Promote in the array alone: no predecessor or successor job document
        # joins the pull's write set, so the splice cannot contend with the
        # promoted unit's own lifecycle writers.
        items = [segment for segment in (queue.get('items') or []) if segment != head['segment_id']]
        items.insert(0, head['segment_id'])
        queue['items'] = items
        queue['head'] = head['segment_id']
        queue['tail'] = items[-1] if items else ''
        return head
    previous['next'] = head['next']
    tx.put('jobs', previous['segment_id'], previous)
    if queue['tail'] == head['segment_id']:
        queue['tail'] = previous['segment_id']
    head['next'] = queue['head']
    queue['head'] = head['segment_id']
    tx.put('jobs', head['segment_id'], head)
    return head


def owns_lease(job: dict, token: str, now: float) -> bool:
    return job.get('state') == 'leased' and job.get('token') == token and job['lease_until'] > now


def _defer(job: dict, now: float, reason: str) -> None:
    job.update(
        state='retry',
        available_at=now + min(RETRY_BACKOFF_CAP_SECONDS, 5 * 2 ** min(7, max(0, job['attempt'] - 1))),
        retry_started_at=job.get('retry_started_at', now),
        token='',
        lease_until=0.0,
        # Only bounded machine reason codes belong here, never provider errors/text.
        failure=reason,
    )


class Scheduler:
    def __init__(self, store: Store, *, metrics: QueueMetrics | None = None, pool: str = 'batch', worker_id: str = ''):
        if pool not in {'batch', 'live'}:
            raise ValueError('pool must be batch or live')
        self.store = store
        self.metrics = metrics
        self.pool = pool
        self.worker_id = worker_id or uuid.uuid4().hex
        self._contention_failures = 0
        self._contention_backoff_until = 0.0
        self._contention_generation = 0
        self._contention_lock = Lock()

    def enqueue(self, item: WorkItem, now: float) -> bool:
        # Advisory rejoin seed: read outside the transaction so a rejoining
        # admission never joins the argmax shard's abort set.
        frontier = rejoin_frontiers(self.store, (item.priority,)).get(int(item.priority), 0.0)
        with store_operation('batch_enqueue'):
            return self.store.run(lambda tx: self.enqueue_in_transaction(tx, item, now, frontier=frontier))

    @staticmethod
    def enqueue_in_transaction(
        tx: Transaction, item: WorkItem, now: float, *, policy=None, frontier: float = 0.0
    ) -> bool:
        """Admit one work item into the GPU ring.

        ``frontier`` is the advisory rejoin fairness seed for the item's
        priority, read outside any transaction (``Scheduler.rejoin_frontiers`` /
        ``Store.service_frontier_hint``); the default ``0.0`` is the
        empty-collection seed and never authorizes anything.
        """
        if item.shadow:
            raise ValueError('shadow jobs may only use idle offers')
        previous = tx.get('jobs', item.segment_id)
        # Live jobs are never shadow; keep their documents free of the field.
        immutable = {key: value for key, value in item.to_dict().items() if key != 'shadow'}
        immutable['priority'] = int(item.priority)
        if previous.get('state') == 'record_pending' and (
            previous.get('owner_id') != item.owner_id
            or previous.get('conversation_id') != item.conversation_id
            or previous.get('privacy_generation') != item.privacy_generation
        ):
            raise ValueError('pending recording owner cannot change')
        if previous and previous.get('state') != 'record_pending':
            if any(
                previous.get(key, {'unit_kind': 'conversation', 'requires_compute_admission': False}.get(key)) != value
                for key, value in immutable.items()
                if not (key == 'privacy_generation' and value is None)
            ):
                raise ValueError('segment ID reused with different immutable work')
            return False
        policy = policy or resolve_batch_policy(item.owner_id)
        key = owner_key(item.owner_id)
        owner = tx.get('owners', key)
        watermark = owner.get('watermark')
        control = read_control(tx, scheduler_control_key(key))
        job = {
            # Unstamped work keeps the legacy document shape; readers default to None.
            **{key: value for key, value in immutable.items() if key != 'timing_store' or value is not None},
            'policy': policy.to_dict(),
            'policy_source': 'admission',
            'protocol_version': 1,
            'owner_key': key,
            'enqueued_at': now,
            'state': 'ready',
            # Capacity may follow a newly admitted first attempt. This is not
            # paid permission: per-lease admission replaces it with allowed or
            # held, or removes it on an unevaluated refusal (also on old workers).
            'compute_decision': {'outcome': 'unattempted'},
            'attempt': 0,
            'token': '',
            'lease_until': 0.0,
            'available_at': now,
            'merge_pending': True,
            'late_capture': bool(
                watermark and (item.capture_at, item.segment_id) <= (watermark['capture_at'], watermark['segment_id'])
            ),
            # Merge class only: fresh rows commit ahead of the owner's catch-up backlog.
            'fresh_capture': now - item.capture_at - item.duration_seconds <= FRESH_CAPTURE_LAG_SECONDS,
        }
        _append(tx, control, job, now, frontier)
        tx.put('jobs', item.segment_id, job)
        # Admission and merge serialize through this fence even for different classes.
        owner['revision'] = owner.get('revision', 0) + 1
        tx.put('owners', key, owner)
        return True

    def pull(self, now: float, limit: int = 1, *, capacity: PoolCapacity | None = None) -> list[LeasedWork]:
        if not 1 <= limit <= 32:
            raise ValueError('pull limit must be in [1, 32]')
        with self._contention_lock:
            if self._contention_backoff_until > monotonic():
                return []
            contention_generation = self._contention_generation
        if self.pool == 'live' and (capacity is None or not capacity.shared_with_live):
            return []
        if self.pool == 'batch' and capacity is not None and capacity.shared_with_live:
            return []
        # No snapshot is the dedicated-batch worker contract only. Shared live
        # callers must supply a fresh exclusive-admission snapshot every pull.
        allow_backfill, max_seconds, backfill_budget = True, 7200.0, limit
        if capacity is not None:
            slots, allow_backfill, max_seconds = capacity.limits(now, shared_live_enabled=True)
            limit = min(limit, slots)
            backfill_budget = max(0, slots - capacity.reserved_fresh_slots)
        result = []
        contention_deferred = False
        shared_gpu_id = capacity.gpu_id if capacity is not None and capacity.shared_with_live else None
        # One shard transaction may lease several units from the ring it has
        # already read; the kill switch restores one lease per transaction.
        multi = pull_multi_lease_enabled() and shared_gpu_id is None
        while len(result) < limit:
            remaining = limit - len(result) if multi else 1
            try:
                leases = self._pull_one(
                    now,
                    allow_backfill=allow_backfill and backfill_budget > 0,
                    max_seconds=max_seconds,
                    shared_gpu_id=shared_gpu_id,
                    max_fresh=remaining,
                    max_backfill=min(remaining, backfill_budget),
                )
            except Exception as error:
                if isinstance(error, FirestoreContentionExhausted):
                    with self._contention_lock:
                        self._contention_failures += 1
                        maximum = min(
                            CONTENTION_BACKOFF_CAP_SECONDS,
                            2.0 ** min(self._contention_failures - 1, 5),
                        )
                        delay = maximum * (0.5 + 0.5 * random.random())
                        failed_at = monotonic()
                        self._contention_backoff_until = max(
                            self._contention_backoff_until,
                            failed_at + delay,
                        )
                        retry_after_ms = round((self._contention_backoff_until - failed_at) * 1000)
                        self._contention_generation += 1
                        contention_failures = self._contention_failures
                    contention_deferred = True
                    logger.error(
                        'event=batch_pull outcome=backoff failures=%d retry_after_ms=%d%s',
                        contention_failures,
                        retry_after_ms,
                        error_site_field(error),
                    )
                    break
                if not result:
                    raise
                # Each earlier lease is its own committed transaction. Raising
                # would strand them leased until LEASE_SECONDS expiry and
                # charge a retry; hand them to the caller instead.
                logger.error(
                    'event=batch_pull outcome=partial leased=%d exception_type=%s%s',
                    len(result),
                    type(error).__name__,
                    error_site_field(error),
                )
                break
            if not leases:
                break
            result.extend(leases)
            backfill_budget -= sum(lease.item.priority != Priority.FRESH for lease in leases)
            if capacity is not None and capacity.shared_with_live:
                break  # One non-preemptible short item, never a mixed long batch.
        if not contention_deferred:
            with self._contention_lock:
                if self._contention_generation == contention_generation:
                    self._contention_failures = 0
                    self._contention_backoff_until = 0.0
        return result

    def _pull_one(
        self,
        now: float,
        *,
        allow_backfill: bool,
        max_seconds: float,
        shared_gpu_id: str | None = None,
        max_fresh: int = 1,
        max_backfill: int = 1,
    ) -> list[LeasedWork]:
        for priority in Priority:
            if priority != Priority.FRESH and not allow_backfill:
                break
            max_leases = max_fresh if priority == Priority.FRESH else max_backfill
            if max_leases < 1:
                break
            spread = shard_spread_enabled()
            excluded = set()
            busy = False
            candidates = None
            refreshed = False
            candidate_fanout = control_candidate_fanout()
            for _ in range(128):
                if spread:
                    if candidates is None:
                        candidates = self.store.control_candidates(
                            int(priority), self.pool, now, worker_id=self.worker_id, fanout=candidate_fanout
                        )
                    shard = next((key for key in candidates if key not in excluded), None)
                else:
                    shard = self.store.control_candidate(int(priority), self.pool, now)
                if shard is None:
                    if (
                        spread
                        and busy
                        and not refreshed
                        and candidate_fanout < SCHEDULER_SHARDS
                        and candidates is not None
                        and len(candidates) >= candidate_fanout
                    ):
                        # A full busy prefix proves nothing about the remaining
                        # shards. Spend the sole refresh on the legacy width,
                        # skipping every already-tried claim locally.
                        candidates = None
                        candidate_fanout = SCHEDULER_SHARDS
                        refreshed = True
                        continue
                    break
                receipts, eligible = self._pull_shard(now, shard, priority, max_seconds, shared_gpu_id, max_leases)
                if receipts:
                    for _, enqueued_at, relet in receipts:
                        if self.metrics:
                            try:
                                self.metrics.record('leased', wait_seconds=now - enqueued_at, relet=relet)
                            except Exception:
                                pass  # Metrics cannot turn an issued lease into a failed pull.
                    return [lease for lease, _, _ in receipts]
                if eligible == 'reserved':
                    return []
                if eligible == 'busy':
                    excluded.add(shard)
                    busy = True
                    continue
                if spread:
                    if not eligible:
                        excluded.add(shard)
                    # Share one wide refresh budget with busy-window refill.
                    # Later deficit rounds retry the eligible head locally.
                    if not refreshed:
                        candidates = None
                        candidate_fanout = SCHEDULER_SHARDS
                        refreshed = True
                if eligible:
                    # Bounded deficit accrual must not bypass eligible fresh work.
                    continue
            else:
                return []
            if busy:
                # Busy higher-priority work is still pending. Do not borrow
                # backfill capacity while another puller owns its shard.
                return []
        return []

    def _pull_shard(self, now, shard, priority, max_seconds, shared_gpu_id, max_leases=1):
        candidates = {}
        pins: list = []
        started = monotonic()
        spread = shard_spread_enabled()
        claim_token = uuid.uuid4().hex

        def current_time():
            return now + max(0.0, monotonic() - started)

        if spread:
            # Hint reads take no transaction locks and never authorize writes.
            # A loser does not join the expensive control/queue/job read set.
            if not self.store.acquire_pull_claim(shard, claim_token, current_time(), PULL_CLAIM_SECONDS):
                return None, 'busy'

        def commit(tx):
            tx = _OwnWrites(tx)
            observations, receipts = [], []
            if spread:
                claim = tx.get('pull_claims', shard)
                if claim.get('token') != claim_token or claim.get('expires_at', 0) <= current_time():
                    return None, 'busy', observations
                # Buffered release commits atomically with the pull. Reading
                # this fence also invalidates a paused holder after takeover.
                tx.put('pull_claims', shard, {'token': '', 'expires_at': 0.0})
            gpu_key = owner_key(shared_gpu_id) if shared_gpu_id is not None else ''
            gpu = tx.get('gpus', gpu_key) if gpu_key else {}
            if gpu.get('token'):
                return None, 'reserved', observations
            control = read_control(tx, shard)
            ring = control['rings'][str(int(priority))]
            eligible_queues, blocked = {}, set()
            owner_count = max(1, len(ring))
            head_budget = [HEAD_OWNER_BUDGET]
            visits, write_stop = 0, False
            # MAX_VISITS still bounds the whole walk, and with it the queue
            # writes; later leases spend what the first left, from cached reads.
            while visits < MAX_VISITS and len(receipts) < max_leases:
                if tx.buffered_writes() >= PULL_WRITE_HEADROOM:
                    write_stop = True
                    break
                visits += 1
                if not ring:
                    break
                queue_key = ring[0]
                queue = tx.get('queues', queue_key)
                if queue.get('link_mode') == 'fifo_array' and _fifo_absorb_strays(tx, queue):
                    # Folded mid-roll stragglers into the array; the lease or
                    # rotation below commits the queue document either way.
                    tx.put('queues', queue_key, queue)
                job = tx.get('jobs', queue['head']) if queue.get('head') else {}
                if not job:
                    ring.pop(0)  # A completed purge may have removed this queue.
                    continue
                job.setdefault('unit_kind', 'conversation')
                if queue_key not in eligible_queues and queue_key not in blocked:
                    try:
                        tx.check_privacy(
                            job['owner_id'],
                            (job['conversation_id'],) if job.get('conversation_id') else (),
                            job.get('privacy_generation'),
                        )
                    except BatchPrivacyBlocked:
                        blocked.add(queue_key)
                        observations.append(('parked_privacy', None))
                    else:
                        privacy_checked_segment = job['segment_id']
                        policy = stage_in_transaction(
                            tx, job, 'scheduler', observations=observations, candidates=candidates, pins=pins
                        )
                        if policy.head_priority:
                            job = _prefer_merge_head(
                                tx,
                                queue,
                                job,
                                head_budget,
                                observations,
                                now=now,
                                max_seconds=max_seconds,
                                shared_gpu=bool(gpu_key),
                                candidates=candidates,
                                pins=pins,
                            )
                        job.setdefault('unit_kind', 'conversation')
                        park = None
                        try:
                            if job['segment_id'] != privacy_checked_segment:
                                tx.check_privacy(
                                    job['owner_id'],
                                    (job['conversation_id'],) if job.get('conversation_id') else (),
                                    job.get('privacy_generation'),
                                )
                            policy = stage_in_transaction(tx, job, 'scheduler', candidates=candidates, pins=pins)
                            allowed = _pool_allows(job, max_seconds, bool(gpu_key)) and (
                                not gpu_key or policy.shared_live
                            )
                        except BatchPrivacyBlocked:
                            allowed, park = False, 'privacy'
                        if allowed:
                            eligible_queues[queue_key] = job['duration_seconds']
                        else:
                            blocked.add(queue_key)
                            # Parking is otherwise silent: the owner's whole FIFO waits behind this head.
                            park = park or _park_reason(job, max_seconds, bool(gpu_key))
                            observations.append((f'parked_{park}', None))
                if queue_key in blocked:
                    ring.append(ring.pop(0))
                    if len(blocked) == len(ring):
                        break
                    continue
                if not queue['continuing']:
                    queue['deficit'] += QUANTUM_SECONDS
                cost = job['duration_seconds']
                if cost > queue['deficit']:
                    queue['continuing'] = False
                    ring.append(ring.pop(0))
                    tx.put('queues', queue_key, queue)
                    # Skip empty DRR rounds in metadata, not repeated privacy IO.
                    if len(eligible_queues) + len(blocked) == len(ring):
                        rounds = min(
                            max(0, math.ceil((duration - tx.get('queues', key)['deficit']) / QUANTUM_SECONDS))
                            for key, duration in eligible_queues.items()
                        )
                        if rounds > 1:
                            for key in eligible_queues:
                                other = tx.get('queues', key)
                                other['deficit'] += (rounds - 1) * QUANTUM_SECONDS
                                tx.put('queues', key, other)
                    continue
                queue['deficit'] -= cost
                if queue.get('link_mode') == 'fifo_array':
                    items = queue.get('items') or []
                    if items and items[0] == job['segment_id']:
                        items.pop(0)
                    queue['items'] = items
                    queue['head'] = items[0] if items else ''
                else:
                    queue['head'] = job['next']
                queue['continuing'] = True
                if not queue['head']:
                    queue.update(tail='', deficit=0.0, continuing=False)
                    ring.pop(0)
                token = uuid.uuid4().hex
                job.update(
                    state='leased',
                    token=token,
                    attempt=job['attempt'] + 1,
                    lease_until=now + LEASE_SECONDS,
                    shared_gpu_key=gpu_key,
                )
                if not job.get('requires_compute_admission') and not cap_dispatch_enabled(job['owner_id'], 'batch'):
                    # The pump dispatches this lease without admission, so it
                    # is a real commitment: a parked hold must not hide it.
                    job.pop('last_policy_hold', None)
                if gpu_key:
                    tx.put(
                        'gpus',
                        gpu_key,
                        {'token': token, 'segment_id': job['segment_id'], 'lease_until': job['lease_until']},
                    )
                tx.put('queues', queue_key, queue)
                tx.put('jobs', job['segment_id'], job)
                control[field(int(priority), 'service')] += cost / owner_count
                item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
                # defer() refunds the attempt, so an admission-deferred re-lease
                # is a relet only through its admission_refusals streak; a
                # charged attempt (> 1 after this lease's increment) marks every
                # other re-lease.
                relet = job.get('admission_refusals', 0) > 0 or job['attempt'] > 1
                receipts.append(
                    (LeasedWork(item, token, job['attempt'], job['lease_until']), job['enqueued_at'], relet)
                )
                # The owner's next head is a different unit: it gets its own
                # privacy, policy and pool checks before it can be leased.
                eligible_queues.pop(queue_key, None)
                owner_count = max(1, len(ring))
            # Ring rotations after the last lease commit with their deficits.
            control[field(int(priority), 'active')] = bool(ring)
            if not receipts and not eligible_queues and not write_stop:
                control[field(int(priority), self.pool + '_available_at')] = now + 30
            tx.put('control', shard, control)
            # A write stop proved nothing about the unvisited queues: no backoff.
            return receipts or None, bool(receipts or eligible_queues or write_stop), observations

        with pull_operation('pull', shard):
            receipts, eligible, observations = self.store.run(commit)
        flush_anchor_stage_pins(self.store, pins)
        try:
            record_policy_observations(observations)
        except Exception:
            pass  # Telemetry after commit cannot drop the lease it just issued.
        # Only committed attempts emit telemetry; Firestore may retry callbacks.
        if self.metrics:
            for event, age in observations:
                if event in {'policy_fallback', 'policy_stage'}:
                    continue
                try:
                    self.metrics.record_head(event, priority, age=age)
                except Exception:
                    pass  # Metrics cannot turn an issued lease into a failed pull.
        return receipts, eligible

    def heartbeat(self, segment_id: str, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return False
            gpu_key = job.get('shared_gpu_key')
            gpu = tx.get('gpus', gpu_key) if gpu_key else {}
            if gpu_key and gpu.get('token') != token:
                return False
            job['lease_until'] = max(job['lease_until'], now + LEASE_SECONDS)
            if gpu_key:
                gpu['lease_until'] = job['lease_until']
                tx.put('gpus', gpu_key, gpu)
            tx.put('jobs', segment_id, job)
            return True

        with store_operation('batch_heartbeat'):
            return self.store.run(commit)

    def complete(self, result: WorkResult, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', result.segment_id)
            if job.get('state') in {'result_ready', 'committed'}:
                return result.matches_persisted(job.get('result')) and job.get('token') == token, False, 0
            if not owns_lease(job, token, now):
                return False, False, 0
            if job.get('requires_compute_admission') and job.get('compute_admission_token') != token:
                return False, False, 0
            job.update(state='result_ready', result=result.to_dict(), ready_at=now)
            job.pop('retry_started_at', None)
            job.pop('admission_refusals', None)
            job.pop('worker_failure_evidence', None)
            tx.put('jobs', result.segment_id, job)
            return True, True, job['duration_seconds']

        with store_operation('batch_complete'):
            accepted, changed, seconds = self.store.run(commit)
        if changed and self.metrics:
            self.metrics.record('completed')
            try:
                self.metrics.record_completed_audio(result.outcome, seconds)
            except Exception:
                pass  # Duration telemetry cannot undo a fenced completion.
        return accepted

    def fail(
        self,
        segment_id: str,
        token: str,
        now: float,
        *,
        quarantine: bool = False,
        padded_retry_empty: bool = False,
        padded_retry: str | None = None,
        worker_failure: dict | None = None,
        worker_failure_evidence: dict | None = None,
        measured_held_vad_speech_seconds: float | None = None,
        worker_vad_receipt: dict | None = None,
    ) -> bool:
        if worker_failure is not None:
            validate_worker_failure(worker_failure)
        if worker_failure_evidence is not None:
            # Evidence-only diagnostics from an ordinary retryable failure.
            # Unlike ``worker_failure`` this never decides the transition: the
            # ladder still runs, but the terminal record keeps the diagnosis.
            validate_worker_failure_evidence(worker_failure_evidence)
        if padded_retry is None and padded_retry_empty:
            padded_retry = 'empty'
        elif padded_retry == 'empty' and not padded_retry_empty:
            padded_retry_empty = True
        if padded_retry not in {None, 'empty', 'skipped_oversize', 'skipped_long_speech'} or (
            padded_retry_empty and padded_retry != 'empty'
        ):
            raise ValueError('invalid padded retry evidence')

        candidates = {}
        observations = []
        pins: list = []
        # The job's accumulated diagnosis, read inside the transaction. The
        # terminal record below must name the stage/reason this ladder
        # actually collected — not the anonymous unknown/unclassified shape —
        # even when the exhausting attempt arrives evidence-less (a missing
        # worker result or an untyped stage), because the commit above already
        # preserved earlier attempts' evidence on the job.
        preserved_diagnosis: dict | None = None

        def commit(tx):
            nonlocal preserved_diagnosis
            observations.clear()
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return None
            policy = stage_in_transaction(
                tx, job, 'scheduler', candidates=candidates, observations=observations, pins=pins
            )
            attach_held_vad(job, measured_held_vad_speech_seconds, worker_vad_receipt)
            if worker_failure_evidence is not None:
                # Latest worker diagnosis rides on the job through every
                # ladder attempt; a later attempt without evidence preserves
                # the previous diagnosis rather than erasing it.
                job['worker_failure_evidence'] = dict(worker_failure_evidence)
            if quarantine or worker_failure is not None or job['attempt'] >= policy.max_attempts:
                preserved_diagnosis = job.get('worker_failure_evidence')
                quarantine_job(tx, job, now, 'worker_failed')
                if quarantine and padded_retry in {'empty', 'skipped_oversize', 'skipped_long_speech'}:
                    job['worker_empty_evidence'] = {'padded_retry': padded_retry, 'version': 1}
                if worker_failure is not None:
                    job['worker_failure'] = dict(worker_failure)
            else:
                _defer(job, now, 'worker_failed')
            tx.put('jobs', segment_id, job)
            return job['state'], job['attempt'], job['duration_seconds']

        with store_operation('batch_fail'):
            outcome = self.store.run(commit)
        flush_anchor_stage_pins(self.store, pins)
        record_policy_observations(observations)
        if outcome:
            state, attempt, seconds = outcome
            if state == 'quarantined':
                record_correctness('failed', seconds=seconds)
            else:
                try:
                    logger.info('event=batch_retry reason=worker_failed outcome=deferred attempt=%d', attempt)
                except Exception:
                    pass
            # Best effort AFTER the transaction/exception scope: telemetry may
            # neither fail a sibling nor reveal a worker exception via handleError.
            if self.metrics:
                try:
                    self.metrics.record('quarantined' if state == 'quarantined' else 'retry')
                    if state == 'quarantined':
                        self.metrics.record('recovery_held')
                except Exception:
                    pass
            if state == 'quarantined':
                try:
                    # A terminal quarantine names the strongest diagnosis it
                    # holds: the structured worker_failure of a validation or
                    # recovery handoff, else the evidence this attempt
                    # carried, else the diagnosis earlier ladder attempts
                    # preserved on the job (the exhausting attempt may arrive
                    # evidence-less), else the historical
                    # unknown/unclassified shape for a never-diagnosed unit.
                    diagnosis = worker_failure or worker_failure_evidence or preserved_diagnosis or {}
                    terminal_stage = diagnosis.get('stage', 'unknown')
                    terminal_reason = diagnosis.get('reason', 'unclassified')
                    if language_guard_redrive_failure(diagnosis):
                        # The language guard is the designed redrive handoff:
                        # a typed, evidence-backed terminal hold that the
                        # fenced independent-recognizer lane settles. It keeps
                        # the same durable state and the awaiting-recovery
                        # warning below, but it is not a worker fault, so it
                        # leaves the ERROR quarantine channel to faults.
                        logger.info(
                            'event=batch_language_guard outcome=held_for_redrive attempt=%d recovery=held stage=%s worker_reason=%s',
                            attempt,
                            terminal_stage,
                            terminal_reason,
                        )
                    else:
                        logger.error(
                            'event=batch_quarantined reason=worker_failed attempt=%d recovery=held stage=%s worker_reason=%s',
                            attempt,
                            terminal_stage,
                            terminal_reason,
                        )
                    logger.warning('event=batch_recovery outcome=held reason=awaiting_fenced_recovery')
                except Exception:
                    pass
        return bool(outcome)

    def defer(
        self,
        segment_id: str,
        token: str,
        now: float,
        retry_after: float = 30,
        *,
        held_reason: str | None = None,
        admission_refused: bool = False,
    ) -> bool:
        """Policy/capacity refusal is waiting, not a provider failure attempt.

        ``held_reason`` carries the bounded machine reason from the admission
        decision that caused the defer; it records the latest decision in the
        same transaction, so an outside reader can classify the wait without
        a second round-trip. Refund defers (shutdown, GPU abort) pass none and
        preserve the previously recorded decision. ``last_policy_hold`` keeps
        the latest hold across an unevaluated re-evaluation (which clears the
        decision to BLIND) until an allow is sealed or another hold replaces
        it, so the uncommitted-age proxy does not flap on a parked job.
        """

        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return False
            delay = retry_after
            if admission_refused:
                previous = job.get('admission_refusals', 0)
                previous = previous if type(previous) is int and 0 <= previous <= 5 else 0
                streak = min(previous + 1, 5)
                job['admission_refusals'] = streak
                # Bad/missing authority stays deferred; it never grants compute.
                delay = _admission_retry_delay(delay, streak)
                if not held_reason:
                    # A prior allow is not the latest decision when this RPC
                    # was unevaluated. Preserve BLIND instead of a false hold.
                    job.pop('compute_decision', None)
            job.update(
                state='retry',
                available_at=now + max(1, min(86400, delay)),
                attempt=max(0, job['attempt'] - 1),
                token='',
                lease_until=0.0,
            )
            if held_reason:
                job['compute_decision'] = {'reason': held_reason, 'outcome': 'held', 'at': now}
                job['last_policy_hold'] = {'reason': held_reason, 'at': now}
            tx.put('jobs', segment_id, job)
            return True

        with store_operation('batch_defer'):
            deferred = self.store.run(commit)
        if deferred and admission_refused and self.metrics:
            try:
                self.metrics.record(
                    'admission_policy_deferred' if held_reason else 'admission_unevaluated_deferred',
                    reason=held_reason,
                )
            except Exception:
                pass  # Metrics cannot turn a committed defer into a retry.
        return deferred

    def release(self, segment_id: str, token: str, now: float) -> bool:
        """Expire a held lease now: the lease-expiry transition without the wait.

        For a holder that can no longer publish. The attempt stays charged and
        the retry backoff applies, exactly as ``recover`` would after expiry;
        a stale token is fenced like every other transition.
        """

        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return False
            _defer(job, now, 'lease_released')
            tx.put('jobs', segment_id, job)
            return True

        with store_operation('batch_release'):
            return self.store.run(commit)

    def recover(self, now: float, limit: int = 100) -> int:
        # Advisory rejoin seeds for the sweep: one map per sweep covers the
        # legacy migration and every retry requeue below, read outside the
        # transactions (never the argmax shard's abort set).
        seeds = rejoin_frontiers(self.store, (0, 1, 2))
        with store_operation('batch_recover'):
            try:
                self.store.run(lambda tx: migrate_legacy(tx, now, seeds))
            except FirestoreContentionExhausted as error:
                # A lost migration budget is one bounded retry at the next
                # sweep, not a reason to starve every expired lease behind it.
                if not maintenance_contention_continuation_enabled():
                    raise
                logger.warning(
                    'event=batch_recover outcome=retry scope=migrate exception_type=%s%s',
                    type(error).__name__,
                    error_site_field(error),
                )
            recovered = 0
            candidates, observations = {}, []
            for state in ('leased', 'retry'):
                for segment_id in self.store.due(state, now, limit):

                    def commit(tx: Transaction):
                        observations.clear()
                        job = tx.get('jobs', segment_id)
                        if job.get('state') == 'leased' and job['lease_until'] <= now:
                            outcome = expire_lease(
                                tx,
                                job,
                                now,
                                stage_policy=stage_in_transaction,
                                candidates=candidates,
                                observations=observations,
                                defer=_defer,
                            )
                        elif job.get('state') == 'retry' and job['available_at'] <= now:
                            control = read_control(tx, scheduler_control_key(job['owner_key']))
                            job['state'] = 'ready'
                            _append(tx, control, job, now, seeds.get(int(job['priority']), 0.0))
                            outcome = ('requeued', 0, None)
                        else:
                            return None
                        tx.put('jobs', segment_id, job)
                        return outcome

                    try:
                        outcome = self.store.run(commit, operation='batch_recover')
                        record_policy_observations(observations)
                    except BatchPrivacyBlocked:
                        self.store.quarantine_fenced(segment_id, now)
                        continue
                    except FirestoreContentionExhausted as error:
                        # One hot item loses its budget; the item stays due and
                        # the next sweep re-decides it, so the leases behind it
                        # recover this pass instead of never. The store-level
                        # damper spaces the re-strike; the sweep cadence (>=5s)
                        # bounds it.
                        if not maintenance_contention_continuation_enabled():
                            raise
                        logger.warning(
                            'event=batch_recover outcome=retry scope=item exception_type=%s%s',
                            type(error).__name__,
                            error_site_field(error),
                        )
                        continue
                    if outcome:
                        recovered += 1
                        observe_recovery(outcome, self.metrics)
            return recovered

    @staticmethod
    def restore_audio_in_transaction(tx: Transaction, job: dict, now: float, *, frontier: float = 0.0) -> None:
        """Requeue one CAS-verified missing-input repair under its original identity.

        The artifact-missing store owns the content/privacy/staging checks. No
        paid recovery intent or sibling receipt is reset by this queue mutation.
        ``frontier`` is the advisory rejoin seed read outside the caller's
        transaction (``Scheduler.rejoin_frontiers``).
        """
        marker = job.get('artifact_disposition') or {}
        if (
            job.get('state') != 'quarantined'
            or job.get('recovery_state') != 'failed_held'
            or marker.get('state') != 'restored'
            or job.get('result')
            or job.get('merge_pending') is not False
            or job.get('token')
            or job.get('lease_until', 0) > now
        ):
            raise ValueError('verified missing-input repair required')
        control = read_control(tx, scheduler_control_key(job['owner_key']))
        job.update(state='ready', available_at=now, merge_pending=True, token='', lease_until=0.0)
        # A restored ladder collects its own diagnosis; the quarantined
        # epoch's evidence must not name the new one.
        job.pop('worker_failure_evidence', None)
        _append(tx, control, job, now, frontier)
        tx.put('jobs', job['segment_id'], job)

    @staticmethod
    def redrive_in_transaction(tx: Transaction, job: dict, now: float, *, frontier: float = 0.0) -> bool:
        """Requeue one dead unit; ``frontier`` is the advisory rejoin seed read
        outside the caller's transaction (``Scheduler.rejoin_frontiers``)."""
        if job.get('state') != 'dead' or not job.get('merge_pending'):
            return False
        control = read_control(tx, scheduler_control_key(job['owner_key']))
        job.update(
            state='ready',
            available_at=now,
            failure='',
            token='',
            lease_until=0.0,
            retry_started_at=job.get('retry_started_at', now),
        )
        # A redriven ladder collects its own diagnosis too.
        job.pop('worker_failure_evidence', None)
        _append(tx, control, job, now, frontier)
        tx.put('jobs', job['segment_id'], job)
        return True

    def redrive_dead(self, segment_id: str, now: float) -> bool:
        """Authenticated recovery of historical dead records; never skips a gap."""
        # Advisory rejoin seed: probe the row for its priority outside the
        # transaction; the body re-verifies every fence it acts on.
        probed = self.store.probe('jobs', segment_id)
        priority = int(probed.get('priority', 0))
        frontier = rejoin_frontiers(self.store, (priority,)).get(priority, 0.0)
        with store_operation('batch_redrive'):
            return self.store.run(
                lambda tx: self.redrive_in_transaction(tx, tx.get('jobs', segment_id), now, frontier=frontier)
            )

    def acknowledge_gpu_idle(self, gpu_id: str, token: str) -> bool:
        """Only the hardware admission owner may call this after GPU quiescence.

        Complete/fail/lease expiry never proves non-preemptible inference stopped.
        An orphaned shared reservation stays closed until that owner verifies idle.
        """
        if not gpu_id or len(gpu_id) > 128 or not token:
            raise ValueError('bounded GPU identity and current reservation token required')

        def commit(tx):
            key = owner_key(gpu_id)
            gpu = tx.get('gpus', key)
            if not gpu.get('token'):
                return gpu.get('released_token') == token
            if gpu['token'] != token:
                return False
            gpu.update(token='', lease_until=0.0, released_token=token)
            tx.put('gpus', key, gpu)
            return True

        with store_operation('batch_gpu_release'):
            return self.store.run(commit)
