"""Queue-age autoscaling export. Refresh from a supervised worker, never import IO."""

import logging
import math
import threading
import time

from config.firestore_read_levers import lever_enabled
from config.policy.kill_switches import kill_switch

from prometheus_client import CollectorRegistry, Gauge, Histogram, Counter, REGISTRY

from config.batch_timeliness import (
    SLA_SECONDS,
    TERMINAL_EMPTY_IS_PROCESSED,
    batch_timeliness_alarm_enabled,
    timeliness_epoch,
    timeliness_interval_seconds,
)
from database.batch_pipeline_store import (
    Store,
    FirestoreStore,
    PROJECTION_OBLIGATION_STATES,
    timeliness_all_time_counts,
    timeliness_sample,
)
from utils.batch_pipeline.leader import TIMELINESS_LEASE_GRACE_SECONDS, TIMELINESS_METRICS, LeaderLease
from utils.batch_pipeline.contracts import Priority, WORK_OUTCOMES
from utils.observability.reasons import AdmissionHoldReason, ReasonFamily, reason_label
from utils.lifecycle_metrics import PhaseMetrics
from utils.batch_pipeline import vendor_route_metrics as vendor_metrics
from utils.batch_pipeline.fresh_guard import FreshGuard
from utils.batch_pipeline.delivered_share import DeliveredShare

PROJECTION_FINISH_READS = Counter(
    'omi_batch_projection_finish_reads_total',
    'Finish-page rows read by the projection sweep',
)
PROJECTION_FINISH_COMPLETED = Counter(
    'omi_batch_projection_finish_completed_total',
    'Finish-page rows completed by the projection sweep',
)
PROJECTION_DRAIN_CLAIM_HELD = Counter(
    'omi_batch_projection_drains_skipped_total', 'Owner drain admissions deferred because the fleet claim is held'
)
PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS = Counter(
    'omi_batch_projection_claim_busy_backoffs_total', 'Owner drain turns deferred after losing the fleet claim race'
)

PROJECTION_DRAIN_PRIVACY_STOPS = Counter(
    'omi_batch_projection_privacy_blocked_stops_total',
    'Owner drain turns stopped by privacy, with bounded reasons',
    ['reason'],
)
PROJECTION_DRAIN_PRIVACY_BACKOFFS = Counter(
    'omi_batch_projection_privacy_backoffs_total', 'Zero-progress privacy owner drain backoffs applied'
)
PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS = Counter(
    'omi_batch_projection_live_target_backoffs_total', 'Zero-progress awaiting-live-target owner drain backoffs applied'
)
PROJECTION_DRAIN_PRIVACY_ROW_CHANGED = Counter(
    'omi_batch_projection_privacy_row_changed_total', 'Early owner re-requests after a blocked head row changes'
)


PROJECTION_PRIVACY_RESUMES_ATTEMPTED = Counter(
    'omi_batch_projection_privacy_resumes_attempted_total', 'Fenced privacy refusal replays attempted'
)
PROJECTION_PRIVACY_RESUMES_SUCCEEDED = Counter(
    'omi_batch_projection_privacy_resumes_succeeded_total', 'Fenced privacy refusal replays completed'
)
PROJECTION_PRIVACY_FALLTHROUGHS = Counter(
    'omi_batch_projection_privacy_fallthroughs_total', 'Stale privacy refusals retried without a stored refusal'
)
PROJECTION_PRIVACY_STILL_REFUSED = Counter(
    'omi_batch_projection_privacy_still_refused_total', 'Applicable privacy refusals held, including unchanged holds'
)


RECORD_SEAL_ORPHAN_PARKED = Counter(
    'omi_record_seal_orphan_parked_total',
    'Seal passes observing a parked restore obligation on a discarded row',
    ['seal_path'],
)


def record_privacy_stop(stop: str) -> None:
    PROJECTION_DRAIN_PRIVACY_STOPS.labels(
        reason=(
            'tombstone'
            if stop == 'blocked_privacy_disposition_requires_a_source_deletion_tombstone'
            else ('refusal_no_longer_applies' if stop == 'blocked_privacy_refusal_no_longer_applies' else 'other')
        )
    ).inc()


# Per tick: eight count aggregations (one read per 1,000 index entries, minimum one each) and three head reads.
VENDOR_HELD_REFRESH_SECONDS = 300.0

LABELS = {Priority.FRESH: 'fresh', Priority.RECENT: 'recent', Priority.DEEP: 'deep'}
AGE_TARGETS = {Priority.FRESH: 30, Priority.RECENT: 300, Priority.DEEP: 3600}
PARK_REASONS = frozenset({'privacy', 'pool_duration', 'pool_unit_kind', 'shared_live_policy'})


def age_seconds(started: float | None, now: float) -> float:
    # Preserve an explicitly incomplete bounded scan as NaN. max(0, NaN)
    # would silently turn unknown debt into a healthy zero.
    if started is None:
        return 0
    return max(0.0, now - started) if math.isfinite(started) else float('nan')


QUEUE_SAMPLE_FRESH_SECONDS = 60.0


class _FreshQueueGauge(Gauge):
    """Expire fleet samples at collection even if their supervised refresh stops."""

    def __init__(self, *args, fresh=None, **kwargs):
        self._fresh = fresh
        super().__init__(*args, **kwargs)

    def collect(self):
        if self._fresh is None or self._fresh():
            yield from super().collect()


class QueueMetrics:
    def __init__(
        self,
        registry: CollectorRegistry = REGISTRY,
        *,
        worker_release: str = 'unscoped',
        namespace: str = 'unscoped',
        capacity_sampling: bool = False,
        min_refresh_seconds: float = 0.0,
        oldest_leader=None,
        timeliness_leader=None,
        oldest_min_refresh_seconds: float = 0.0,
    ):
        self.timeliness_leader = timeliness_leader
        self.fresh_guard = FreshGuard(registry)
        self.delivered_share = DeliveredShare(registry)
        self._timeliness_lock = threading.Lock()
        self._timeliness_all_time_visible = False
        self._timeliness_visible = False
        self._timeliness_expires = 0.0
        self.scope = (worker_release, namespace)
        self.oldest_leader = oldest_leader
        self.oldest_min_refresh_seconds = oldest_min_refresh_seconds
        self._oldest_due = 0.0
        self._held_due = 0.0
        self._provider_observed = None
        self._oldest_lock = threading.Lock()
        self._oldest_observed = None
        self._capacity_observed = None
        self.held_expired = Counter(
            'omi_batch_held_expired_total',
            'Unique fenced held expirations across jobs and projection receipts; content retained',
            registry=registry,
        )
        self.held_expired_stock = Gauge(
            'omi_batch_held_expired_units',
            'Retained held_expired job and projection receipt stock across all ages',
            registry=registry,
        )
        self.held_expired_observed_at = Gauge(
            'omi_batch_held_expired_observed_at_seconds', 'Last successful held-expired stock sample', registry=registry
        )
        self.record_dead_letter = Counter(
            'omi_batch_record_dead_letter_total',
            'Committed record barrier aged dead letters; custody retained',
            registry=registry,
        )
        self.record_dead_letter_stock = Gauge(
            'omi_batch_record_dead_letter_units',
            'Retained record_barrier_aged job stock',
            registry=registry,
        )
        self.record_dead_letter_observed_at = Gauge(
            'omi_batch_record_dead_letter_observed_at_seconds',
            'Last successful record dead-letter stock sample',
            registry=registry,
        )
        # Serving instances share one global queue; workers keep 0 for the HPA.
        self.min_refresh_seconds = min_refresh_seconds
        self._refresh_due = 0.0
        self._refresh_lock = threading.Lock()
        self.capacity_sampling = capacity_sampling
        self.projection_pump_last_tick = Gauge(
            'omi_batch_projection_pump_last_tick_seconds',
            'Unix timestamp of the last completed projection pump tick, including failed ticks; zero before first tick',
            registry=registry,
        )
        self.projection_pump_last_success = Gauge(
            'omi_batch_projection_pump_last_success_seconds',
            'Unix timestamp of the last successful projection pump tick; zero before first success',
            registry=registry,
        )
        self.projection_age = Gauge(
            'omi_batch_projection_obligation_oldest_age_seconds',
            'Oldest unfinished committed projection age, including held content; alarm above 900s',
            registry=registry,
        )
        self.projection_observed_at = Gauge(
            'omi_batch_projection_obligation_observed_at_seconds',
            'Last successful oldest projection obligation observation',
            registry=registry,
        )
        # 2-hour timeliness alarm (David, 2026-11-02). Alert-only: no scheduler, ramp or rollback guard reads it.
        self.timeliness_age = _FreshQueueGauge(
            'omi_batch_timeliness_new_oldest_age_seconds',
            'Oldest unpublished unit admitted (projection legs: committed) at or after the epoch; alarm above 7200s',
            ['leg'],
            registry=registry,
            fresh=self._timeliness_sample_visible,
        )
        self.drain_age = _FreshQueueGauge(
            'omi_batch_projection_drain_oldest_age_seconds',
            'Oldest runnable projection age across all epochs; excludes quarantine_held; alert-only',
            registry=registry,
            fresh=self._timeliness_sample_visible,
        )
        self.held_age = _FreshQueueGauge(
            'omi_batch_held_oldest_age_seconds',
            'Oldest held row age without an epoch or rolling cohort cutoff; alert-only',
            ['leg'],
            registry=registry,
            fresh=self._timeliness_sample_visible,
        )
        self.staged_input_clock_invalid = Counter(
            'omi_batch_staged_input_clock_invalid_total',
            'Malformed clock observations in bounded held pages and age samples; repeated observations count again',
            registry=registry,
        )
        self.timeliness_over_sla = _FreshQueueGauge(
            'omi_batch_timeliness_new_over_sla_units',
            'Units admitted at or after the epoch and still unpublished past the 2h SLA, by counted leg',
            ['leg'],
            registry=registry,
            fresh=self._timeliness_sample_visible,
        )
        self.timeliness_all_time = _FreshQueueGauge(
            'omi_batch_timeliness_all_time_units',
            'Unpublished stock across all epochs and ages; exact aggregate counts by projection hold leg',
            ['leg'],
            registry=registry,
            fresh=lambda: self._timeliness_sample_visible()
            and self._timeliness_all_time_visible
            and kill_switch('BATCH_TIMELINESS_ALL_TIME_COUNTS_ENABLED', log=False),
        )
        self.timeliness_backlog = _FreshQueueGauge(
            'omi_batch_timeliness_backlog_units',
            'Pre-epoch unpublished units by leg; capped at 10000 (lower bound) with batch_timeliness_leader',
            ['leg'],
            registry=registry,
            fresh=self._timeliness_sample_visible,
        )
        self.timeliness_truncated = _FreshQueueGauge(
            'omi_batch_timeliness_scan_truncated',
            '1 when a leg\'s bounded walk or unusable clock may hide an older unpublished unit',
            ['leg'],
            registry=registry,
            fresh=self._timeliness_sample_visible,
        )
        self.timeliness_observed_at = _FreshQueueGauge(
            'omi_batch_timeliness_observed_at_seconds',
            'Last successful timeliness sample',
            registry=registry,
            fresh=self._timeliness_sample_visible,
        )
        self.timeliness_samples = Counter(
            'omi_batch_timeliness_samples_total',
            'Timeliness sample attempts by outcome',
            ['outcome'],
            registry=registry,
        )
        self._timeliness_due = 0.0
        self.record_pending = PhaseMetrics('omi_batch_record_pending', ['state'], registry=registry)
        self.nojob = PhaseMetrics('omi_record_seal_nojob', ['kind'], registry=registry)
        self.oldest_age = _FreshQueueGauge(
            'omi_batch_pipeline_oldest_age_seconds',
            'Oldest admitted uncommitted item age',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
            fresh=lambda: self._sample_fresh(self._oldest_observed),
        )
        self.ready_age = _FreshQueueGauge(
            'omi_batch_pipeline_ready_age_seconds',
            'Oldest item ready for GPU capacity',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
            fresh=lambda: self._sample_fresh(self._oldest_observed),
        )
        self.retry_age = _FreshQueueGauge(
            'omi_batch_pipeline_retry_age_seconds',
            'Age since first compute failure; alert above 600 seconds',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
            fresh=lambda: self._sample_fresh(self._oldest_observed),
        )
        self.sampler_observed_at = Gauge(
            'omi_batch_pipeline_sampler_observed_at_seconds',
            'Last successful per-instance sampler tick, independent of fleet queue-query cadence',
            ['worker_release', 'namespace'],
            registry=registry,
        )
        self.refreshed_at = _FreshQueueGauge(
            'omi_batch_pipeline_metrics_refreshed_at_seconds',
            'Last complete queue sample timestamp',
            ['worker_release', 'namespace'],
            registry=registry,
            fresh=lambda: self._sample_fresh(self._oldest_observed),
        )
        self.provider_stage_units = _FreshQueueGauge(
            'omi_batch_pipeline_provider_stage_units',
            'Provider-STT stage stock by state (provider_pending, provider_running); capped at 1e6',
            ['state', 'worker_release', 'namespace'],
            registry=registry,
            fresh=lambda: self._provider_fresh(),
        )
        self.provider_stage_oldest_age = _FreshQueueGauge(
            'omi_batch_pipeline_provider_stage_oldest_age_seconds',
            'Oldest provider-STT stage row age by state, all epochs; no paging rule reads it',
            ['state', 'worker_release', 'namespace'],
            registry=registry,
            fresh=lambda: self._provider_fresh(),
        )
        self.ready_units = _FreshQueueGauge(
            'omi_batch_pipeline_admissible_ready_units',
            'Ready admitted units excluding held, parked, unmarked legacy and unevaluated refusals',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
            fresh=lambda: self._sample_fresh(self._capacity_observed),
        )
        self.capacity_refreshed_at = _FreshQueueGauge(
            'omi_batch_pipeline_capacity_refreshed_at_seconds',
            'Last complete three-priority admissible capacity count',
            ['worker_release', 'namespace'],
            registry=registry,
            fresh=lambda: self._sample_fresh(self._capacity_observed),
        )
        self.owner_wait = Histogram(
            'omi_batch_pipeline_owner_wait_seconds',
            'Per-item admission to lease wait; no owner labels; relet="true" is a re-lease, not fresh wait',
            ['relet'],
            buckets=(1, 10, 30, 60, 300, 3600, 43200, 86400, 604800),
            registry=registry,
        )
        self.events = Counter(
            'omi_batch_pipeline_events_total',
            'Worker transition receipts; jobs/s is rate of completed events',
            ['event'],
            registry=registry,
        )
        self.admission_hold_reasons = Counter(
            'omi_batch_pipeline_admission_hold_reasons_total',
            'Evaluated compute-admission hold reasons on policy defers; bounded enum, unknown folds to unknown',
            ['reason'],
            registry=registry,
        )
        self.completed_audio = Counter(
            'omi_batch_pipeline_completed_audio_seconds_total',
            'Capture audio seconds at unique fenced completion, including silence',
            ['outcome'],
            registry=registry,
        )

        self.head_not_found = Counter(
            'omi_batch_pipeline_head_not_found_total',
            'Capture head or unique ready FIFO predecessor not found',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
        )
        self.head_budget_exhausted = Counter(
            'omi_batch_pipeline_head_budget_exhausted_total',
            'Owner head lookup budget exhausted in a pull transaction',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
        )
        self.predecessor_ready_age = Histogram(
            'omi_batch_pipeline_predecessor_ready_age_seconds',
            'Capture-order head ready age at scheduler visit',
            ['priority', 'worker_release', 'namespace'],
            buckets=(1, 10, 30, 60, 120, 300, 600, 900, 3600, 86400),
            registry=registry,
        )
        self.head_parked = Counter(
            'omi_batch_pipeline_head_parked_total',
            'Owner queue visits parked behind an unleasable head, by bounded reason',
            ['priority', 'reason', 'worker_release', 'namespace'],
            registry=registry,
        )

    def record_head(self, event: str, priority: Priority, *, age: float | None = None) -> None:
        if event == 'ready_age' and age is not None:
            self.predecessor_ready_age.labels(LABELS[priority], *self.scope).observe(age)
        elif event.startswith('parked_') and event[len('parked_') :] in PARK_REASONS:
            self.head_parked.labels(LABELS[priority], event[len('parked_') :], *self.scope).inc()
        elif event == 'head_not_found':
            self.head_not_found.labels(LABELS[priority], *self.scope).inc()
        elif event == 'budget_exhausted':
            self.head_budget_exhausted.labels(LABELS[priority], *self.scope).inc()
        else:
            raise ValueError('static head scheduling event required')

    def refresh(self, store: Store, now: float) -> None:
        if self.min_refresh_seconds <= 0:
            self._refresh(store, now)
            return
        # The serving loop and the /metrics handler share this object across
        # executors: reserve the interval before reading so concurrent callers
        # skip. A skipped call reads nothing and changes nothing; a failed
        # refresh releases its reservation so the next call reads again.
        due = now + self.min_refresh_seconds
        with self._refresh_lock:
            if now < self._refresh_due:
                return
            previous, self._refresh_due = self._refresh_due, due
        try:
            self._refresh(store, now)
        except BaseException:
            with self._refresh_lock:
                if self._refresh_due == due:
                    self._refresh_due = previous
            raise

    def _sample_fresh(self, observed: float | None) -> bool:
        return not lever_enabled('batch_metrics_oldest_leader') or (
            observed is not None and time.monotonic() - observed < QUEUE_SAMPLE_FRESH_SECONDS
        )

    def _forget_queue_sample(self) -> None:
        # Remove only this process's labelled children. A follower never writes
        # a synthetic zero, and cannot change another process's leader sample.
        for gauge in (
            self.oldest_age,
            self.ready_age,
            self.retry_age,
            self.ready_units,
            self.refreshed_at,
            self.capacity_refreshed_at,
        ):
            gauge.clear()
        # The held gauges live in the vendor-route module: a former leader must not keep exporting
        # its last stock. Zero is a floor under max(), never a fleet claim.
        vendor_metrics.HELD_UNITS.clear()
        vendor_metrics.HELD_OLDEST_AGE.set(0)
        self._held_due = 0.0
        self._provider_observed = None
        self._oldest_observed = self._capacity_observed = None

    def _refresh(self, store: Store, now: float) -> None:
        elected = lever_enabled('batch_metrics_oldest_leader')
        # The old serving reservation still bounds all its other samplers.
        # This independent reservation affects only fleet queue queries.
        with self._oldest_lock:
            if not elected or now >= self._oldest_due:
                if elected and self.oldest_leader is not None and not self.oldest_leader.acquire():
                    self._forget_queue_sample()
                else:
                    self._refresh_queue(store, now)
                self._oldest_due = now + self.oldest_min_refresh_seconds
        # Timeliness elects its own fleet role on serving and worker planes;
        # lifecycle and projection keep their existing per-instance schedules.
        if isinstance(store, FirestoreStore):
            from database.lifecycle_metrics_queries import record_pending, nojob

            self.record_pending.refresh(now, lambda: record_pending(store.client, store.namespace, now))
            self.nojob.refresh(now, lambda: nojob(store.client, store.namespace))
            self.refresh_timeliness(store, now)
            self.refresh_projection(store, now)
        self.sampler_observed_at.labels(*self.scope).set(now)

    def _refresh_queue(self, store: Store, now: float) -> None:
        observed = time.monotonic()
        # Collect every query before changing gauges. Failed refresh retains last
        # values and does not advance freshness; adapters must reject stale data.
        samples = []
        for priority in Priority:
            pending = store.oldest(int(priority), ready_only=False)
            ready = store.oldest(int(priority), ready_only=True)
            samples.append((priority, pending, ready, store.oldest_retry(int(priority))))
        capacity = []
        # Older injected stores may expose only the age contract. Their absent
        # capacity clock stays never-observed, so no adapter can fabricate zero.
        sampler = getattr(store, 'ready_for_capacity', None)
        if self.capacity_sampling and callable(sampler):
            try:
                for priority in Priority:
                    count = sampler(int(priority), now)
                    if type(count) is not int or count < 0:
                        raise ValueError('nonnegative integer capacity count required')
                    capacity.append((priority, count))
            except Exception as error:
                # Freeze this independent scaling signal without failing an
                # otherwise successful recovery/projection request. Publish no
                # partial counts and never advance its freshness on failure.
                capacity = []
                logging.getLogger(__name__).warning(
                    'event=batch_capacity_sample outcome=unavailable exception_type=%s', type(error).__name__
                )
        for priority, pending, ready, retry in samples:
            self.oldest_age.labels(LABELS[priority], *self.scope).set(age_seconds(pending, now))
            self.ready_age.labels(LABELS[priority], *self.scope).set(max(0.0, now - ready) if ready is not None else 0)
            self.retry_age.labels(LABELS[priority], *self.scope).set(age_seconds(retry, now))
        self.refreshed_at.labels(*self.scope).set(now)
        self._oldest_observed = observed
        if capacity:
            for priority, count in capacity:
                self.ready_units.labels(LABELS[priority], *self.scope).set(count)
            self.capacity_refreshed_at.labels(*self.scope).set(now)
            self._capacity_observed = observed
        self._refresh_vendor_held(store, now)

    def _refresh_vendor_held(self, store: Store, now: float) -> None:
        """Feed ``vendor_route_metrics.held_units``, which had no producer: the gauges read 0 over a real stock.

        Runs on the queue sampler's (leader-elected) path, at most every VENDOR_HELD_REFRESH_SECONDS.
        A failed read keeps the last values; it never publishes a synthetic zero.
        """
        if not isinstance(store, FirestoreStore) or now < self._held_due:
            return
        self._held_due = now + VENDOR_HELD_REFRESH_SECONDS
        from database.lifecycle_metrics_queries import vendor_held

        try:
            counts, age, truncated = vendor_held(store.client, store.namespace, now)
        except Exception as error:
            logging.getLogger(__name__).warning(
                'event=batch_vendor_held_sample outcome=unavailable exception_type=%s', type(error).__name__
            )
        else:
            vendor_metrics.held_units(counts, age)
            if truncated:
                # Counts at the cap are lower bounds; the frozen held collectors carry no truncation label.
                logging.getLogger(__name__).warning('event=batch_vendor_held_sample outcome=truncated')
        # Independent of the held sample: provider_pending has no other stock signal.
        from database.lifecycle_metrics_queries import provider_stage

        try:
            stage = provider_stage(store.client, store.namespace, now)
        except Exception as error:
            logging.getLogger(__name__).warning(
                'event=batch_provider_stage_sample outcome=unavailable exception_type=%s', type(error).__name__
            )
            return
        for state, (count, oldest_age) in stage.items():
            self.provider_stage_units.labels(state, *self.scope).set(count)
            self.provider_stage_oldest_age.labels(state, *self.scope).set(oldest_age)
        self._provider_observed = time.monotonic()

    def _provider_fresh(self) -> bool:
        # Two missed ticks expire the sample; a follower that lost the lease stops exporting it.
        observed = self._provider_observed
        return observed is not None and time.monotonic() - observed < 2 * VENDOR_HELD_REFRESH_SECONDS + 60

    def _timeliness_sample_visible(self) -> bool:
        # A stalled replica must not combine its old breach with another
        # replica's fresh timestamp in max-based alerts. Expire at collection
        # in every election mode, including rollback to per-instance sampling.
        return self._timeliness_visible and time.monotonic() < self._timeliness_expires

    def refresh_timeliness(self, store: FirestoreStore, now: float) -> None:
        """One fleet sample per interval; errors preserve the last successful timestamp."""
        with self._timeliness_lock:
            self._refresh_timeliness(store, now)

    def _refresh_timeliness(self, store: FirestoreStore, now: float) -> None:
        if now < self._timeliness_due:
            return
        interval = timeliness_interval_seconds()
        self._timeliness_due = now + interval
        if not batch_timeliness_alarm_enabled():
            self.timeliness_samples.labels('disabled').inc()
            return
        elected = lever_enabled('batch_timeliness_leader')
        lease_seconds = interval + TIMELINESS_LEASE_GRACE_SECONDS
        sample_expires = time.monotonic() + lease_seconds
        if elected:
            if self.timeliness_leader is None:
                # Lazy and shared by both planes, using the data namespace, not
                # pod/release identity. No import-time or disabled-path IO.
                self.timeliness_leader = LeaderLease(store, TIMELINESS_METRICS, ttl_seconds=lease_seconds)
            self.timeliness_leader.ttl_seconds = lease_seconds
            if not self.timeliness_leader.acquire():
                # Retry through the incumbent's refresh grace without waiting
                # another full sample interval after it stops. Followers do
                # at most one lease check per minute and never sample on loss.
                self._timeliness_due = now + min(interval, TIMELINESS_LEASE_GRACE_SECONDS)
                self._timeliness_visible = False
                return
        # Companion counts need leader mode and this replica's lease, so a fleet
        # never runs them on every replica. Election off means no companion counts.
        all_time_counts = elected and kill_switch('BATCH_TIMELINESS_ALL_TIME_COUNTS_ENABLED', log=False)
        try:
            sample = timeliness_sample(
                store.client,
                store.namespace,
                timeliness_epoch(),
                now,
                SLA_SECONDS,
                terminal_empty_processed=TERMINAL_EMPTY_IS_PROCESSED,
            )
        except Exception as error:
            self.timeliness_samples.labels('error').inc()
            logging.getLogger(__name__).warning(
                'event=batch_timeliness_sample outcome=unavailable exception_type=%s', type(error).__name__
            )
            return
        self.staged_input_clock_invalid.inc(sample.get('staged_input_clock_invalid', 0))
        self.drain_age.set(age_seconds(sample['drain_oldest'], now))
        for leg, started in sample['held_oldest'].items():
            self.held_age.labels(leg).set(age_seconds(started, now))
        for leg, started in sample['new_oldest'].items():
            self.timeliness_age.labels(leg).set(max(0.0, now - started) if started is not None else 0)
        for leg, units in sample['new_over_sla'].items():
            self.timeliness_over_sla.labels(leg).set(units)
        for leg, units in sample['backlog'].items():
            self.timeliness_backlog.labels(leg).set(units)
        for leg, truncated in sample['truncated'].items():
            self.timeliness_truncated.labels(leg).set(1 if truncated else 0)
        self.timeliness_observed_at.set(now)
        # Only a successful sample extends visibility, including with election
        # disabled. A lease renewal/fail-open result alone cannot revive debt.
        self._timeliness_expires = sample_expires
        self._timeliness_visible = True
        self.timeliness_samples.labels('ok').inc()
        # Companion counts run only after the epoch gauges above are published,
        # so a slow or failed COUNT can never delay or stale the epoch series.
        if all_time_counts:
            self._refresh_all_time(store)
        else:
            self._timeliness_all_time_visible = False

    def _refresh_all_time(self, store: FirestoreStore) -> None:
        try:
            counts = timeliness_all_time_counts(store.client, store.namespace)
        except Exception as error:
            logging.getLogger(__name__).warning(
                'event=batch_timeliness_all_time_sample outcome=unavailable exception_type=%s', type(error).__name__
            )
            counts = {}
        # A failed leg must disappear, including a value from the previous refresh;
        # it cannot become a fake zero or stay stale.
        self.timeliness_all_time.clear()
        for leg, units in counts.items():
            self.timeliness_all_time.labels(leg).set(units)
        self._timeliness_all_time_visible = bool(counts)

    def refresh_projection(self, store: FirestoreStore, now: float) -> None:
        # Reuses the indexed discovery shape, one row, including durable holds.
        # A failed query/read leaves freshness unchanged; never exports false zero.
        ids, _ = store.projection_page(limit=1, states=PROJECTION_OBLIGATION_STATES)
        age = 0.0
        if ids:
            row = store.client.collection(f'{store.namespace}_results').document(ids[0]).get().to_dict()
            if row is None:  # concurrent privacy erase; retry next supervised tick
                return
            age = max(0.0, now - row['committed_at'])
        self.projection_age.set(age)
        self.projection_observed_at.set(now)

    def record(
        self,
        event: str,
        *,
        wait_seconds: float | None = None,
        relet: bool = False,
        reason: str | None = None,
    ) -> None:
        if event not in {
            'leased',
            'completed',
            'retry',
            'requeued',
            'lease_expired',
            'dead',
            'committed',
            'quarantined',
            'recovery_held',
            'admission_policy_deferred',
            'admission_unevaluated_deferred',
        }:
            raise ValueError('metric event must be a static worker transition')
        self.events.labels(event).inc()
        if event == 'leased' and wait_seconds is not None:
            self.owner_wait.labels('true' if relet else 'false').observe(max(0.0, wait_seconds))
        if event == 'admission_policy_deferred' and reason:
            self.admission_hold_reasons.labels(
                reason=reason_label(ReasonFamily.ADMISSION_HOLD, reason, AdmissionHoldReason)
            ).inc()

    def record_completed_audio(self, outcome: str, seconds: float) -> None:
        if outcome not in WORK_OUTCOMES:
            raise ValueError('invalid completion outcome')
        self.completed_audio.labels(outcome).inc(seconds)
