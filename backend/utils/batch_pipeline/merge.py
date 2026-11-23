"""Ordered durable result log. Projection consumers must use stable segment IDs."""

from collections import Counter, OrderedDict
import logging
import math
import threading
import time

from google.api_core.exceptions import Aborted, FailedPrecondition, GoogleAPICallError

from config.batch_pipeline import (
    MERGE_STALE_HEAD_SECONDS,
    merge_catch_up_depth,
    merge_head_wait_seconds,
    merge_stale_head_skip,
    provider_backlog_release_enabled,
    provider_merge_membership_enabled,
    recovered_merge_release_enabled,
)
from config.policy.kill_switches import kill_switch
from config.record_drain import capture_age_priority
from config.record_latency import record_fresh_merge_enabled
from database import batch_pipeline_allowance_hold as allowance_hold
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_outbox import arm as arm_projection
from database.batch_pipeline_store import Store
from utils.batch_pipeline import backlog_release
from utils.batch_pipeline.result_protocol import merge_markers
from utils.batch_pipeline.held_terminal import held_without_recovery
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.scheduler import owner_key, requeue_due_retry
from utils.batch_pipeline.metrics import QueueMetrics
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# A missing head-wait index falls back to strict order; retry the query after this.
HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS = 300
# Pending fresh rows read per probe (the query cap); an owner rarely has more in flight.
FRESH_PROBE_ROWS = 32
# Ready rows scanned when a blocked record sibling hides independent work.
RECORD_SIBLING_PROBE_ROWS = FRESH_PROBE_ROWS + 128
# Pending rows a stale-head skip reads ahead of its row; more refuses the skip.
STALE_HEAD_PAGE_ROWS = 128
# Per lease-waiting state, the clock that must be 30+ min old: due that long, or a lease
# that expired that long ago. Lease-ending paths reset lease_until to 0, so ready/retry
# rows use available_at. Any other unready state may be about to finish.
_STARVED_CLOCKS = {'ready': 'available_at', 'retry': 'available_at', 'leased': 'lease_until'}
# Content siblings a recovery wake may release with the recovered unit.
RELEASE_SIBLINGS_MAX = 32
# Stale-head promotion (see OrderedMerge._promote_stale_heads).
STALE_HEAD_SWITCH = 'BATCH_PIPELINE_MERGE_STALE_HEAD_PROMOTE_ENABLED'
# Due retry rows one blocked commit promotes; later drains take the rest.
STALE_HEAD_PROMOTE_ROWS = 8
# Process-wide promotion transactions per second, and the burst a quiet process may spend.
STALE_HEAD_PROMOTE_RATE = 2.0
STALE_HEAD_PROMOTE_BURST = 16
# A row is promoted at most this many times; after that recovery and the head wait own it.
STALE_HEAD_PROMOTIONS_PER_ROW = 3
# Owners whose promotion stopped at a bound are continued on later drains: bounded and expiring.
STALE_OWNERS_TRACKED = 1024
STALE_OWNER_TTL_SECONDS = 600.0
_HEAD_STATES = frozenset({'ready', 'leased', 'retry', 'record_pending', 'privacy_blocked'})
_FRESH_FIRST_HEAD_STATES = _HEAD_STATES | {'result_ready'}
_RELEASE_HEAD_STATES = _FRESH_FIRST_HEAD_STATES | {'held'}
# Aged GPU results may cross the depth cap one at a time per owner.
GPU_DEPTH_HOLD_AGE_SECONDS = 6 * 3600
GPU_AGED_RELEASE_INTERVAL_SECONDS = 60
GPU_AGED_RELEASE_SWITCH = 'BATCH_PIPELINE_MERGE_AGED_GPU_RELEASE_ENABLED'
_WAIT_BUCKETS = (60, 120, 300, 600, 1800)


class HeadWaitUnavailable(Exception):
    """The head-wait query has no serving index; the merge keeps strict order."""


class _FreshGateReadError(Exception):
    def __init__(self, error: GoogleAPICallError):
        self.error = error


def _wait_bucket(seconds: float) -> str:
    return next((f'lt{bound}' for bound in _WAIT_BUCKETS if seconds < bound), f'ge{_WAIT_BUCKETS[-1]}')


def _catch_up(job: dict) -> bool:
    # Only rows classified at admission; record-lane and older rows keep the plain order.
    if job.get('fresh_capture') is False:
        return True
    # Provider rows admitted before provider admission stamped the class are backlog by now:
    # without this they would commit in plain order ahead of the owner's fresh rows.
    return (
        job.get('fresh_capture') is None
        and (job.get('stt_route') or {}).get('stt_route') == 'provider'
        and provider_merge_membership_enabled()
    )


def _backlog_held(job: dict) -> bool:
    """A provider backlog row requiring either the metered lane or the legacy hold."""
    # Independent of the membership switch: rows it stamped stay eligible for the head wait
    # after it is turned off, so the hold must outlive it (2026-11-13, 1,700 commits a minute
    # an hour after the switch went off).
    return (
        (job.get('stt_route') or {}).get('stt_route') == 'provider'
        and job.get('fresh_capture') is not True
        and (
            kill_switch('BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED', log=False)
            or not provider_backlog_release_enabled()
        )
    )


def _ready_since(row: dict) -> float | None:
    """When the row became ready. A provider row settled before provider settle stamped
    ``ready_at`` carries a settle instant on its intent."""
    if row.get('ready_at') is not None:
        return row['ready_at']
    if (row.get('stt_route') or {}).get('stt_route') == 'provider' and provider_merge_membership_enabled():
        return (row.get('provider_intent') or {}).get('settled_at')
    return None


def _fresh_pick(rows: list[dict], now: float, wait: float) -> tuple[dict | None, dict | None]:
    """The earliest pending fresh row once ready. If it is not, and a ready fresh
    row has waited ``wait`` behind it, the earliest ready one (the bounded head
    wait among fresh rows; the skipped row appends later as late_capture)."""
    if not rows:
        return None, None
    if rows[0].get('state') == 'result_ready':
        return rows[0], None
    ready = [row for row in rows if row.get('state') == 'result_ready']
    # A provider row settled while the ready_at stamp was off (or had it removed) carries a
    # settle instant on its intent. Reading only ready_at left such rows behind an unready
    # earlier fresh row until ready_at was restored.
    waited = max((now - since for row in ready if (since := _ready_since(row)) is not None), default=None)
    if wait > 0 and waited is not None and waited >= wait:
        earlier = [row['segment_id'] for row in rows[: rows.index(ready[0])]]
        return ready[0], {'segment_ids': earlier, 'state': rows[0].get('state'), 'waited': waited}
    return None, None


def _promotable(row: dict, now: float) -> bool:
    """A due retry whose promotion cannot cycle.

    Worker failures and lease expiries charge an attempt, and an allowance hold parks. An
    admission refusal refunds its attempt (``Scheduler.defer``), so a non-allowance policy
    hold or an unevaluated refusal stays with recovery and the head wait, as before."""
    if row.get('state') != 'retry' or row.get('available_at', math.inf) > now:
        return False
    if row.get('stale_head_promotions', 0) >= STALE_HEAD_PROMOTIONS_PER_ROW:
        return False
    decision = row.get('compute_decision') or {}
    if decision.get('outcome') == 'held':
        return allowance_hold.enabled() and allowance_hold.eligible(row)
    return bool(decision) or not row.get('admission_refusals')


def _aged_priority(job: dict, now: float) -> int:
    """The stored class, lowered by capture age the way record intake classifies (never raised)."""
    age = now - job.get('capture_at', math.nan) - (job.get('duration_seconds') or 0)
    return max(int(job['priority']), int(capture_age_priority(age)))


class _TokenBucket:
    def __init__(self, rate: float, burst: int, clock=time.monotonic):
        self.rate, self.burst, self.clock = rate, float(burst), clock
        self.tokens, self.at = float(burst), clock()
        self.lock = threading.Lock()

    def take(self) -> bool:
        with self.lock:
            now = self.clock()
            self.tokens = min(self.burst, self.tokens + (now - self.at) * self.rate)
            self.at = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True

    def empty(self) -> bool:
        with self.lock:
            return min(self.burst, self.tokens + (self.clock() - self.at) * self.rate) < 1


_PROMOTIONS = _TokenBucket(STALE_HEAD_PROMOTE_RATE, STALE_HEAD_PROMOTE_BURST)


def _awaiting_projection(tx, owner: dict) -> int:
    """Committed rows not yet projected. A missing watermark row never holds a commit."""
    sequence = owner.get('log_sequence', 0)
    projected = owner.get('projection_watermark')
    if not projected:
        return sequence
    done = tx.get('results', projected).get('log_sequence')
    return sequence - done if done else 0


def _record_sibling_pending(tx, job: dict) -> bool:
    """Every merge route preserves the immutable native recording's unit order."""
    if not record_fresh_merge_enabled():
        return False
    return _native_sibling_pending(tx, job)


def _starved(job: dict, now: float) -> bool:
    """Admitted 30+ min ago and waiting 30+ min for a lease: it will not finish within the head wait."""
    state = job.get('state')
    field = _STARVED_CLOCKS.get(state) if isinstance(state, str) else None
    if field is None:
        return False
    for value in (job.get('enqueued_at'), job.get(field)):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or now - value < MERGE_STALE_HEAD_SECONDS:
            return False
    return True


def _only_starved_ahead(tx, key: str, row: dict, now: float) -> bool:
    """Every pending row captured before ``row`` is starved. A full page refuses."""
    position = (row['capture_at'], row['segment_id'])
    for job in tx.pending_page(key, STALE_HEAD_PAGE_ROWS + 1):
        if (job['capture_at'], job['segment_id']) >= position:
            return True
        if not _starved(job, now):
            return False
    return False


def _native_sibling_pending(tx, job: dict) -> bool:
    binding = job.get('projection_binding') or {}
    if binding.get('native_record') is not True:
        return False
    for sibling in binding.get('segment_ids') or ():
        if sibling == job['segment_id']:
            return False
        previous = tx.get('jobs', sibling)
        if previous.get('state') != 'committed' and not held_without_recovery(previous):
            return True
    return True  # An incomplete/malformed binding cannot authorize a bypass.


class OrderedMerge:
    def __init__(
        self,
        store: Store,
        *,
        metrics: QueueMetrics | None = None,
        commit_source: str = 'ordered_merge',
        head_wait_seconds: float | None = None,
        catch_up_depth: int | None = None,
    ):
        self.store = store
        self.metrics = metrics
        self.commit_source = commit_source
        # None reads BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS on every commit.
        self.head_wait_seconds = head_wait_seconds
        # None reads BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH on every commit.
        self.catch_up_depth = catch_up_depth
        self._head_wait_retry_at = 0.0
        self._fresh_first_retry_at = 0.0
        self._fresh_tx_retry_at = 0.0
        # Backoff for a backlog-hold probe alone: it must not switch the depth hold off.
        self._backlog_probe_retry_at = 0.0
        # Owners whose last commit attempt found them at the projection depth
        # cap with rows pending. Maintenance re-offers them by owner: a held
        # backlog can fill the global result_ready page and hide them.
        self.held_owners: set[str] = set()
        self._marked_after: str | None = None
        # Owners whose last promotion stopped at a bound: LRU-capped, entries expire.
        self._stale_owners: OrderedDict[str, float] = OrderedDict()
        self._stale_lock = threading.Lock()

    def _head_wait(self) -> float:
        if time.monotonic() < self._head_wait_retry_at:
            return 0.0
        return self.head_wait_seconds if self.head_wait_seconds is not None else merge_head_wait_seconds()

    def _catch_up_depth(self) -> int:
        if time.monotonic() < self._fresh_first_retry_at:
            return 0
        return self.catch_up_depth if self.catch_up_depth is not None else merge_catch_up_depth()

    def release_hold(self, key: str, *, force: bool = False) -> None:
        """Clear an owner's durable hold marker once it is below the depth cap (or has nothing pending)."""
        depth = self._catch_up_depth()

        def clear(tx):
            mark = tx.get('merge_holds', key)
            if mark.get('held') and (force or not depth or _awaiting_projection(tx, tx.get('owners', key)) < depth):
                tx.put('merge_holds', key, {**mark, 'held': False})

        self.store.run(clear)

    def marked_page(self, limit: int = 50) -> list[tuple[str, str | None]]:
        """The next page of durable hold markers; the cursor rotates so every
        marked owner is reached however many stay held."""
        page = self.store.held_merge_owners(limit, after=self._marked_after)
        self._marked_after = page[-1][0] if len(page) >= limit else None
        return page

    def reoffer_marked(self, drain, limit: int = 50) -> None:
        """Leader maintenance: re-offer owners holding durable markers, which an
        in-memory set loses on restart and the global ready page can hide."""
        for key, owner_id in self.marked_page(limit):
            try:
                if owner_id:
                    drain(owner_id)
                self.release_hold(key, force=not owner_id)
            except Exception as error:
                # One fenced or failing owner must not starve the rest of the page.
                logger.warning(
                    'event=batch_merge action=held_reoffer outcome=retry source=%s exception_type=%s count=1',
                    self.commit_source,
                    type(error).__name__,
                )

    def _head_wait_unavailable(self) -> None:
        self._head_wait_retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
        logger.warning('event=batch_merge outcome=head_wait_unavailable source=%s count=1', self.commit_source)
        record_fallback(
            component='firestore_read',
            from_mode='head_wait',
            to_mode='strict_order',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )
        return None

    def release_set(self, segment_id: str) -> list[str]:
        """The recovered unit first, then its content's other units (bounded).

        A recovery wake passes this to ``commit_next(release=...)``. Only rows
        still pending and ready are ever committed from it."""
        job = self.store.run(lambda tx: tx.get('jobs', segment_id))
        siblings = (job.get('projection_binding') or {}).get('segment_ids') or []
        return [segment_id, *[sid for sid in siblings if sid != segment_id][:RELEASE_SIBLINGS_MAX]]

    def _next_release(self, key: str, release: list[str]) -> str | None:
        """Drop release rows that are not this owner's pending, ready rows; return the first that is."""
        while release:
            segment = release[0]
            job = self.store.run(lambda tx: tx.get('jobs', segment))
            if job.get('owner_key') == key and job.get('merge_pending') and job.get('state') == 'result_ready':
                return segment
            release.pop(0)
        return None

    def _stale_pending(self, owner_id: str) -> bool:
        with self._stale_lock:
            marked = self._stale_owners.get(owner_id)
            if marked is not None and time.monotonic() - marked > STALE_OWNER_TTL_SECONDS:
                del self._stale_owners[owner_id]
                marked = None
            return marked is not None

    def _mark_stale(self, owner_id: str, more: bool) -> None:
        with self._stale_lock:
            self._stale_owners.pop(owner_id, None)
            if more:
                self._stale_owners[owner_id] = time.monotonic()
                while len(self._stale_owners) > STALE_OWNERS_TRACKED:
                    self._stale_owners.popitem(last=False)

    def _promote_stale_heads(self, owner_id: str, stale: dict[str, dict], now: float) -> None:
        """Requeue (or allowance-park) the owner's due retry rows through recovery's transition.

        Recovery requeues due retries oldest-first, 100 per pass. Behind a large
        backlog that runs days late (prod 2026-11-18: 1.07M due retries, the oldest
        94 h overdue), so an owner's retry head held every newer recording in the
        head wait. Each row is re-verified in its own transaction, keeps its
        admission identity and drops to the service class its capture age earns.
        Protected-share eligibility is not consulted: like recovery's ordinary
        oldest-due page this is a plain requeue, and lease admission rechecks it."""
        if _PROMOTIONS.empty():
            # Skip the probe read while the process budget is spent; the owner stays marked.
            self._mark_stale(owner_id, True)
            return
        key = owner_key(owner_id)
        rows = dict(stale)
        try:
            rows.update((row['segment_id'], row) for row in self.store.fresh_pending(key, FRESH_PROBE_ROWS))
        except GoogleAPICallError as error:
            logger.warning(
                'event=batch_merge outcome=stale_head_probe_retry source=%s exception_type=%s count=1',
                self.commit_source,
                type(error).__name__,
            )
        due = sorted(
            (row for row in rows.values() if _promotable(row, now)),
            key=lambda row: (row.get('capture_at', 0), row['segment_id']),
        )
        more = len(due) > STALE_HEAD_PROMOTE_ROWS
        outcomes: Counter = Counter()
        for row in due[:STALE_HEAD_PROMOTE_ROWS]:
            if not _PROMOTIONS.take():
                more = True
                break
            segment_id = row['segment_id']

            def promote(tx, segment_id=segment_id):
                job = tx.get('jobs', segment_id)
                if not job or job.get('owner_key') != key or not job.get('merge_pending') or not _promotable(job, now):
                    return None
                job['stale_head_promotions'] = job.get('stale_head_promotions', 0) + 1
                if (job.get('compute_decision') or {}).get('outcome') == 'held':
                    return 'allowance_parked' if allowance_hold.park(tx, job, now) else None
                return requeue_due_retry(tx, job, now, priority=_aged_priority(job, now))

            try:
                outcome = self.store.run(promote)
            except BatchPrivacyBlocked:
                # Recovery's disposition for the same refusal: privacy cleanup owns the row.
                try:
                    if not self.store.quarantine_fenced(segment_id, now):
                        continue
                    outcome = 'privacy_fenced'
                except Exception as error:
                    logger.warning(
                        'event=batch_merge outcome=stale_head_fence_retry source=%s exception_type=%s count=1',
                        self.commit_source,
                        type(error).__name__,
                    )
                    continue
            except Exception as error:
                # Recovery still owns the row; this only leaves it waiting there.
                logger.warning(
                    'event=batch_merge outcome=stale_head_promote_retry source=%s exception_type=%s count=1',
                    self.commit_source,
                    type(error).__name__,
                )
                continue
            if outcome:
                outcomes[outcome] += 1
                if self.metrics and outcome != 'privacy_fenced':
                    try:
                        self.metrics.record(outcome)
                    except Exception:
                        pass
        self._mark_stale(owner_id, more)
        for outcome, count in outcomes.items():
            logger.info(
                'event=batch_merge outcome=stale_head_promoted action=%s source=%s count=%d',
                outcome,
                self.commit_source,
                count,
            )

    def commit_next(self, owner_id: str, now: float, *, release: list[str] | None = None) -> dict | None:
        """Commit the owner's next result-log row, or return None.

        ``release`` (a recovery wake's ``release_set``, consumed in place):
        when strict order, fresh-first and the head wait commit nothing, the
        first still-pending ready row in it commits at once. Recovered units
        already waited out quarantine and recovery, so the set skips the head
        wait; only the recovered unit also passes the catch-up depth hold. The
        body, late marking and chain are the same as every other commit.

        A due ``retry`` row read at the owner's head is promoted before the
        head wait, so it runs (or parks) now instead of blocking newer rows."""
        key = owner_key(owner_id)
        started = time.monotonic()
        wait = self._head_wait()
        depth = self._catch_up_depth()
        # False while the fresh query is backing off: then nothing probes, and a held
        # backlog stays held instead of falling back to the plain order.
        fresh_query = time.monotonic() >= max(self._fresh_first_retry_at, self._backlog_probe_retry_at)
        blocked: dict = {}
        bypass: dict = {}
        skipped_wait: dict = {}
        fresh_first: dict = {}
        released: dict = {}
        held: dict = {}
        aged_gpu: dict = {}
        head: dict = {}
        # Retry rows read at the owner's strict or fresh head (see _promote_stale_heads).
        stale: dict[str, dict] = {}
        gate = {'determined': True}
        backlog: dict = {}
        metered = kill_switch('BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED', log=False)

        def commit(
            tx,
            waiter: dict | None = None,
            fresh: dict | None = None,
            skipped: dict | None = None,
            exact: str | None = None,
            tx_fresh: bool = False,
            skip_wait: bool = False,
            allow_aged_gpu: bool = False,
        ):
            blocked.clear()  # Firestore may retry this callback.
            backlog.clear()
            bypass.clear()
            skipped_wait.clear()
            fresh_first.clear()
            released.clear()
            held.clear()
            aged_gpu.clear()
            head.clear()
            gate['determined'] = True  # Reset on every transaction retry.
            owner = tx.get('owners', key)
            # Terminal quarantine atomically removes merge_pending; it never
            # enters this success log or the projection predecessor chain.
            candidate = tx.first_pending(key)
            if candidate and candidate.get('shadow'):
                return None
            if candidate and candidate['state'] == 'retry':
                stale[candidate['segment_id']] = candidate
            if candidate and candidate.get('source_alias_fallback') and candidate.get('state') == 'result_ready':
                from database.batch_pipeline_source_fallback import merge_ready

                return merge_ready(tx, candidate, now)
            over_cap = bool(depth and candidate and _awaiting_projection(tx, owner) >= depth)
            if candidate:
                head['catch_up'] = _catch_up(candidate)
                head['backlog'] = _backlog_held(candidate)
            if tx_fresh:
                if not candidate or not (
                    _catch_up(candidate) or _backlog_held(candidate) or candidate['state'] != 'result_ready'
                ):
                    return None
                try:
                    first = tx.fresh_first_pending(key)
                    fresh = tx.fresh_first_ready_pending(key)
                except Aborted:
                    # Contention belongs to the transaction's own retry (or to the caller when
                    # retries are off), never to the gate's read fallback.
                    raise
                except GoogleAPICallError as error:
                    # Only query errors get probe-style handling; commit writes still raise.
                    raise _FreshGateReadError(error) from error
                if first is not None and first['state'] == 'retry':
                    stale[first['segment_id']] = first
                if fresh is None and not (metered and _backlog_held(candidate)):
                    return None
                if fresh is not None and (
                    first is None
                    or first['segment_id'] != fresh['segment_id']
                    or not (_catch_up(candidate) or _backlog_held(candidate))
                ):
                    since = _ready_since(fresh)
                    if since is None:
                        # The probe can measure a later ready row's wait and pick this row.
                        gate['determined'] = False
                        return None
                    if wait <= 0 or now - since < wait:
                        # No committable fresh row; a held backlog head may use its own lane.
                        if not (metered and _backlog_held(candidate)):
                            return None
                        fresh = None
                    else:
                        skipped = {
                            'segment_ids': [],
                            'state': first.get('state') if first else None,
                            'waited': now - since,
                        }
            if exact is not None:
                # Recovered release: the wake's row must still be this owner's
                # pending, ready row. It appends at the tail like any commit;
                # anything it passes appends later, as late_capture if behind.
                current = tx.get('jobs', exact)
                if current.get('shadow'):
                    return None
                if not (
                    current.get('owner_key') == key
                    and current.get('merge_pending')
                    and current.get('state') == 'result_ready'
                ):
                    return None
                if candidate and candidate.get('segment_id') != exact:
                    released['head_state'] = candidate['state']
                else:
                    released['head_state'] = 'held' if over_cap else 'ready'
                # Only the recovered unit itself (it already waited out
                # quarantine and recovery) passes the catch-up depth hold;
                # its content siblings keep it, so a wake cannot pile up to
                # 33 rows past the cap ahead of a later fresh row.
                released['recovered'] = current.get('recovery_state') == 'recovered'
                candidate = current
            elif (
                over_cap
                and waiter is None
                and fresh is None
                # A held backlog head, ready or not, is not a depth hold: no marker, no re-offer.
                and not _backlog_held(candidate)
            ):
                # At the depth cap with rows pending, whatever the head's state:
                # maintenance re-offers this owner, and the durable marker
                # (owner key only) survives a restart.
                held['over_cap'] = True
                if not tx.get('merge_holds', key).get('held'):
                    tx.put('merge_holds', key, {'held': True, 'held_at': now})
            if fresh is not None:
                # Fresh-first (David's fresh bar, 2026-10-20): the selected fresh
                # row must still be pending and ready behind a catch-up head;
                # it commits ahead of that backlog, which appends later as
                # late_capture through the unchanged body below.
                current = tx.get('jobs', fresh['segment_id'])
                if not (
                    candidate
                    and (
                        _catch_up(candidate)
                        or _backlog_held(candidate)
                        or _record_sibling_pending(tx, candidate)
                        or (tx_fresh and candidate['state'] != 'result_ready')
                    )
                    and current.get('merge_pending')
                    and current.get('state') == 'result_ready'
                    and (
                        current.get('fresh_capture') is True
                        or (_record_sibling_pending(tx, candidate) and not over_cap and not _backlog_held(current))
                    )
                ):
                    return None
                if skipped is not None:
                    # Every skipped earlier fresh row must still be unready;
                    # otherwise the next drain commits them in capture order.
                    for earlier in skipped['segment_ids']:
                        row = tx.get('jobs', earlier)
                        if row.get('merge_pending') and row.get('state') == 'result_ready':
                            return None
                    bypass.update(head_state=skipped['state'], waited=skipped['waited'])
                fresh_first.update(head_state=candidate['state'])
                candidate = current
            elif candidate and candidate['state'] != 'result_ready':
                if waiter is None:
                    blocked.update(
                        head_state=candidate['state'], catch_up=_catch_up(candidate), starved=_starved(candidate, now)
                    )
                    return None
                # Bounded head wait (David, 2026-10-20): the probed waiter must
                # still be pending and ready; then release the owner's ready
                # rows in capture order. The bypassed head later appends as
                # late_capture through the unchanged body below.
                current = tx.get('jobs', waiter['segment_id'])
                since = _ready_since(waiter)
                if since is None or not (
                    current.get('merge_pending')
                    and current.get('state') == 'result_ready'
                    and _ready_since(current) == since
                ):
                    return None
                (skipped_wait if skip_wait else bypass).update(head_state=candidate['state'], waited=now - since)
                try:
                    candidate = tx.first_ready_pending(key)
                except FailedPrecondition as error:
                    raise HeadWaitUnavailable from error
                if skip_wait and not (
                    # A native recording unit whose earlier units are settled,
                    # behind nothing but starved rows; anything else keeps the wait.
                    candidate
                    and (candidate.get('projection_binding') or {}).get('native_record') is True
                    and not _native_sibling_pending(tx, candidate)
                    and _only_starved_ahead(tx, key, candidate, now)
                ):
                    return None
            if not candidate or candidate['state'] != 'result_ready':
                return None
            if _record_sibling_pending(tx, candidate):
                blocked.update(
                    head_state='record_sibling',
                    sibling=True,
                    segment_id=candidate['segment_id'],
                    cursor=owner.get('record_sibling_cursor'),
                )
                return None
            if not fresh_first and _backlog_held(candidate):
                # Not a depth hold: no marker, no re-offer. The fresh probe below still runs.
                # A recovered unit is held too: recovery does not make an old capture fresh.
                held['backlog'] = True
                if not (tx_fresh and metered):
                    return None
                # Sample after the gate read on every attempt: its latency, earlier transactions
                # and retries all count toward heartbeat age and reach, using the injected clock.
                read_clock = lambda: now + (time.monotonic() - started)
                token, reason = backlog_release.read(tx, candidate, read_clock, self.commit_source)
                if reason:
                    backlog['refusal'] = reason
                    return None
                if backlog_release.projection_refusal(tx, owner, depth, owner_key=key, owner_id=owner_id):
                    backlog['refusal'] = 'projection'
                    return None
                backlog['token'] = token
            aged_gpu_release = False
            if over_cap and not fresh_first and not released.get('recovered') and _catch_up(candidate):
                # Keep the owner's unprojected log short so a fresh row lands
                # near the projection head.
                route = (candidate.get('stt_route') or {}).get('stt_route')
                if route in (None, 'parakeet'):
                    since = _ready_since(candidate)
                    age_source = 'ready_at' if since is not None else 'enqueued_at'
                    if since is None:
                        since = candidate.get('enqueued_at')
                    if since is not None:
                        held['gpu_age'] = max(0.0, now - since)
                        held['gpu_age_source'] = age_source
                        projection_watermark = owner.get('projection_watermark')
                        prior_release_watermark_present = 'aged_gpu_release_projection_watermark' in owner
                        projection_advanced = not prior_release_watermark_present or projection_watermark != owner.get(
                            'aged_gpu_release_projection_watermark'
                        )
                        held['gpu_release_eligible'] = (
                            held['gpu_age'] >= GPU_DEPTH_HOLD_AGE_SECONDS
                            and kill_switch(GPU_AGED_RELEASE_SWITCH, log=False)
                            and now >= owner.get('next_aged_gpu_release_at', 0)
                            and projection_advanced
                        )
                        aged_gpu_release = allow_aged_gpu and held['gpu_release_eligible']
                if not aged_gpu_release:
                    held['catch_up'] = True
                    return None
            job = tx.get('jobs', candidate['segment_id'])
            markers = merge_markers(job)
            if markers is None:
                return None
            existing = tx.get('results', job['segment_id'])
            if existing:
                raise RuntimeError('result log exists for pending job; reconciliation required')
            watermark = owner.get('watermark')
            position = {'capture_at': job['capture_at'], 'segment_id': job['segment_id']}
            late = bool(
                watermark
                and (position['capture_at'], position['segment_id'])
                <= (watermark['capture_at'], watermark['segment_id'])
            )
            tail = owner.get('log_tail', watermark['segment_id'] if watermark else None)
            entry = {
                **position,
                'protocol_version': job['protocol_version'],
                'owner_key': key,
                'owner_id': job['owner_id'],
                'conversation_id': job.get('conversation_id'),
                'privacy_generation': job.get('privacy_generation'),
                'previous_segment_id': tail,
                'late_capture': late,
                'log_sequence': owner.get('log_sequence', 0) + 1,
                'result': job['result'],
                'committed_at': now,
                'projection_state': 'pending',
                'fresh_capture': job.get('fresh_capture') is True,
            }
            entry.update(markers)
            entry.update(arm_projection(entry, now))
            if job.get('recovery_state') == 'recovered' or (job.get('stt_route') or {}).get('stt_route') == 'provider':
                entry['recovery_version'] = 1
            if bypass:
                entry['head_wait_bypass'] = True
            if fresh_first:
                entry['fresh_first'] = True
            if released:
                entry['recovered_release'] = True
            if backlog.get('token') is not None:
                entry['backlog_release'] = True
                tx.put('backlog_release', 'gate', backlog['token'])
            tx.put('results', job['segment_id'], entry)
            job.update(state='committed', merge_pending=False)
            tx.put('jobs', job['segment_id'], job)
            if aged_gpu_release:
                owner['next_aged_gpu_release_at'] = now + GPU_AGED_RELEASE_INTERVAL_SECONDS
                owner['aged_gpu_release_projection_watermark'] = owner.get('projection_watermark')
                aged_gpu.update(age=held['gpu_age'], age_source=held['gpu_age_source'])
            owner.pop('record_sibling_cursor', None)
            owner.update(
                watermark=watermark if late else position,
                log_tail=job['segment_id'],
                log_sequence=entry['log_sequence'],
                revision=owner.get('revision', 0) + 1,
            )
            tx.put('owners', key, owner)
            return entry

        fenced: BatchPrivacyBlocked | None = None
        try:
            entry = self.store.run(commit)
        except BatchPrivacyBlocked as error:
            entry, fenced = None, error
        strict_blocked, strict_catch_up = dict(blocked), bool(held.get('catch_up'))
        strict_gpu_age = held.get('gpu_age')
        strict_gpu_age_source = held.get('gpu_age_source')
        strict_gpu_eligible = held.get('gpu_release_eligible', False)
        # A held backlog row at or behind the head needs the fresh probe even when the depth
        # hold is switched off: a ready head is refused, and behind an unready one the head
        # wait would pick a held row and commit nothing.
        backlog_probe = fresh_query and bool(
            held.get('backlog') or (head.get('backlog') and (strict_blocked or fenced))
        )
        if held.get('over_cap'):
            self.held_owners.add(owner_id)
        else:
            self.held_owners.discard(owner_id)
        if fenced is not None and not ((depth and head.get('catch_up')) or backlog_probe):
            # A fenced catch-up head must not hide the owner's ready fresh rows;
            # any other fence keeps its strict-order behaviour.
            raise fenced
        depth_probe = bool(depth and (strict_catch_up or strict_blocked.get('catch_up') or fenced))
        sibling_probe = bool(strict_blocked.get('sibling') and fresh_query)
        probe = entry is None and (backlog_probe or depth_probe or sibling_probe)
        if (
            probe
            and not sibling_probe
            and kill_switch('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', log=False)
            and time.monotonic() >= self._fresh_tx_retry_at
        ):
            try:
                entry = self.store.run(lambda tx: commit(tx, tx_fresh=True))
                probe = not gate['determined']
            except _FreshGateReadError as failure:
                if isinstance(failure.error, FailedPrecondition):
                    self._fresh_tx_retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
                    logger.warning(
                        'event=batch_merge outcome=fresh_tx_gate_unavailable source=%s count=1', self.commit_source
                    )
                    record_fallback(
                        component='firestore_read',
                        from_mode='fresh_tx_gate',
                        to_mode='fresh_first',
                        reason='unavailable',
                        outcome='degraded',
                        log=logger,
                    )
                else:
                    logger.warning(
                        'event=batch_merge outcome=fresh_tx_gate_retry source=%s exception_type=%s count=1',
                        self.commit_source,
                        type(failure.error).__name__,
                    )
                    probe = False
            except BatchPrivacyBlocked:
                probe = False
                fresh_first.clear()
                bypass.clear()
        if (
            entry is None
            and (any(_promotable(row, now) for row in stale.values()) or self._stale_pending(owner_id))
            and kill_switch(STALE_HEAD_SWITCH, log=False)
        ):
            self._promote_stale_heads(owner_id, stale, now)
        if probe:
            # A catch-up row heads the owner. Probe for a ready fresh row
            # outside the strict transaction (no transactional query lock);
            # only a ready one opens a second, re-verifying transaction.
            try:
                if sibling_probe:
                    # Existing ready-head query/index, widened only for a blocked group.
                    cursor = strict_blocked.get('cursor') or {}
                    after = (
                        (cursor['capture_at'], cursor['segment_id'])
                        if (cursor.get('head') == strict_blocked['segment_id'])
                        else None
                    )
                    page = self.store.ready_pending(key, RECORD_SIBLING_PROBE_ROWS, after=after)

                    def independent(tx):
                        over_depth = bool(depth and _awaiting_projection(tx, tx.get('owners', key)) >= depth)
                        return [
                            row
                            for row in page
                            if not _record_sibling_pending(tx, row)
                            and not _backlog_held(row)
                            and (row.get('fresh_capture') is True or not over_depth)
                        ]

                    pending = self.store.run(independent)
                    pending.sort(
                        key=lambda row: (row.get('fresh_capture') is not True, row['capture_at'], row['segment_id'])
                    )
                    if not pending:
                        # Persist progress only for a full blocked page. The hint
                        # never authorizes a commit and clears on commit or exhaustion.
                        def remember(tx):
                            tx.check_privacy(owner_id)
                            current = tx.get('owners', key)
                            if len(page) >= RECORD_SIBLING_PROBE_ROWS:
                                current['record_sibling_cursor'] = {
                                    'head': strict_blocked['segment_id'],
                                    'capture_at': page[-1]['capture_at'],
                                    'segment_id': page[-1]['segment_id'],
                                }
                            else:
                                current.pop('record_sibling_cursor', None)
                            tx.put('owners', key, current)

                        self.store.run(remember)
                else:
                    pending = self.store.fresh_pending(key, FRESH_PROBE_ROWS)
            except FailedPrecondition:
                # Without the fresh query a catch-up hold would also hold fresh
                # rows: take the plain order now and retry the query later. A probe made only
                # for a backlog hold backs off on its own clock: the depth hold stays on for
                # every owner, and the held backlog stays held.
                retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
                if depth_probe:
                    self._fresh_first_retry_at = retry_at
                else:
                    self._backlog_probe_retry_at = retry_at
                logger.warning(
                    'event=batch_merge outcome=fresh_first_unavailable source=%s count=1', self.commit_source
                )
                record_fallback(
                    component='firestore_read',
                    from_mode='fresh_first',
                    to_mode='ordered_merge',
                    reason='unavailable',
                    outcome='degraded',
                    log=logger,
                )
                self.held_owners.discard(owner_id)
                return self.commit_next(owner_id, now, release=release)
            except GoogleAPICallError as error:
                # A transient probe read keeps the strict result; the next drain probes again.
                logger.warning(
                    'event=batch_merge outcome=fresh_first_probe_retry source=%s exception_type=%s count=1',
                    self.commit_source,
                    type(error).__name__,
                )
                pending = []
            fresh, skipped = _fresh_pick(pending, now, wait)
            if len(pending) >= FRESH_PROBE_ROWS and not any(row.get('state') == 'result_ready' for row in pending):
                # The probe sees one page. A full page with no ready row may hide ready rows
                # behind it; nothing commits for this owner through the pick until one clears.
                logger.warning(
                    'event=batch_merge outcome=fresh_probe_full_no_ready source=%s count=1', self.commit_source
                )
            if fresh is not None:
                try:
                    entry = self.store.run(lambda tx: commit(tx, fresh=fresh, skipped=skipped))
                except BatchPrivacyBlocked:
                    # A fence on that fresh row refuses only it; the head wait
                    # below still releases the owner's other ready rows.
                    entry = None
                    fresh_first.clear()
                    bypass.clear()
        if entry is None and fenced is not None:
            raise fenced
        if entry is None and release and recovered_merge_release_enabled():
            # Recovery wake: commit the recovered unit (then its content's
            # ready siblings) now instead of after the head wait or the depth
            # hold. Run 18: 46 of 54 wakes advanced no row; held recovered
            # units waited 65-86 s for the head wait plus a maintenance tick.
            segment = self._next_release(key, release)
            if segment is not None:
                try:
                    entry = self.store.run(lambda tx: commit(tx, exact=segment))
                    if entry is not None and entry['segment_id'] == segment:
                        release.pop(0)  # Committed: the next call need not re-read it.
                except BatchPrivacyBlocked:
                    # A fence refuses only this row; strict order commits nothing here.
                    release.pop(0)
                    entry = None
                    released.clear()
        if entry is None and strict_gpu_eligible:
            # Give fresh work and recovery their usual first opportunity. Recheck the
            # capture-order head and the owner's durable cooldown in the commit transaction.
            try:
                entry = self.store.run(lambda tx: commit(tx, allow_aged_gpu=True))
            except BatchPrivacyBlocked:
                return None
        if entry is None and strict_blocked and wait > 0:
            # The strict transaction issues no head-wait query. Probe outside
            # it so a blocked owner takes no extra transactional query lock;
            # only an expired wait opens a second, re-verifying transaction.
            # Every early return below is strict order's result: the head is not ready.
            try:
                waiter = self.store.longest_ready_pending(key)
            except FailedPrecondition:
                return self._head_wait_unavailable()
            except GoogleAPICallError as error:
                # A transient probe read must not fail a drain strict order would finish.
                logger.warning(
                    'event=batch_merge outcome=head_wait_probe_retry source=%s exception_type=%s count=1',
                    self.commit_source,
                    type(error).__name__,
                )
                return None
            if not waiter and provider_merge_membership_enabled():
                # Provider rows settled before the ready_at stamp never match that probe. The
                # owner's earliest ready row stands in; its intent carries when it settled.
                try:
                    waiter = self.store.run(lambda tx: tx.first_ready_pending(key))
                except FailedPrecondition:
                    return self._head_wait_unavailable()
                except GoogleAPICallError as error:
                    logger.warning(
                        'event=batch_merge outcome=head_wait_probe_retry source=%s exception_type=%s count=1',
                        self.commit_source,
                        type(error).__name__,
                    )
                    return None
            since = _ready_since(waiter) if waiter else None
            if since is None:
                return None
            skip_wait = now - since < wait
            if skip_wait and not (strict_blocked.get('starved') and merge_stale_head_skip(owner_id)):
                return None
            try:
                entry = self.store.run(lambda tx: commit(tx, waiter, skip_wait=skip_wait, allow_aged_gpu=True))
            except BatchPrivacyBlocked:
                # An owner-wide fence (often the reason the head is blocked)
                # also refuses the successor; strict order commits nothing here.
                return None
            except HeadWaitUnavailable:
                return self._head_wait_unavailable()
            if entry is None and self.metrics and 'gpu_age' in held:
                self.metrics.gpu_depth_held_age.labels(*self.metrics.scope, held['gpu_age_source']).observe(
                    held['gpu_age']
                )
            if skip_wait and entry is None:
                return None  # A refused skip keeps the ordinary wait: no hold or fallback fires early.
            if held and not held.get('backlog'):
                # The released ready row is catch-up and the owner is at depth.
                self.held_owners.add(owner_id)
            if (
                entry is None
                and held.get('backlog')
                and fresh_query
                and kill_switch('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', log=False)
                and time.monotonic() >= self._fresh_tx_retry_at
            ):
                # An unready fresh/legacy head can hide held provider stock
                # before ready fresh work. The head wait keeps selecting that
                # stock; reselect fresh in one transaction after the same wait.
                try:
                    entry = self.store.run(lambda tx: commit(tx, tx_fresh=True))
                except BatchPrivacyBlocked:
                    return None
                except _FreshGateReadError as failure:
                    if isinstance(failure.error, FailedPrecondition):
                        self._fresh_tx_retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
                        record_fallback(
                            component='firestore_read',
                            from_mode='fresh_tx_gate',
                            to_mode='strict_order',
                            reason='unavailable',
                            outcome='degraded',
                            log=logger,
                        )
                    logger.warning(
                        'event=batch_merge outcome=blocked_fresh_gate_retry source=%s exception_type=%s count=1',
                        self.commit_source,
                        type(failure.error).__name__,
                    )
        if entry is None and self.metrics and strict_gpu_age is not None:
            self.metrics.gpu_depth_held_age.labels(*self.metrics.scope, strict_gpu_age_source).observe(strict_gpu_age)
        if backlog.get('refusal'):
            backlog_release.REFUSED.labels(backlog['refusal']).inc()
        if entry and entry.get('backlog_release'):
            backlog_release.COMMITTED.inc()
            backlog_release.TOKENS_GRANTED.inc()
            backlog_release.TOKENS_USED.set(backlog['token']['tokens_used'])
            backlog_release.WINDOW.set(backlog['token']['window'])
            if key in backlog['token'].get('owner_keys', ()):
                backlog_release.ALLOWLIST_HITS.inc()
        if entry:
            record_correctness('committed', source=self.commit_source)
            if self.metrics:
                self.metrics.record('committed')
                if aged_gpu:
                    self.metrics.gpu_aged_releases.labels(*self.metrics.scope).inc()
                    self.metrics.gpu_aged_release_age.labels(*self.metrics.scope, aged_gpu['age_source']).observe(
                        aged_gpu['age']
                    )
            if fresh_first:
                head_state = (
                    fresh_first['head_state'] if fresh_first['head_state'] in _FRESH_FIRST_HEAD_STATES else 'other'
                )
                logger.info(
                    'event=batch_merge outcome=fresh_first source=%s head_state=%s count=1',
                    self.commit_source,
                    head_state,
                )
            if released:
                head_state = released['head_state'] if released['head_state'] in _RELEASE_HEAD_STATES else 'other'
                logger.info(
                    'event=batch_merge outcome=recovered_release source=%s head_state=%s count=1',
                    self.commit_source,
                    head_state,
                )
            if bypass:
                head_state = bypass['head_state'] if bypass['head_state'] in _HEAD_STATES else 'other'
                logger.info(
                    'event=batch_merge outcome=head_wait_bypass source=%s head_state=%s wait_bucket=%s count=1',
                    self.commit_source,
                    head_state,
                    _wait_bucket(bypass['waited']),
                )
            if skipped_wait:
                head_state = skipped_wait['head_state'] if skipped_wait['head_state'] in _HEAD_STATES else 'other'
                logger.info(
                    'event=batch_merge outcome=stale_head_skip source=%s head_state=%s wait_bucket=%s count=1',
                    self.commit_source,
                    head_state,
                    _wait_bucket(skipped_wait['waited']),
                )
        return entry

    def committed_result(self, segment_id: str) -> dict:
        """Idempotent re-read after a lost commit reply; no external side effects."""
        return self.store.run(lambda tx: tx.get('results', segment_id))
