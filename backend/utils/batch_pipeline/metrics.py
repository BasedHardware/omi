"""Queue-age autoscaling export. Refresh from a supervised worker, never import IO."""

from prometheus_client import CollectorRegistry, Gauge, Histogram, Counter, REGISTRY

from database.batch_pipeline_store import Store
from utils.batch_pipeline.contracts import Priority

LABELS = {Priority.FRESH: 'fresh', Priority.RECENT: 'recent', Priority.DEEP: 'deep'}
AGE_TARGETS = {Priority.FRESH: 30, Priority.RECENT: 300, Priority.DEEP: 3600}


class QueueMetrics:
    def __init__(
        self, registry: CollectorRegistry = REGISTRY, *, worker_release: str = 'unscoped', namespace: str = 'unscoped'
    ):
        self.scope = (worker_release, namespace)
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
        self.owner_wait = Histogram(
            'omi_batch_pipeline_owner_wait_seconds',
            'Per-item admission to lease wait; no owner labels',
            buckets=(1, 10, 30, 60, 300, 3600, 43200, 86400, 604800),
            registry=registry,
        )
        self.events = Counter(
            'omi_batch_pipeline_events_total',
            'Worker transition receipts; jobs/s is rate of completed events',
            ['event'],
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

    def record_head(self, event: str, priority: Priority, *, age: float | None = None) -> None:
        if event == 'ready_age' and age is not None:
            self.predecessor_ready_age.labels(LABELS[priority], *self.scope).observe(age)
        elif event == 'head_not_found':
            self.head_not_found.labels(LABELS[priority], *self.scope).inc()
        elif event == 'budget_exhausted':
            self.head_budget_exhausted.labels(LABELS[priority], *self.scope).inc()
        else:
            raise ValueError('static head scheduling event required')

    def refresh(self, store: Store, now: float) -> None:
        # Collect every query before changing gauges. Failed refresh retains last
        # values and does not advance freshness; adapters must reject stale data.
        samples = []
        for priority in Priority:
            pending = store.oldest(int(priority), ready_only=False)
            ready = store.oldest(int(priority), ready_only=True)
            samples.append((priority, pending, ready, store.oldest_retry(int(priority))))
        for priority, pending, ready, retry in samples:
            self.oldest_age.labels(LABELS[priority], *self.scope).set(
                max(0.0, now - pending) if pending is not None else 0
            )
            self.ready_age.labels(LABELS[priority], *self.scope).set(max(0.0, now - ready) if ready is not None else 0)
            self.retry_age.labels(LABELS[priority], *self.scope).set(max(0.0, now - retry) if retry is not None else 0)
        self.refreshed_at.labels(*self.scope).set(now)

    def record(self, event: str, *, wait_seconds: float | None = None) -> None:
        if event not in {
            'leased',
            'completed',
            'retry',
            'lease_expired',
            'dead',
            'committed',
            'quarantined',
            'recovery_held',
        }:
            raise ValueError('metric event must be a static worker transition')
        self.events.labels(event).inc()
        if event == 'leased' and wait_seconds is not None:
            self.owner_wait.observe(max(0.0, wait_seconds))
