"""Fenced, duration-fair pull scheduling over durable transactional documents."""

import hashlib
from dataclasses import dataclass
import math
import logging
import random
from threading import Lock
import uuid
from time import monotonic, time as wall_time

from database.batch_pipeline_store import Store, Transaction, pull_operation
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_recovery_fence import RecoveryFence
from database.firestore_transaction_retry import FirestoreContentionExhausted
from config.batch_pipeline import (
    FRESH_CAPTURE_LAG_SECONDS,
    SCHEDULER_SHARDS,
    control_candidate_fanout,
    pull_busy_borrow_enabled,
    pull_multi_lease_enabled,
    scheduler_control_key,
    shard_spread_enabled,
    skip_unchanged_control_write_enabled,
)
from config.policy import resolve_batch_policy
from config.batch_pipeline_packing import sample_rate as packing_sample_rate
from config import batch_pipeline_protected_share as protected_share
from config.stt_cap_dispatch import offline_admission_enabled as cap_dispatch_enabled
from database.batch_pipeline_policy import stage_in_transaction, record_policy_observations, check_unit_privacy
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import LeasedWork, Priority, WorkItem, WorkResult, PoolCapacity, attach_held_vad
from utils.batch_pipeline.capacity import within_unit_ceiling
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.packing_counterfactual import job_observation, sampled as packing_sampled
from utils.batch_pipeline.control import activate, consume_frontier_hint, field, migrate_legacy, read_control
from utils.batch_pipeline.errors import error_site_field, validate_worker_failure
from utils.batch_pipeline.held_terminal import retained_digest_changed_held
from utils.batch_pipeline.retry_policy import quarantine_job, expire_lease, observe_recovery
from config.backlog_state_machine import MAX_HELD_REDRIVES, held_redrive_budget_enabled, held_redrive_counter_enabled
from database import batch_pipeline_allowance_hold as allowance_hold
from database.batch_pipeline_recovery_discovery import RecoveryCaller, RecoveryQuery

QUANTUM_SECONDS = 30.0
LEASE_SECONDS = 120.0
RETRY_BACKOFF_CAP_SECONDS = 600
MAX_ACTIVE_OWNERS = 1024
MAX_VISITS = 128
# The walk visits another queue only below this many buffered writes (flush
# refuses 450); a stop commits the rotations so far and the next pull resumes.
PULL_WRITE_HEADROOM = 300
HEAD_OWNER_BUDGET = 64
CONTENTION_BACKOFF_CAP_SECONDS = 30.0
PULL_CLAIM_SECONDS = 30.0
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedriveResult:
    """Updated job staged by a successful re-drive and its post-commit signal."""

    job: dict
    spent: bool = False


def _admission_retry_delay(value: object, streak: int) -> float:
    minimum = min(300, 30 * 2 ** (streak - 1))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return minimum
    if isinstance(value, float) and not math.isfinite(value):
        return minimum
    return max(minimum, min(86400, value))


def owner_key(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode()).hexdigest()


def _append(tx: Transaction, control: dict, job: dict) -> None:
    queue_key = f"{job['priority']}_{job['owner_key']}"
    queue = tx.get('queues', queue_key) or {'head': '', 'tail': '', 'deficit': 0.0, 'continuing': False}
    ring = control['rings'][str(job['priority'])]
    tail = None
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
    queue['tail'] = job['segment_id']
    job['next'] = ''
    control_key = scheduler_control_key(job['owner_key'])
    activate(tx, control, job['priority'], job['available_at'], control_key)
    # An owner already in the ring, on an active shard with no pull backoff to clear, leaves
    # the shard identical; rewriting it only conflicts with every pull and admission on it.
    write_control = not skip_unchanged_control_write_enabled() or control != tx.get('control', control_key)
    # Finish queue/frontier/control reads before staging the first write.
    if tail is not None:
        tx.put('jobs', tail['segment_id'], tail)
    tx.put('queues', queue_key, queue)
    if write_control:
        tx.put('control', control_key, control)


def _pool_allows(job: dict, max_seconds: float) -> bool:
    return within_unit_ceiling(job['duration_seconds'], max_seconds)


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

    def get_existing(self, table: str, key: str) -> dict | None:
        return self._tx.get_existing(table, key)

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

    def pending_page(self, owner_key: str, limit: int) -> list[dict]:
        return [own for job in self._tx.pending_page(owner_key, limit) if (own := self._own(job)) is not None]

    def first_ready_pending(self, owner_key: str) -> dict | None:
        return self._own(self._tx.first_ready_pending(owner_key))

    def fresh_first_pending(self, owner_key: str) -> dict | None:
        return self._own(self._tx.fresh_first_pending(owner_key))

    def fresh_first_ready_pending(self, owner_key: str) -> dict | None:
        return self._own(self._tx.fresh_first_ready_pending(owner_key))

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        return self._own(self._tx.ready_predecessor(owner_key, priority, segment_id))

    def protected_ready(self, owner_key: str, priority: int, now: float, *, after=None) -> list[dict]:
        rows = []
        for job in self._tx.protected_ready(owner_key, priority, now, after=after):
            current = self._own(job)
            if current is not None:
                rows.append(current)
        return rows

    def service_frontier(self, priority: int) -> float:
        return self._tx.service_frontier(priority)

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
    candidates=None,
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
        or not _pool_allows(head, max_seconds)
    ):
        return job
    previous = tx.ready_predecessor(job['owner_key'], job['priority'], head['segment_id'])
    if not previous or previous.get('state') != 'ready' or previous.get('next') != head['segment_id']:
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
    if not stage_in_transaction(tx, head, 'scheduler', observations=observations, candidates=candidates).head_priority:
        return job
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


def _prefer_protected(tx, queue, job, budget, now, max_seconds):
    """One indexed page per owner visit, sharing the original FIFO and DRR credit.

    Old workers see a valid ordinary queue at every commit. A failed splice
    changes no links. The cursor can skip held/invalid/future-due candidates
    without an unbounded walk or a new priority value that old readers ignore.
    """
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    page = tx.protected_ready(job['owner_key'], job['priority'], now, after=queue.get('protected_after'))
    budget[1] += max(1, len(page))  # Firestore charges at least one read for an empty query.
    queue['protected_after'] = None
    for candidate in page:
        queue['protected_after'] = [candidate['capture_at'], candidate['segment_id']]
        if not protected_share.eligible(candidate, now) or not _pool_allows(candidate, max_seconds):
            continue
        try:
            check_unit_privacy(tx, candidate)
        except BatchPrivacyBlocked:
            continue
        if candidate['segment_id'] == job['segment_id']:
            return candidate
        previous = tx.ready_predecessor(job['owner_key'], job['priority'], candidate['segment_id'])
        budget[1] += 2  # LIMIT 2; ambiguous predecessors fail closed.
        if not previous or previous.get('state') != 'ready' or previous.get('next') != candidate['segment_id']:
            continue
        try:
            check_unit_privacy(tx, previous)
        except BatchPrivacyBlocked:
            continue
        previous['next'] = candidate['next']
        if queue['tail'] == candidate['segment_id']:
            queue['tail'] = previous['segment_id']
        candidate['next'] = queue['head']
        queue['head'] = candidate['segment_id']
        tx.put('jobs', previous['segment_id'], previous)
        tx.put('jobs', candidate['segment_id'], candidate)
        return candidate
    return None


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


def stored_identity(job: dict) -> dict:
    """The job as admitted: a demoted row compares against its admission priority."""
    if 'admitted_priority' not in job:
        return job
    return {**job, 'priority': job['admitted_priority']}


def requeue_due_retry(tx: Transaction, job: dict, now: float, *, priority: int | None = None) -> str | None:
    """A due retry row rejoins DRR, or parks if its latest decision is an allowance hold.

    ``priority`` may only lower the service class; the admission priority stays the row's identity."""
    if job.get('state') != 'retry' or job['available_at'] > now:
        return None
    if allowance_hold.enabled() and allowance_hold.park(tx, job, now):
        return 'allowance_parked'
    if priority is not None and int(priority) > job['priority']:
        job.setdefault('admitted_priority', job['priority'])
        job['priority'] = int(priority)
    control = read_control(tx, scheduler_control_key(job['owner_key']))
    job['state'] = 'ready'
    _append(tx, control, job)
    tx.put('jobs', job['segment_id'], job)
    return 'requeued'


class Scheduler:
    def __init__(
        self,
        store: Store,
        *,
        metrics: QueueMetrics | None = None,
        worker_id: str = '',
        recovery_caller: RecoveryCaller = RecoveryCaller.UNKNOWN,
    ):
        self.store = store
        self.recovery_caller = recovery_caller
        self.metrics = metrics
        # The shared-live GPU pull is retired; the dedicated batch pool is the
        # only queue this scheduler serves.
        self.pool = 'batch'
        self.worker_id = worker_id or uuid.uuid4().hex
        self._contention_failures = 0
        self._contention_backoff_until = 0.0
        self._contention_generation = 0
        self._contention_lock = Lock()
        self._share_lock = Lock()
        self._share_turn = 0
        self._residual_turn = 0
        self._protected_priority_turn = 0
        self._protected_retry_after = None

    def enqueue(self, item: WorkItem, now: float) -> bool:
        return self.store.run(lambda tx: self.enqueue_in_transaction(tx, item, now))

    @staticmethod
    def enqueue_in_transaction(
        tx: Transaction, item: WorkItem, now: float, *, policy=None, park_allowance: bool = False
    ) -> bool:
        if getattr(item, 'source_alias_of', None):
            raise ValueError('source aliases cannot enter paid queues')
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
            stored = stored_identity(previous)
            if any(
                stored.get(key, {'unit_kind': 'conversation', 'requires_compute_admission': False}.get(key)) != value
                for key, value in immutable.items()
                if not (key == 'privacy_generation' and value is None)
            ):
                raise ValueError('segment ID reused with different immutable work')
            return False
        policy = policy or resolve_batch_policy(item.owner_id)
        key = owner_key(item.owner_id)
        owner = tx.get('owners', key)
        watermark = owner.get('watermark')
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
        parked = (
            park_allowance
            and not previous
            and item.requires_compute_admission
            and policy.stt_route == 'parakeet'
            and policy.provider_reason != 'byok'
            and allowance_hold.park(tx, job, now, at_intake=True)
        )
        if not parked:
            control = read_control(tx, scheduler_control_key(key))
            _append(tx, control, job)
            tx.put('jobs', item.segment_id, job)
        # Admission and merge serialize through this fence even for different classes.
        owner['revision'] = owner.get('revision', 0) + 1
        tx.put('owners', key, owner)
        return True

    def pull(
        self,
        now: float,
        limit: int = 1,
        *,
        capacity: PoolCapacity | None = None,
        borrow_when_fresh_busy: bool = False,
    ) -> list[LeasedWork]:
        if not 1 <= limit <= 32:
            raise ValueError('pull limit must be in [1, 32]')
        with self._contention_lock:
            if self._contention_backoff_until > monotonic():
                return []
            contention_generation = self._contention_generation
        # No snapshot is the dedicated-batch worker contract only.
        allow_backfill, max_seconds, backfill_budget = True, 7200.0, limit
        if capacity is not None:
            slots, allow_backfill, max_seconds = capacity.limits(now)
            limit = min(limit, slots)
            backfill_budget = max(0, slots - capacity.reserved_fresh_slots)
        result = []
        contention_deferred = False
        # One shard transaction may lease several units from the ring it has
        # already read; the kill switch restores one lease per transaction.
        multi = pull_multi_lease_enabled()
        borrow = borrow_when_fresh_busy and pull_busy_borrow_enabled()
        protected = protected_share.enabled()
        discovery_budget = [protected_share.READY_OWNER_BUDGET, 0, protected_share.READY_OWNER_BUDGET]
        service_plan = {}
        while len(result) < limit:
            remaining = limit - len(result) if multi else 1
            try:
                leases = self._pull_one(
                    now,
                    allow_backfill=allow_backfill and backfill_budget > 0,
                    max_seconds=max_seconds,
                    max_fresh=remaining,
                    max_backfill=min(remaining, backfill_budget),
                    borrow_when_fresh_busy=borrow,
                    protected=protected,
                    discovery_budget=discovery_budget,
                    service_plan=service_plan,
                    service_slots=min(backfill_budget, limit - len(result)),
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
        if not contention_deferred:
            with self._contention_lock:
                if self._contention_generation == contention_generation:
                    self._contention_failures = 0
                    self._contention_backoff_until = 0.0
        if protected and self.metrics:
            try:
                self.metrics.record_discovery('ready', discovery_budget[1])
            except Exception:
                pass
        return result

    def _service_phases(self, protected, plan, slots):
        # Build the bounded pull-cycle quotas only after FRESH and its busy
        # fence. Batch within a quota so protection does not serialize every
        # residual lease into a separate claim/transaction.
        yield Priority.FRESH, False
        if not protected:
            yield Priority.RECENT, False
            yield Priority.DEEP, False
            return
        if not plan:
            with self._share_lock:
                percent = protected_share.share_percent()
                quota = {'protected': 0, Priority.RECENT: 0, Priority.DEEP: 0}
                residual = (Priority.RECENT, Priority.DEEP)
                if self._residual_turn % 2:
                    residual = tuple(reversed(residual))
                for _ in range(slots):
                    if (self._share_turn * percent) % 100 < percent:
                        quota['protected'] += 1
                    else:
                        quota[(Priority.RECENT, Priority.DEEP)[self._residual_turn % 2]] += 1
                        self._residual_turn += 1
                    self._share_turn += 1
                urgent = (Priority.RECENT, Priority.DEEP)
                if self._protected_priority_turn % 2:
                    urgent = tuple(reversed(urgent))
                self._protected_priority_turn += bool(quota['protected'])
                plan.update(quota=quota, urgent=urgent, residual=residual)
        quota = plan['quota']
        if quota['protected']:
            for priority in plan['urgent']:
                yield priority, True
            # Neither protected priority supplied a lease (or discovery hit
            # its budget). Lend unused opportunities, never spend them on holds.
            with self._share_lock:
                for _ in range(quota['protected']):
                    quota[(Priority.RECENT, Priority.DEEP)[self._residual_turn % 2]] += 1
                    self._residual_turn += 1
            quota['protected'] = 0
        for priority in (*plan['residual'], plan['residual'][0]):
            if not quota[priority]:
                continue
            yield priority, False
            # Empty residual classes lend to the other one. Revisit the first
            # preference once if the second proved empty after it was served.
            other = Priority.DEEP if priority == Priority.RECENT else Priority.RECENT
            quota[other] += quota[priority]
            quota[priority] = 0

    def _pull_one(
        self,
        now: float,
        *,
        allow_backfill: bool,
        max_seconds: float,
        max_fresh: int = 1,
        max_backfill: int = 1,
        borrow_when_fresh_busy: bool = False,
        protected: bool = False,
        discovery_budget: list[int] | None = None,
        service_plan: dict | None = None,
        service_slots=0,
    ) -> list[LeasedWork]:
        if discovery_budget is None:
            discovery_budget = [0, 0, 0]
        if service_plan is None:
            service_plan = {}
        for priority, protected_phase in self._service_phases(protected, service_plan, service_slots or max_backfill):
            if priority != Priority.FRESH and not allow_backfill:
                break
            max_leases = max_fresh if priority == Priority.FRESH else max_backfill
            service_key = 'protected' if protected_phase else priority
            if protected and priority != Priority.FRESH:
                max_leases = min(max_leases, service_plan['quota'][service_key])
            if max_leases < 1:
                break
            spread = shard_spread_enabled()
            excluded = set()
            busy = False
            candidates = None
            refreshed = False
            candidate_fanout = control_candidate_fanout()
            for _ in range(128):
                if protected_phase and (discovery_budget[0] <= 0 or discovery_budget[2] <= 0):
                    break
                if spread:
                    if candidates is None:
                        candidates = self.store.control_candidates(
                            int(priority), self.pool, now, worker_id=self.worker_id, fanout=candidate_fanout
                        )
                    shard = next((key for key in candidates if key not in excluded), None)
                else:
                    if protected_phase:
                        shard = self.store.control_candidate(int(priority), self.pool, now, exclude=excluded)
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
                if protected_phase:
                    discovery_budget[2] -= 1
                if protected:
                    receipts, eligible = self._pull_shard(
                        now,
                        shard,
                        priority,
                        max_seconds,
                        max_leases,
                        protected_phase=protected_phase,
                        discovery_budget=discovery_budget,
                        service=('protected' if protected_phase else priority.name.lower()) if protected else None,
                    )
                else:
                    receipts, eligible = self._pull_shard(now, shard, priority, max_seconds, max_leases)
                if receipts:
                    if protected and priority != Priority.FRESH:
                        service_plan['quota'][service_key] -= len(receipts)
                    for _, enqueued_at, relet in receipts:
                        if self.metrics:
                            try:
                                self.metrics.record('leased', wait_seconds=now - enqueued_at, relet=relet)
                            except Exception:
                                pass  # Metrics cannot turn an issued lease into a failed pull.
                    return [lease for lease, _, _ in receipts]
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
            if busy and not borrow_when_fresh_busy and not protected_phase:
                # Busy higher-priority work is still pending. Do not borrow
                # backfill capacity while another puller owns its shard.
                return []
            # A borrowing lane found every eligible shard of this priority
            # claimed: each claimant is serving that work right now, so this
            # lane leases the next priority instead of idling. The pump's
            # first lane never borrows, which keeps fresh-first per pump.
        return []

    def _pull_shard(
        self,
        now,
        shard,
        priority,
        max_seconds,
        max_leases=1,
        *,
        protected_phase=False,
        discovery_budget: list[int] | None = None,
        service=None,
    ):
        if discovery_budget is None:
            discovery_budget = [0, 0, 0]
        candidates = {}
        started = monotonic()
        spread = shard_spread_enabled()
        claim_token = uuid.uuid4().hex
        attempt_budgets: list[list[int]] = []
        packing_rate = packing_sample_rate() if self.metrics else 0.0

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
            control = read_control(tx, shard)
            consume_frontier_hint(tx, control, int(priority), current_time())
            ring = control['rings'][str(int(priority))]
            eligible_queues, blocked = {}, set()
            owner_count = max(1, len(ring))
            head_budget = [HEAD_OWNER_BUDGET]
            visits, write_stop = 0, False
            # Attempt-local accounting: retries cannot exhaust the next callback's budget.
            protected_budget = [discovery_budget[0], 0]
            if protected_phase:
                attempt_budgets.append(protected_budget)
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
                if (
                    protected_phase
                    and protected_budget[0] <= 0
                    and queue_key not in eligible_queues
                    and queue_key not in blocked
                ):
                    write_stop = True
                    break
                queue = tx.get('queues', queue_key)
                job = tx.get('jobs', queue['head']) if queue.get('head') else {}
                if not job:
                    ring.pop(0)  # A completed purge may have removed this queue.
                    continue
                if protected_phase and queue_key not in eligible_queues and queue_key not in blocked:
                    selected = _prefer_protected(tx, queue, job, protected_budget, current_time(), max_seconds)
                    tx.put('queues', queue_key, queue)
                    if selected is None:
                        blocked.add(queue_key)
                    else:
                        job = selected
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
                            tx, job, 'scheduler', observations=observations, candidates=candidates
                        )
                        if policy.head_priority and not protected_phase:
                            job = _prefer_merge_head(
                                tx,
                                queue,
                                job,
                                head_budget,
                                observations,
                                now=now,
                                max_seconds=max_seconds,
                                candidates=candidates,
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
                            stage_in_transaction(tx, job, 'scheduler', candidates=candidates)
                            allowed = _pool_allows(job, max_seconds)
                        except BatchPrivacyBlocked:
                            allowed, park = False, 'privacy'
                        if allowed:
                            if protected_phase:
                                allowed = protected_share.eligible(job, current_time())
                        if allowed:
                            eligible_queues[queue_key] = job['duration_seconds']
                        else:
                            blocked.add(queue_key)
                            # Parking is otherwise silent: the owner's whole FIFO waits behind this head.
                            park = park or 'pool_duration'
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
                lease_clock = current_time()
                if protected_phase and not protected_share.eligible(job, lease_clock):
                    blocked.add(queue_key)
                    eligible_queues.pop(queue_key, None)
                    continue
                queue['deficit'] -= cost
                queue['head'] = job['next']
                queue['continuing'] = True
                if not queue['head']:
                    queue.update(tail='', deficit=0.0, continuing=False)
                    ring.pop(0)
                token = uuid.uuid4().hex
                if (
                    (job.get('projection_binding') or {}).get('native_record')
                    and job['attempt'] == 0
                    and not job.get('admission_refusals')
                ):
                    job.setdefault('record_first_leased_at', wall_time())
                cohort_age = (
                    lease_clock - protected_share.capture_end(job)
                    if service is not None and protected_share.eligible(job, lease_clock)
                    else None
                )
                job.update(
                    state='leased',
                    token=token,
                    attempt=job['attempt'] + 1,
                    lease_until=now + LEASE_SECONDS,
                )
                if not job.get('requires_compute_admission') and not cap_dispatch_enabled(job['owner_id'], 'batch'):
                    # The pump dispatches this lease without admission, so it
                    # is a real commitment: a parked hold must not hide it.
                    job.pop('last_policy_hold', None)
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
                if service is not None:
                    observations.append(('service_' + service, cohort_age))
                if packing_sampled(token, packing_rate):
                    observations.append(
                        ('packing', (job['owner_key'], job['segment_id'], int(priority), job['attempt'], lease_clock))
                    )
                # The owner's next head is a different unit: it gets its own
                # privacy, policy and pool checks before it can be leased.
                eligible_queues.pop(queue_key, None)
                owner_count = max(1, len(ring))
            # Ring rotations after the last lease commit with their deficits.
            control[field(int(priority), 'active')] = bool(ring)
            if not receipts and not eligible_queues and not write_stop and not protected_phase:
                control[field(int(priority), self.pool + '_available_at')] = now + 30
            tx.put('control', shard, control)
            # A write stop proved nothing about the unvisited queues: no backoff.
            return receipts or None, bool(receipts or eligible_queues or write_stop), observations, protected_budget

        try:
            with pull_operation('pull', shard):
                outcome = self.store.run(commit)
        finally:
            if protected_phase:
                discovery_budget[1] += sum(budget[1] for budget in attempt_budgets)
        receipts, eligible, observations = outcome[:3]
        if protected_phase and len(outcome) == 4:
            used, _ = outcome[3]
            discovery_budget[0] = used
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
                    if event == 'packing':
                        owner, segment, lane_priority, attempt, lease_clock = age
                        # Reconstruct ready candidates leased later by this same
                        # commit. The projected read sees their new lease state.
                        later = {}
                        selected = False
                        for lease, _, _ in receipts or ():
                            if selected:
                                later[lease.item.segment_id] = lease.attempt
                            elif lease.item.segment_id == segment:
                                selected = True
                        self.metrics.packing.observe(
                            self.store, owner, segment, lane_priority, attempt, lease_clock, max_seconds, later
                        )
                    elif event.startswith('service_'):
                        self.metrics.record_service(event[len('service_') :], age=age)
                    else:
                        self.metrics.record_head(event, priority, age=age)
                except Exception:
                    pass  # Metrics cannot turn an issued lease into a failed pull.
        return receipts, eligible

    def heartbeat(self, segment_id: str, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return False
            job['lease_until'] = max(job['lease_until'], now + LEASE_SECONDS)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def complete(self, result: WorkResult, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', result.segment_id)
            if job.get('state') in {'result_ready', 'committed'}:
                return result.matches_persisted(job.get('result')) and job.get('token') == token, False, 0, {}
            if not owns_lease(job, token, now):
                return False, False, 0, {}
            if job.get('requires_compute_admission') and job.get('compute_admission_token') != token:
                return False, False, 0, {}
            packing = job_observation(job)
            job.update(state='result_ready', result=result.to_dict(), ready_at=now)
            job.pop('retry_started_at', None)
            job.pop('admission_refusals', None)
            job.pop('packing_observation', None)
            tx.put('jobs', result.segment_id, job)
            return True, True, job['duration_seconds'], packing

        accepted, changed, seconds, packing = self.store.run(commit)
        if changed and self.metrics:
            self.metrics.record('completed')
            try:
                self.metrics.record_completed_audio(result.outcome, seconds)
            except Exception:
                pass  # Duration telemetry cannot undo a fenced completion.
            try:
                self.metrics.packing.complete(packing)
            except Exception:
                pass  # The intake cohort is optional telemetry.
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
        measured_held_vad_speech_seconds: float | None = None,
        worker_vad_receipt: dict | None = None,
    ) -> bool:
        if worker_failure is not None:
            validate_worker_failure(worker_failure)
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

        def commit(tx):
            observations.clear()
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return None
            policy = stage_in_transaction(tx, job, 'scheduler', candidates=candidates, observations=observations)
            attach_held_vad(job, measured_held_vad_speech_seconds, worker_vad_receipt)
            if quarantine or worker_failure is not None or job['attempt'] >= policy.max_attempts:
                quarantine_job(tx, job, now, 'worker_failed')
                if quarantine and padded_retry in {'empty', 'skipped_oversize', 'skipped_long_speech'}:
                    job['worker_empty_evidence'] = {'padded_retry': padded_retry, 'version': 1}
                if worker_failure is not None:
                    job['worker_failure'] = dict(worker_failure)
            else:
                _defer(job, now, 'worker_failed')
            tx.put('jobs', segment_id, job)
            return job['state'], job['attempt'], job['duration_seconds']

        outcome = self.store.run(commit)
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
                    logger.error(
                        'event=batch_quarantined reason=worker_failed attempt=%d recovery=held stage=%s worker_reason=%s',
                        attempt,
                        worker_failure['stage'] if worker_failure else 'unknown',
                        worker_failure['reason'] if worker_failure else 'unclassified',
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
            if allowance_hold.enabled() and held_reason == 'allowance_exhausted' and allowance_hold.park(tx, job, now):
                return True
            tx.put('jobs', segment_id, job)
            return True

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

        return self.store.run(commit)

    def recover(self, now: float, limit: int = 100, *, caller: RecoveryCaller | None = None) -> int:
        with RecoveryQuery(self.store, now, limit, caller if caller is not None else self.recovery_caller) as query:
            return self._recover(now, limit, query)

    def _recover(self, now: float, limit: int, query: RecoveryQuery) -> int:
        self.store.run(lambda tx: migrate_legacy(tx, now))
        recovered = 0
        candidates, observations = {}, []
        protected = protected_share.enabled()

        def recover_page(segments, discovery=None):
            nonlocal recovered
            for segment_id in segments:

                def commit(tx: Transaction):
                    observations.clear()
                    job = tx.get('jobs', segment_id)
                    if state == 'leased' and job.get('state') == 'leased' and job['lease_until'] <= now:
                        outcome = expire_lease(
                            tx,
                            job,
                            now,
                            stage_policy=stage_in_transaction,
                            candidates=candidates,
                            observations=observations,
                            defer=_defer,
                        )
                    elif state == 'retry' and job.get('state') == 'retry' and job['available_at'] <= now:
                        if segment_id in protected_ids and not protected_share.eligible(job, now):
                            return None
                        return (requeue_due_retry(tx, job, now), 0, None)
                    else:
                        return None
                    tx.put('jobs', segment_id, job)
                    return outcome

                try:
                    outcome = self.store.run(commit)
                    record_policy_observations(observations)
                except BatchPrivacyBlocked:
                    self.store.quarantine_fenced(segment_id, now)
                    if discovery is not None:
                        discovery.candidate(False)
                    continue
                if discovery is not None:
                    discovery.candidate(bool(outcome))
                if outcome:
                    recovered += 1
                    observe_recovery(outcome, self.metrics)

        for state in ('leased', 'retry'):
            protected_ids = set()
            if state == 'leased':
                recover_page(query.discover(), query)
                if query.needs_primary():
                    recover_page(query.primary('hint_ineligible'), query)
            elif protected:
                size = max(1, min(limit, protected_share.RETRY_PAGE_SIZE))
                reserved = max(1, size * protected_share.share_percent() // 100)
                # Preserve at least one oldest-due discovery, even for limit=1.
                ordinary = self.store.due(state, now, max(1, size - reserved))
                with self._share_lock:
                    page = self.store.protected_retries(now, reserved, after=self._protected_retry_after)
                    self._protected_retry_after = [page[-1]['capture_at'], page[-1]['segment_id']] if page else None
                protected_ids = {row['segment_id'] for row in page if protected_share.eligible(row, now)}
                segments = list(dict.fromkeys([*ordinary, *sorted(protected_ids)]))
                if self.metrics:
                    try:
                        self.metrics.record_discovery('retry', max(1, len(ordinary)) + max(1, len(page)))
                    except Exception:
                        pass
                recover_page(segments)
            else:
                recover_page(self.store.due(state, now, limit))
        return recovered

    @staticmethod
    def release_allowance_in_transaction(tx: Transaction, job: dict, now: float) -> None:
        """Capture-ordered owner release rejoins DRR; current admission is still mandatory."""
        allowance_hold.restore_retry(job, now)
        job.update(state='ready', compute_decision={'outcome': 'unattempted'})
        control = read_control(tx, scheduler_control_key(job['owner_key']))
        _append(tx, control, job)
        tx.put('jobs', job['segment_id'], job)

    @staticmethod
    def restore_audio_in_transaction(tx: Transaction, job: dict, now: float) -> None:
        """Requeue one CAS-verified missing-input repair under its original identity.

        The artifact-missing store owns the content/privacy/staging checks. No
        paid recovery intent or sibling receipt is reset by this queue mutation.
        """
        if job.get('source_alias_of') or job.get('source_alias'):
            raise ValueError('source aliases cannot enter paid queues')
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
        _append(tx, control, job)
        tx.put('jobs', job['segment_id'], job)

    @staticmethod
    def held_requeue_eligible(tx: Transaction, job: dict, now: float, *, allow_dead=True) -> bool:
        """Dormant worker holds only; never reopen an active paid/operator intent."""
        held_dead = (
            allow_dead
            and job.get('state') == 'dead'
            and job.get('dead_letter_reason') in {'held_expired', 'input_expiring'}
        )
        state_ok = job.get('state') == 'quarantined' or held_dead
        lease_until = job.get('lease_until', 0)
        if (
            not state_ok
            or job.get('quarantine_reason') != 'worker_failed'
            # Provider-STT units do not belong to the GPU DRR ring. Their
            # vendor-attempt custody needs its own sanctioned re-drive path.
            or (job.get('stt_route') or {}).get('stt_route') == 'provider'
            or job.get('recovery_state') not in {'held', 'failed_held'}
            or job.get('result')
            # Expiry retains the legacy dead re-drive contract. Also accept
            # earlier held-expired rows written with merge_pending=False.
            or not (job.get('merge_pending') is False or (held_dead and job.get('merge_pending') is True))
            or job.get('token')
            or isinstance(lease_until, bool)
            or not isinstance(lease_until, (int, float))
            or not math.isfinite(lease_until)
            or lease_until > now
        ):
            return False
        recovery = job.get('recovery') or {}
        if recovery and not recovery.get('settled_at'):
            return False
        if any(
            job.get(key) and (job.get(key) or {}).get('state') not in {'completed', 'failed_held'}
            for key in ('silence_disposition', 'terminal_disposition', 'speech_redrive')
        ):
            return False
        return not tx.get('results', job['segment_id'])

    @staticmethod
    def requeue_quarantined_in_transaction(
        tx: Transaction, job: dict, now: float, *, account=True
    ) -> RedriveResult | None:
        """CAS requeue without deleting audio, results, intent or attempt history.

        RecoveryStore owns content/ledger/privacy checks, as the missing-input
        store does for restore_audio_in_transaction. The commit fence still runs.
        """
        if not Scheduler.held_requeue_eligible(tx, job, now):
            return None
        control = read_control(tx, scheduler_control_key(job['owner_key']))
        owner = tx.get('owners', job['owner_key'])
        owner['revision'] = owner.get('revision', 0) + 1
        job.update(state='ready', available_at=now, merge_pending=True, token='', lease_until=0.0, held_requeued_at=now)
        spent = account_held_redrive(job, now) if account else False
        _append(tx, control, job)
        tx.put('owners', job['owner_key'], owner)
        tx.put('jobs', job['segment_id'], job)
        return RedriveResult(job, spent)

    @staticmethod
    def redrive_in_transaction(
        tx: Transaction, job: dict, now: float, *, operator=False, checked=None
    ) -> RedriveResult | None:
        """Return the staged job and spent signal; refuse without a result."""
        # Status polling must not silently undo an input-expiring terminal.
        if job.get('dead_letter_reason') == 'input_expiring' and not operator:
            return None
        if job.get('state') != 'dead' or not job.get('merge_pending'):
            return None
        if job.get('dead_letter_reason') == 'held_expired':
            # A fresh budget and its telemetry require the same content-owner,
            # privacy, result and active-intent CAS as an operator requeue.
            if checked is None:
                return None
            job, _ = checked(tx, job['segment_id'])
            if not operator and retained_digest_changed_held(job):
                # A repeatedly disagreeing pinned source can never satisfy its
                # manifest; automatic intake redrive must not spend a requeue.
                return None
            return Scheduler.requeue_quarantined_in_transaction(tx, job, now)
        control = read_control(tx, scheduler_control_key(job['owner_key']))
        job.update(
            state='ready',
            available_at=now,
            failure='',
            token='',
            lease_until=0.0,
            retry_started_at=job.get('retry_started_at', now),
        )
        _append(tx, control, job)
        tx.put('jobs', job['segment_id'], job)
        return RedriveResult(job)

    def redrive_dead(self, segment_id: str, now: float) -> bool:
        """Authenticated recovery of historical dead records; never skips a gap."""
        outcome = self.store.run(
            lambda tx: self.redrive_in_transaction(
                tx, tx.get('jobs', segment_id), now, operator=True, checked=RecoveryFence(self.store).checked
            )
        )
        if outcome is not None and outcome.spent:
            from utils.backlog_metrics import record_transition

            record_transition('held_redrive_budget_spent')
        return bool(outcome)


def held_redrives(job: dict) -> int:
    """Nonnegative integer metadata; integral Firestore doubles are valid.

    Invalid legacy metadata is repaired from zero on the next committed re-drive.
    Log only the static signal, never the malformed value or content.
    """
    count = job.get('held_redrives', 0)
    if type(count) is int and count >= 0:
        return count
    if type(count) is float and math.isfinite(count) and count >= 0 and count.is_integer():
        return int(count)
    logger.warning('event=batch_held_redrives_malformed action=restart_budget')
    return 0


def account_held_redrive(job: dict, now: float) -> bool:
    """Account a verified held re-drive; return its once-per-unit spent event.

    Durable accounting bounds class 3 independently of the telemetry switch.
    The caller emits the returned signal only after the transaction commits.
    Input-expiring repairs consume no held grant.
    """
    if job.get('dead_letter_reason') == 'input_expiring':
        return False
    prior = held_redrives(job)
    spent = prior >= MAX_HELD_REDRIVES and 'held_redrive_budget_spent_at' not in job
    job['held_redrives'] = prior + 1
    if spent:
        job['held_redrive_budget_spent_at'] = now
    if held_redrive_budget_enabled() and prior < MAX_HELD_REDRIVES and retry_cap_enforced_for(job.get('owner_id', '')):
        job['held_redrive_last_attempt'] = job.get('attempt', 0)
        job['attempt'] = 0
    return spent and held_redrive_counter_enabled()


def retry_cap_enforced_for(owner_id: str) -> bool:
    """Whether the batch lease-expiry retry cap quarantines at the cap for this owner."""
    # Rollback: switching class 1 OFF stops new cap enforcement; existing grants
    # persist until they finish; no clawback. Each grant is capped at
    # MAX_ATTEMPTS only while the retry cap enforces for the owner (class 1 on,
    # or the owner in the served cohort). With class 1 off, lease expiries
    # defer, as on main.
    from utils.capture.retry_cap import retry_cap

    decision = retry_cap(owner_id, 0, 1, enforce=True)
    return decision is not None and decision.serving
