"""Queue-age autoscaling export. Refresh from a supervised worker, never import IO."""

import logging
import math
import threading

from prometheus_client import CollectorRegistry, Gauge, Histogram, Counter, REGISTRY

from config.batch_timeliness import (
    SLA_SECONDS,
    TERMINAL_EMPTY_IS_PROCESSED,
    batch_timeliness_alarm_enabled,
    timeliness_epoch,
    timeliness_interval_seconds,
)
from database.batch_pipeline_store import Store, FirestoreStore, PROJECTION_OBLIGATION_STATES, timeliness_sample
from utils.batch_pipeline.contracts import Priority, WORK_OUTCOMES
from utils.observability.reasons import AdmissionHoldReason, ReasonFamily, reason_label
from utils.lifecycle_metrics import PhaseMetrics

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
PROJECTION_DRAIN_PRIVACY_ROW_CHANGED = Counter(
    'omi_batch_projection_privacy_row_changed_total', 'Early owner re-requests after a blocked head row changes'
)


def privacy_stop_reason(stop: str) -> str:
    if stop == 'blocked_privacy_disposition_requires_a_source_deletion_tombstone':
        return 'tombstone'
    if stop == 'blocked_privacy_refusal_no_longer_applies':
        return 'refusal_no_longer_applies'
    return 'other'


LABELS = {Priority.FRESH: 'fresh', Priority.RECENT: 'recent', Priority.DEEP: 'deep'}
AGE_TARGETS = {Priority.FRESH: 30, Priority.RECENT: 300, Priority.DEEP: 3600}
PARK_REASONS = frozenset({'privacy', 'pool_duration', 'pool_unit_kind', 'shared_live_policy'})


def age_seconds(started: float | None, now: float) -> float:
    # Preserve an explicitly incomplete bounded scan as NaN. max(0, NaN)
    # would silently turn unknown debt into a healthy zero.
    if started is None:
        return 0
    return max(0.0, now - started) if math.isfinite(started) else float('nan')


class QueueMetrics:
    def __init__(
        self,
        registry: CollectorRegistry = REGISTRY,
        *,
        worker_release: str = 'unscoped',
        namespace: str = 'unscoped',
        capacity_sampling: bool = False,
        min_refresh_seconds: float = 0.0,
    ):
        self.scope = (worker_release, namespace)
        self.held_expired = Counter(
            'omi_batch_held_expired_total', 'Unique fenced held-to-dead transitions; audio retained', registry=registry
        )
        self.held_expired_stock = Gauge(
            'omi_batch_held_expired_units', 'Retained dead(held_expired) stock across all ages', registry=registry
        )
        self.held_expired_observed_at = Gauge(
            'omi_batch_held_expired_observed_at_seconds', 'Last successful held-expired stock sample', registry=registry
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
        self.timeliness_age = Gauge(
            'omi_batch_timeliness_new_oldest_age_seconds',
            'Oldest unpublished unit admitted (projection legs: committed) at or after the epoch; alarm above 7200s',
            ['leg'],
            registry=registry,
        )
        self.drain_age = Gauge(
            'omi_batch_projection_drain_oldest_age_seconds',
            'Oldest runnable projection age across all epochs; excludes quarantine_held; alert-only',
            registry=registry,
        )
        self.held_age = Gauge(
            'omi_batch_held_oldest_age_seconds',
            'Oldest held row age without an epoch or rolling cohort cutoff; alert-only',
            ['leg'],
            registry=registry,
        )
        self.timeliness_over_sla = Gauge(
            'omi_batch_timeliness_new_over_sla_units',
            'Units admitted at or after the epoch and still unpublished past the 2h SLA, by counted leg',
            ['leg'],
            registry=registry,
        )
        self.timeliness_backlog = Gauge(
            'omi_batch_timeliness_backlog_units',
            'Unpublished units from before the epoch, by leg; kept visible, never alarmed',
            ['leg'],
            registry=registry,
        )
        self.timeliness_truncated = Gauge(
            'omi_batch_timeliness_scan_truncated',
            '1 when a leg\'s bounded walk may hide an older unpublished unit',
            ['leg'],
            registry=registry,
        )
        self.timeliness_observed_at = Gauge(
            'omi_batch_timeliness_observed_at_seconds',
            'Last successful timeliness sample',
            registry=registry,
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
        self.oldest_age = Gauge(
            'omi_batch_pipeline_oldest_age_seconds',
            'Oldest admitted uncommitted item age',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
        )
        self.ready_age = Gauge(
            'omi_batch_pipeline_ready_age_seconds',
            'Oldest item ready for GPU capacity',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
        )
        self.retry_age = Gauge(
            'omi_batch_pipeline_retry_age_seconds',
            'Age since first compute failure; alert above 600 seconds',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
        )
        self.refreshed_at = Gauge(
            'omi_batch_pipeline_metrics_refreshed_at_seconds',
            'Last complete queue sample timestamp',
            ['worker_release', 'namespace'],
            registry=registry,
        )
        self.ready_units = Gauge(
            'omi_batch_pipeline_admissible_ready_units',
            'Ready admitted units excluding held, parked, unmarked legacy and unevaluated refusals',
            ['priority', 'worker_release', 'namespace'],
            registry=registry,
        )
        self.capacity_refreshed_at = Gauge(
            'omi_batch_pipeline_capacity_refreshed_at_seconds',
            'Last complete three-priority admissible capacity count',
            ['worker_release', 'namespace'],
            registry=registry,
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

    def _refresh(self, store: Store, now: float) -> None:
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
        if capacity:
            for priority, count in capacity:
                self.ready_units.labels(LABELS[priority], *self.scope).set(count)
            self.capacity_refreshed_at.labels(*self.scope).set(now)
        if isinstance(store, FirestoreStore):
            from database.lifecycle_metrics_queries import record_pending, nojob

            self.record_pending.refresh(now, lambda: record_pending(store.client, store.namespace, now))
            self.nojob.refresh(now, lambda: nojob(store.client, store.namespace))
            self.refresh_timeliness(store, now)
            self.refresh_projection(store, now)

    def refresh_timeliness(self, store: FirestoreStore, now: float) -> None:
        """At most one sample per interval per process; a failed sample keeps last values and freshness."""
        if now < self._timeliness_due:
            return
        self._timeliness_due = now + timeliness_interval_seconds()
        if not batch_timeliness_alarm_enabled():
            self.timeliness_samples.labels('disabled').inc()
            return
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
        self.timeliness_samples.labels('ok').inc()

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
