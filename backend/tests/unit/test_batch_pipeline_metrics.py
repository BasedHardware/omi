from dataclasses import replace
import math
from pathlib import Path

from prometheus_client import CollectorRegistry
from unittest.mock import Mock
import pytest
import yaml

from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.metrics import QueueMetrics
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.scheduler import Scheduler

BACKEND = Path(__file__).resolve().parents[2]
ALERTS = BACKEND / 'charts/monitoring/batch-projection/alerts.yaml'


def test_projection_obligation_age_includes_quarantine_and_does_not_refresh_on_error():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = Mock(namespace='synthetic')
    store.projection_page.return_value = (['held'], None)
    reference = store.client.collection.return_value.document.return_value
    reference.get.return_value.to_dict.return_value = {'committed_at': 100.0}
    metrics.refresh_projection(store, 1001.0)
    assert registry.get_sample_value('omi_batch_projection_obligation_oldest_age_seconds') == 901
    assert registry.get_sample_value('omi_batch_projection_obligation_observed_at_seconds') == 1001
    assert 'quarantine_held' in store.projection_page.call_args.kwargs['states']
    store.projection_page.side_effect = RuntimeError('unavailable')
    with pytest.raises(RuntimeError):
        metrics.refresh_projection(store, 1100)
    assert registry.get_sample_value('omi_batch_projection_obligation_observed_at_seconds') == 1001
    store.projection_page.side_effect = None
    store.projection_page.return_value = ([], None)
    metrics.refresh_projection(store, 1200)
    assert registry.get_sample_value('omi_batch_projection_obligation_oldest_age_seconds') == 0


def test_projection_obligation_failing_first_sample_stays_never_observed():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = Mock(namespace='synthetic')
    store.projection_page.side_effect = RuntimeError('unavailable')
    with pytest.raises(RuntimeError):
        metrics.refresh_projection(store, 1000.0)
    # Never observed must read as zero, never a fabricated timestamp: the stale
    # rule's zero-inclusive expression is the only startup path that alarms.
    assert not registry.get_sample_value('omi_batch_projection_obligation_observed_at_seconds')
    store.projection_page.side_effect = None
    store.projection_page.return_value = ([], None)
    metrics.refresh_projection(store, 1001.0)
    assert registry.get_sample_value('omi_batch_projection_obligation_observed_at_seconds') == 1001


def test_stale_observation_alert_rule_includes_never_observed_zero_with_bounded_grace():
    rules = yaml.safe_load(ALERTS.read_text(encoding='utf-8'))
    alerts = {rule['alert']: rule for group in rules['spec']['groups'] for rule in group['rules']}
    stale = alerts['OmiBatchProjectionObservationStale']
    expr = ' '.join(stale['expr'].split())
    assert 'omi_batch_projection_obligation_observed_at_seconds > 0' not in expr
    assert 'time() - omi_batch_projection_obligation_observed_at_seconds >= 120' in expr
    assert stale['for'] == '2m'
    overdue = ' '.join(alerts['OmiBatchProjectionObligationOverdue']['expr'].split())
    assert 'time() - omi_batch_projection_obligation_observed_at_seconds < 120' in overdue


def test_queue_age_and_stale_refresh_retains_previous_sample(monkeypatch):
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    metrics.refresh(store, 100)
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_oldest_age_seconds',
            {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
        )
        == 100
    )
    lease = queue.pull(101)[0]
    metrics.refresh(store, 102)
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_ready_age_seconds',
            {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
        )
        == 0
    )
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_oldest_age_seconds',
            {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
        )
        == 102
    )

    def unavailable(*args, **kwargs):
        raise RuntimeError('store unavailable')

    monkeypatch.setattr(store, 'oldest', unavailable)
    with pytest.raises(RuntimeError):
        metrics.refresh(store, 200)
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_metrics_refreshed_at_seconds', {'worker_release': 'unscoped', 'namespace': 'unscoped'}
        )
        == 102
    )
    assert lease.item.segment_id == 'a'
    metrics.record('leased', wait_seconds=101)
    metrics.record('completed')
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'completed'}) == 1
    with pytest.raises(ValueError):
        metrics.record('user-id')


def test_min_refresh_interval_skips_reads_and_a_failure_retries_next_call(monkeypatch):
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry, min_refresh_seconds=30)
    store = MemoryStore()
    Scheduler(store).enqueue(item('a'), 0)
    calls = []
    oldest = store.oldest

    def counted(*args, **kwargs):
        calls.append(args)
        return oldest(*args, **kwargs)

    monkeypatch.setattr(store, 'oldest', counted)
    freshness = {'worker_release': 'unscoped', 'namespace': 'unscoped'}
    metrics.refresh(store, 100)
    reads = len(calls)
    assert reads > 0
    metrics.refresh(store, 129)
    assert len(calls) == reads
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', freshness) == 100

    def unavailable(*args, **kwargs):
        raise RuntimeError('store unavailable')

    monkeypatch.setattr(store, 'oldest', unavailable)
    with pytest.raises(RuntimeError):
        metrics.refresh(store, 130)
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', freshness) == 100
    # A failed sample does not start a new interval: the next call reads again.
    monkeypatch.setattr(store, 'oldest', counted)
    metrics.refresh(store, 131)
    assert len(calls) > reads
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', freshness) == 131


def test_a_refresh_started_during_another_skips_its_reads(monkeypatch):
    metrics = QueueMetrics(CollectorRegistry(), min_refresh_seconds=30)
    store = MemoryStore()
    calls = []
    oldest = store.oldest

    def overlapping(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            metrics.refresh(store, 100)  # a second caller arriving mid-read
        return oldest(*args, **kwargs)

    monkeypatch.setattr(store, 'oldest', overlapping)
    metrics.refresh(store, 100)
    assert len(calls) == 2 * len(list(Priority))


def test_zero_min_refresh_interval_reads_on_every_call(monkeypatch):
    metrics = QueueMetrics(CollectorRegistry())
    store = MemoryStore()
    calls = []
    oldest = store.oldest
    monkeypatch.setattr(store, 'oldest', lambda *a, **k: calls.append(a) or oldest(*a, **k))
    metrics.refresh(store, 100)
    reads = len(calls)
    metrics.refresh(store, 100)
    assert len(calls) == 2 * reads


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [('', 30.0), ('off', 0.0), ('0', 0.0), ('-5', 0.0), ('45', 45.0), ('61', 30.0), ('0.5', 30.0), ('bad', 30.0)],
)
def test_serving_metrics_min_refresh_seconds_is_bounded_below_the_guard_blind_window(monkeypatch, raw, expected):
    from config.batch_pipeline import serving_metrics_min_refresh_seconds

    monkeypatch.setenv('BATCH_PIPELINE_SERVING_METRICS_MIN_REFRESH_SECONDS', raw)
    assert serving_metrics_min_refresh_seconds() == expected


def test_admission_hold_reason_counter_counts_policy_defers_and_folds_unknown():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    metrics.record('admission_policy_deferred', reason='allowance_exhausted')
    metrics.record('admission_policy_deferred', reason='free-text-escape')
    # An unevaluated defer carries no reason; its lease never reached a decision.
    metrics.record('admission_unevaluated_deferred', reason='ignored')
    metrics.record('admission_policy_deferred')
    assert (
        registry.get_sample_value('omi_batch_pipeline_admission_hold_reasons_total', {'reason': 'allowance_exhausted'})
        == 1
    )
    assert registry.get_sample_value('omi_batch_pipeline_admission_hold_reasons_total', {'reason': 'unknown'}) == 1
    assert registry.get_sample_value('omi_batch_pipeline_admission_hold_reasons_total', {'reason': 'ignored'}) is None
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'admission_policy_deferred'}) == 3

    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    assert queue.defer('a', lease.token, 1, retry_after=60, held_reason='fair_use_restricted', admission_refused=True)
    assert (
        registry.get_sample_value('omi_batch_pipeline_admission_hold_reasons_total', {'reason': 'fair_use_restricted'})
        == 1
    )
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'admission_policy_deferred'}) == 4


def test_scheduler_records_new_transitions_without_duplicate_completion_count():
    from utils.batch_pipeline.contracts import WorkResult
    from utils.batch_pipeline.merge import OrderedMerge

    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(10)[0]
    result = WorkResult('a', 'gs://results/a')
    assert queue.complete(result, lease.token, 11)
    assert queue.complete(result, lease.token, 12)
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'completed'}) == 1
    assert registry.get_sample_value('omi_batch_pipeline_owner_wait_seconds_sum', {'relet': 'false'}) == 10
    merge = OrderedMerge(store, metrics=metrics)
    merge.commit_next('heavy', 13)
    merge.commit_next('heavy', 14)
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'committed'}) == 1


def test_exported_age_and_freshness_have_the_hpa_release_namespace_scope():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry, worker_release='synthetic-worker', namespace='synthetic')
    store = MemoryStore()
    Scheduler(store).enqueue(item('scoped'), 0)
    metrics.refresh(store, 100)
    scope = {'worker_release': 'synthetic-worker', 'namespace': 'synthetic'}
    assert registry.get_sample_value('omi_batch_pipeline_ready_age_seconds', {**scope, 'priority': 'deep'}) == 100
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', scope) == 100


def test_retry_age_survives_requeue_and_clears_only_after_success():
    from utils.batch_pipeline.contracts import WorkResult

    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('retry-head'), 0)
    lease = queue.pull(1)[0]
    queue.fail('retry-head', lease.token, 2)
    queue.recover(7)
    metrics.refresh(store, 1000)
    labels = {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'}
    assert registry.get_sample_value('omi_batch_pipeline_retry_age_seconds', labels) == 998
    lease = queue.pull(1000)[0]
    queue.complete(WorkResult('retry-head', 'gs://results/retry'), lease.token, 1001)
    metrics.refresh(store, 1002)
    assert registry.get_sample_value('omi_batch_pipeline_retry_age_seconds', labels) == 0


@pytest.fixture
def correctness(monkeypatch):
    from prometheus_client import Counter
    from utils.batch_pipeline import correctness_metrics as metrics

    registry = CollectorRegistry()
    monkeypatch.setattr(
        metrics,
        'TRANSITIONS',
        Counter('omi_batch_pipeline_correctness_transitions_total', '', ['event', 'source'], registry=registry),
    )
    monkeypatch.setattr(
        metrics,
        'DURATION',
        Counter('omi_batch_pipeline_correctness_audio_seconds_total', '', ['event'], registry=registry),
    )
    monkeypatch.setattr(
        metrics, 'LABELS', Counter('omi_batch_pipeline_projected_segments_total', '', ['authority'], registry=registry)
    )
    monkeypatch.setenv('BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED', 'true')
    return metrics, registry


def test_cpu_and_gpu_commits_and_failed_duration_count_only_changed_transitions(correctness):
    from utils.batch_pipeline.merge import OrderedMerge
    from utils.batch_pipeline.contracts import WorkResult

    _, registry = correctness
    store = MemoryStore()
    queue = Scheduler(store)
    for index, source in enumerate(('gpu_pump', 'ordered_merge')):
        sid = f'unit{index}'
        queue.enqueue(item(sid), 0)
        lease = queue.pull(1)[0]
        result = WorkResult(sid, 'gs://synthetic/result')
        assert queue.complete(result, lease.token, 2)
        merge = OrderedMerge(store, commit_source=source)
        assert merge.commit_next('heavy', 3)
        assert merge.commit_next('heavy', 4) is None
        assert (
            registry.get_sample_value(
                'omi_batch_pipeline_correctness_transitions_total', {'event': 'committed', 'source': source}
            )
            == 1
        )
    queue.enqueue(item('bad'), 0)
    lease = queue.pull(5)[0]
    assert queue.fail('bad', lease.token, 6, quarantine=True)
    assert not queue.fail('bad', lease.token, 7, quarantine=True)
    assert (
        registry.get_sample_value('omi_batch_pipeline_correctness_audio_seconds_total', {'event': 'failed'})
        == lease.item.duration_seconds
    )


def test_metrics_dark_and_label_abstention_is_separate(correctness, monkeypatch):
    metrics, registry = correctness
    monkeypatch.delenv('BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED')
    metrics.record('admitted', seconds=123)
    assert (
        registry.get_sample_value('omi_batch_pipeline_correctness_audio_seconds_total', {'event': 'admitted'}) is None
    )
    monkeypatch.setenv('BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED', 'true')
    metrics.record_labels(
        [
            {'speaker': 'SPEAKER_00', 'speaker_id_scope': 'final:batch:unit'},
            {
                'speaker': 'BATCH_UNASSIGNED_1',
                'speaker_id_scope': 'final:batch:unit',
                'speaker_match_source': 'batch_abstention',
            },
            {'speaker': 'SPEAKER_00', 'speaker_id_scope': 'sync:legacy'},
        ]
    )
    for authority in ('batch', 'abstained', 'legacy'):
        assert registry.get_sample_value('omi_batch_pipeline_projected_segments_total', {'authority': authority}) == 1


def test_allowance_policy_hold_does_not_trip_the_uncommitted_age_proxy():
    # 2026-10-25: 131 allowance_exhausted holds (~26h old) kept the in-cluster
    # guard's uncommitted_job_age_over_30m proxy tripped permanently. A durable
    # policy hold is parking, not a compute commitment: the proxy must not
    # measure it.
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('held'), 0)
    lease = queue.pull(100)[0]
    assert queue.defer('held', lease.token, 110, 86400, held_reason='allowance_exhausted')
    metrics.refresh(store, 93444)  # ~26h later: the hold alone reads age 0
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_oldest_age_seconds',
            {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
        )
        == 0
    )


def test_admitted_job_stuck_31_minutes_still_trips_the_proxy():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('held'), 0)
    lease = queue.pull(100)[0]
    assert queue.defer('held', lease.token, 110, 86400, held_reason='allowance_exhausted')
    queue.enqueue(item('stuck'), 100_000)  # admitted, uncommitted, no decision
    metrics.refresh(store, 101_860)  # the stuck job is 1860s old; the hold is ignored
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_oldest_age_seconds',
            {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
        )
        == 1860
    )


def test_firestore_oldest_walks_past_policy_holds():
    from database.batch_pipeline_store import is_allowance_policy_hold, oldest

    assert is_allowance_policy_hold({'compute_decision': {'outcome': 'held', 'reason': 'allowance_exhausted', 'at': 1}})
    assert not is_allowance_policy_hold({'compute_decision': {'outcome': 'allowed', 'reason': 'batch', 'at': 1}})
    assert not is_allowance_policy_hold({'compute_decision': {'outcome': 'held', 'reason': 'privacy_blocked', 'at': 1}})
    assert not is_allowance_policy_hold({})

    class Query:
        def __init__(self, rows):
            self.rows = rows

        def where(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, count):
            assert count == 501  # scan bound plus the truncation sentinel row
            return self

        def stream(self):
            return iter(self.rows)

    class Doc:
        def __init__(self, payload):
            self.payload = payload

        def to_dict(self):
            return self.payload

    class Client:
        def __init__(self, rows):
            self.rows = rows

        def collection(self, name):
            return Query(self.rows)

    held = {
        'merge_pending': True,
        'enqueued_at': 1.0,
        'compute_decision': {'outcome': 'held', 'reason': 'allowance_exhausted'},
    }
    commitment = {'merge_pending': True, 'enqueued_at': 2.0}
    rows = [Doc(held), Doc(dict(held)), Doc(commitment)]
    assert oldest(Client(rows), 'omi', 2) == 2.0  # skips the hold prefix, early-returns the commitment
    assert oldest(Client([Doc(dict(held))]), 'omi', 2) is None  # only holds, FIFO exhausted: nothing measurable
    assert oldest(Client([]), 'omi', 2) is None

    from database.batch_pipeline_store import OLDEST_POLICY_HOLD_SCAN_LIMIT

    # Review r1/r2 P1s: a scan truncated at the bound with holds in every row
    # must report an incomplete scan - a fresh zero could
    # bless a ramp while a real commitment sits unmeasured just past the bound.
    # A FIFO that is exactly as long as the bound, or shorter, is not
    # truncated: zero is truthful.
    truncated = Client([Doc({**held, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)])
    assert math.isnan(oldest(truncated, 'omi', 2))
    exactly_bound = Client([Doc({**held, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT)])
    assert oldest(exactly_bound, 'omi', 2) is None
    just_short = Client([Doc({**held, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT - 1)])
    assert oldest(just_short, 'omi', 2) is None


def _deep_oldest_age(registry):
    return registry.get_sample_value(
        'omi_batch_pipeline_oldest_age_seconds',
        {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
    )


@pytest.mark.parametrize('state', ['dead', 'quarantined', 'committed', 'privacy_blocked'])
def test_oldest_and_retry_skip_dispositioned_rows_but_keep_completed_result_ready(state):
    from database.batch_pipeline_store import oldest, oldest_retry

    class Doc:
        def __init__(self, job):
            self.job = job

        def to_dict(self):
            return self.job

    class Query:
        def __init__(self, jobs):
            self.jobs = jobs

        def collection(self, *args):
            return self

        def where(self, *args):
            return self

        def order_by(self, *args):
            return self

        def limit(self, limit):
            self.bound = limit
            return self

        def stream(self):
            return iter(Doc(job) for job in self.jobs[: self.bound])

    disposed = {'state': state, 'enqueued_at': 1, 'retry_started_at': 2, 'merge_pending': True}
    active = {
        'state': 'result_ready',
        'enqueued_at': 100,
        'retry_started_at': 200,
        'merge_pending': True,
        'terminal_disposition': {'state': 'completed'},
    }
    assert oldest(Query([disposed, active]), 'synthetic', 0) == 100
    assert oldest_retry(Query([disposed, active]), 'synthetic', 0) == 200
    assert oldest(Query([disposed]), 'synthetic', 0) is None
    assert oldest_retry(Query([disposed]), 'synthetic', 0) is None
    assert math.isnan(oldest(Query([disposed] * 501), 'synthetic', 0))
    assert math.isnan(oldest_retry(Query([disposed] * 501), 'synthetic', 0))


def test_incomplete_age_sample_preserves_nan_without_blocking_other_queue_signals():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    store.oldest = lambda priority, ready_only: None if ready_only or priority else float('nan')
    metrics.refresh(store, 1000)
    labels = {'priority': 'fresh', 'worker_release': 'unscoped', 'namespace': 'unscoped'}
    assert math.isnan(registry.get_sample_value('omi_batch_pipeline_oldest_age_seconds', labels))
    assert registry.get_sample_value('omi_batch_pipeline_ready_age_seconds', labels) == 0
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_metrics_refreshed_at_seconds', {'worker_release': 'unscoped', 'namespace': 'unscoped'}
        )
        == 1000
    )


def test_allowance_hold_through_an_unevaluated_reevaluation_does_not_flap_the_proxy(monkeypatch):
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')  # Legacy recovery under rollback.
    # 2026-10-27: the proxy flapped to ~54h when a held job's re-evaluation came
    # back unevaluated: defer pops compute_decision (BLIND, never a false hold)
    # and the job read as a decisionless commitment until the next re-hold.
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(replace(item('held'), requires_compute_admission=True), 0)
    lease = queue.pull(100)[0]
    assert queue.defer('held', lease.token, 110, 60, held_reason='allowance_exhausted', admission_refused=True)
    queue.recover(200)
    lease = queue.pull(200)[0]
    assert queue.defer('held', lease.token, 210, admission_refused=True)  # unevaluated RPC
    job = store.rows['jobs', 'held']
    assert 'compute_decision' not in job  # BLIND contract unchanged
    assert job['last_policy_hold'] == {'reason': 'allowance_exhausted', 'at': 110}
    metrics.refresh(store, 194_400)  # ~54h later: still parked, not a commitment
    assert _deep_oldest_age(registry) == 0


def test_lease_that_bypasses_admission_ends_the_parked_hold(monkeypatch):
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')  # Legacy recovery under rollback.
    # Review (Luna): with offline enforcement off, a unit that does not require
    # compute admission dispatches without authorize(); its lease is a real
    # commitment, so a stale hold marker must not hide it from the proxy.
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('held'), 0)
    lease = queue.pull(100)[0]
    assert queue.defer('held', lease.token, 110, 60, held_reason='allowance_exhausted', admission_refused=True)
    queue.recover(200)
    lease = queue.pull(200)[0]
    assert queue.defer('held', lease.token, 210, admission_refused=True)
    assert 'last_policy_hold' not in store.rows['jobs', 'held']
    metrics.refresh(store, 1900)
    assert _deep_oldest_age(registry) == 1900


def test_firestore_oldest_skips_a_decisionless_job_with_a_last_allowance_hold():
    from database.batch_pipeline_store import OLDEST_POLICY_HOLD_SCAN_LIMIT, is_allowance_policy_hold, oldest

    parked = {'merge_pending': True, 'last_policy_hold': {'reason': 'allowance_exhausted', 'at': 1}}
    assert is_allowance_policy_hold(parked)
    assert not is_allowance_policy_hold({'last_policy_hold': {'reason': 'privacy_blocked', 'at': 1}})
    # The current decision wins over the marker whenever one is recorded.
    assert not is_allowance_policy_hold(
        {**parked, 'compute_decision': {'outcome': 'allowed', 'reason': 'batch', 'at': 2}}
    )

    class Query:
        def __init__(self, rows):
            self.rows = rows

        def where(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, count):
            return self

        def stream(self):
            return iter(self.rows)

    class Doc:
        def __init__(self, payload):
            self.payload = payload

        def to_dict(self):
            return self.payload

    class Client:
        def __init__(self, rows):
            self.rows = rows

        def collection(self, name):
            return Query(self.rows)

    commitment = {'merge_pending': True, 'enqueued_at': 2.0}
    assert oldest(Client([Doc({**parked, 'enqueued_at': 1.0}), Doc(commitment)]), 'omi', 1) == 2.0
    assert oldest(Client([Doc({**parked, 'enqueued_at': 1.0})]), 'omi', 1) is None
    # Marker-only holds have the same incomplete-scan contract as current
    # allowance decisions: never fabricate late work or report a fresh zero.
    truncated = [Doc({**parked, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)]
    assert math.isnan(oldest(Client(truncated), 'omi', 1))
    exact = [Doc({**parked, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT)]
    assert oldest(Client(exact), 'omi', 1) is None


def test_elected_queue_sampler_follower_reads_nothing_and_hands_over(monkeypatch):
    from utils.batch_pipeline.leader import LeaderLease, QUEUE_METRICS
    from utils.batch_pipeline import metrics as module
    from unittest.mock import Mock

    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    store = MemoryStore()
    monkeypatch.setattr(store, 'ready_for_capacity', Mock(return_value=0), raising=False)
    for name in ('oldest', 'oldest_retry'):
        monkeypatch.setattr(store, name, Mock(wraps=getattr(store, name)))
    registries = [CollectorRegistry(), CollectorRegistry()]
    samplers = [
        QueueMetrics(
            registry,
            capacity_sampling=True,
            oldest_leader=LeaderLease(store, QUEUE_METRICS, ttl_seconds=20, clock=lambda: clock[0]),
        )
        for registry in registries
    ]
    labels = {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'}
    samplers[0].refresh(store, clock[0])
    samplers[1].refresh(store, clock[0])
    assert store.oldest.call_count == 6
    assert store.oldest_retry.call_count == 3
    assert store.ready_for_capacity.call_count == 3
    assert _deep_oldest_age(registries[0]) == 0
    assert _deep_oldest_age(registries[1]) is None
    assert registries[1].get_sample_value('omi_batch_pipeline_admissible_ready_units', labels) is None
    # Lease expires before the next default serving sample (40s). A follower
    # can take over in that interval; the former leader drops only its gauges.
    clock[0] += 40
    samplers[1].refresh(store, clock[0])
    samplers[0].refresh(store, clock[0])
    assert store.oldest.call_count == 12
    assert store.oldest_retry.call_count == 6
    assert store.ready_for_capacity.call_count == 6
    assert _deep_oldest_age(registries[0]) is None
    assert _deep_oldest_age(registries[1]) == 0
    assert registries[1].get_sample_value('omi_batch_pipeline_admissible_ready_units', labels) == 0


def test_lever_zero_restores_queries_on_every_instance_and_old_freshness(monkeypatch):
    from unittest.mock import Mock
    from utils.batch_pipeline import metrics as module

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"batch_metrics_oldest_leader":0}')
    leader = Mock()
    leader.acquire.return_value = False
    store = MemoryStore()
    monkeypatch.setattr(store, 'oldest', Mock(wraps=store.oldest))
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    for _ in range(2):
        registry = CollectorRegistry()
        sampler = QueueMetrics(registry, oldest_leader=leader, oldest_min_refresh_seconds=60)
        sampler.refresh(store, 100)
        sampler.refresh(store, 115)
        clock[0] += 61
        assert _deep_oldest_age(registry) == 0  # old adapter freshness contract
    assert store.oldest.call_count == 24
    leader.acquire.assert_not_called()


def test_queue_gauges_expire_without_another_refresh_and_keep_local_gauges(monkeypatch):
    from utils.batch_pipeline import metrics as module

    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    registry = CollectorRegistry()
    sampler = QueueMetrics(registry, capacity_sampling=True)
    assert _deep_oldest_age(registry) is None
    store = MemoryStore()
    monkeypatch.setattr(store, 'ready_for_capacity', lambda *_: 0, raising=False)
    sampler.refresh(store, 100)
    sampler.record('leased', wait_seconds=1)
    clock[0] = 159.9
    assert _deep_oldest_age(registry) == 0
    clock[0] = 160
    for family in registry.collect():
        if family.name in {
            'omi_batch_pipeline_oldest_age_seconds',
            'omi_batch_pipeline_ready_age_seconds',
            'omi_batch_pipeline_retry_age_seconds',
            'omi_batch_pipeline_metrics_refreshed_at_seconds',
            'omi_batch_pipeline_admissible_ready_units',
            'omi_batch_pipeline_capacity_refreshed_at_seconds',
        }:
            assert not family.samples
    assert _deep_oldest_age(registry) is None
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'leased'}) == 1


def test_gpu_fallback_bounds_only_queue_queries_and_failed_samples_expire(monkeypatch):
    from unittest.mock import Mock
    from utils.batch_pipeline import metrics as module
    from database.batch_pipeline_store import FirestoreStore
    from database import lifecycle_metrics_queries

    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    registry = CollectorRegistry()
    sampler = QueueMetrics(registry, capacity_sampling=True, oldest_min_refresh_seconds=60)
    # Firestore boundary is mocked; no cloud clients or reads.
    store = Mock(spec=FirestoreStore)
    store.client, store.namespace = Mock(), 'synthetic'
    store.oldest.return_value = store.oldest_retry.return_value = None
    store.ready_for_capacity.return_value = 0
    monkeypatch.setattr(sampler.record_pending, 'refresh', Mock())
    monkeypatch.setattr(sampler.nojob, 'refresh', Mock())
    monkeypatch.setattr(sampler, 'refresh_timeliness', Mock())
    monkeypatch.setattr(sampler, 'refresh_projection', Mock())
    monkeypatch.setattr(lifecycle_metrics_queries, 'record_pending', Mock())
    monkeypatch.setattr(lifecycle_metrics_queries, 'nojob', Mock())
    for instant in (100, 115, 130, 145, 160):
        clock[0] = instant
        sampler.refresh(store, instant)
    assert store.oldest.call_count == 12
    assert store.oldest_retry.call_count == 6
    assert store.ready_for_capacity.call_count == 6
    assert sampler.refresh_timeliness.call_count == 5
    assert sampler.refresh_projection.call_count == 5
    assert sampler.record_pending.refresh.call_count == 5
    clock[0] = 220
    store.oldest.side_effect = TimeoutError('synthetic')
    with pytest.raises(TimeoutError):
        sampler.refresh(store, 220)
    assert _deep_oldest_age(registry) is None
    # Failure did not reserve another 60s; the immediately following tick retries.
    store.oldest.side_effect = None
    sampler.refresh(store, 221)
    assert _deep_oldest_age(registry) == 0


def test_capacity_expiry_does_not_borrow_a_successful_age_sample_clock(monkeypatch):
    from utils.batch_pipeline import metrics as module
    from unittest.mock import Mock

    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    registry = CollectorRegistry()
    sampler = QueueMetrics(registry, capacity_sampling=True)
    store = MemoryStore()
    capacity = Mock(return_value=0)
    monkeypatch.setattr(store, 'ready_for_capacity', capacity, raising=False)
    sampler.refresh(store, 100)
    scope = {'worker_release': 'unscoped', 'namespace': 'unscoped'}
    assert registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope) == 100
    clock[0] = 150
    capacity.side_effect = TimeoutError('synthetic')
    sampler.refresh(store, 150)
    clock[0] = 160
    assert _deep_oldest_age(registry) == 0
    assert registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope) is None
    assert registry.get_sample_value('omi_batch_pipeline_admissible_ready_units', {**scope, 'priority': 'deep'}) is None


def test_gpu_query_cadence_does_not_stale_per_pod_busy_time_heartbeat(monkeypatch):
    from utils.batch_pipeline import metrics as module

    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    registry = CollectorRegistry()
    sampler = QueueMetrics(registry, oldest_min_refresh_seconds=60)
    store = MemoryStore()
    scope = {'worker_release': 'unscoped', 'namespace': 'unscoped'}
    # Simulate 2s of IO plus 15s sleep: ticks arrive 17s apart, so the
    # next queue sample is at 168, after the 160 queue freshness deadline.
    for instant in (100, 117, 134, 151):
        clock[0] = instant
        sampler.refresh(store, instant)
    clock[0] = 161
    assert _deep_oldest_age(registry) is None
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', scope) is None
    assert registry.get_sample_value('omi_batch_pipeline_sampler_observed_at_seconds', scope) == 151
    sampler.refresh(store, 168)
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', scope) == 168


def test_queue_refresh_feeds_the_vendor_held_and_provider_stage_gauges(monkeypatch):
    from unittest.mock import Mock
    from prometheus_client import REGISTRY
    from utils.batch_pipeline import metrics as module
    from database.batch_pipeline_store import FirestoreStore
    from database import lifecycle_metrics_queries
    from utils.observability.reasons import VendorHoldReason

    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    registry = CollectorRegistry()
    sampler = QueueMetrics(registry, namespace='synthetic-ns')
    # Firestore boundary is mocked; no cloud clients or reads.
    store = Mock(spec=FirestoreStore)
    store.client, store.namespace = Mock(), 'synthetic'
    store.oldest.return_value = store.oldest_retry.return_value = None
    for name in ('record_pending', 'nojob'):
        monkeypatch.setattr(getattr(sampler, name), 'refresh', Mock())
    monkeypatch.setattr(sampler, 'refresh_timeliness', Mock())
    monkeypatch.setattr(sampler, 'refresh_projection', Mock())
    held = Mock(return_value=({**{r: 0 for r in VendorHoldReason}, VendorHoldReason.FUNDS_REFUSAL: 7}, 5400.0, False))
    stage = Mock(return_value={'provider_pending': (300, 86400.0), 'provider_running': (2, 30.0)})
    monkeypatch.setattr(lifecycle_metrics_queries, 'vendor_held', held)
    monkeypatch.setattr(lifecycle_metrics_queries, 'provider_stage', stage)
    sampler.refresh(store, 100.0)
    sampler.refresh(store, 200.0)  # inside the 300 s interval: no second read
    assert held.call_count == stage.call_count == 1
    assert REGISTRY.get_sample_value('omi_batch_pipeline_vendor_held_units', {'reason': 'funds_refusal'}) == 7
    assert REGISTRY.get_sample_value('omi_batch_pipeline_vendor_held_oldest_age_seconds') == 5400.0
    labels = {'state': 'provider_pending', 'worker_release': 'unscoped', 'namespace': 'synthetic-ns'}
    assert registry.get_sample_value('omi_batch_pipeline_provider_stage_units', labels) == 300
    assert registry.get_sample_value('omi_batch_pipeline_provider_stage_oldest_age_seconds', labels) == 86400.0
    # A stalled sampler expires instead of exporting a frozen stock.
    clock[0] = 100.0 + 2 * module.VENDOR_HELD_REFRESH_SECONDS + 61
    assert registry.get_sample_value('omi_batch_pipeline_provider_stage_units', labels) is None
    # A failed read keeps the last held values and publishes no synthetic zero.
    held.side_effect = TimeoutError('synthetic')
    stage.return_value = {'provider_pending': (301, 86700.0), 'provider_running': (0, 0.0)}
    sampler.refresh(store, 100.0 + module.VENDOR_HELD_REFRESH_SECONDS + 1)
    assert REGISTRY.get_sample_value('omi_batch_pipeline_vendor_held_units', {'reason': 'funds_refusal'}) == 7
    # ...and does not stop the provider-stage sample.
    clock[0] = 100.0 + module.VENDOR_HELD_REFRESH_SECONDS + 1
    assert registry.get_sample_value('omi_batch_pipeline_provider_stage_units', labels) == 301


def test_timeliness_cohort_includes_provider_running_but_not_provider_pending():
    from database.batch_pipeline_store import TIMELINESS_ACTIVE_STATES, TIMELINESS_UNCOMMITTED_STATES

    assert 'provider_running' in TIMELINESS_ACTIVE_STATES
    assert 'provider_pending' not in TIMELINESS_UNCOMMITTED_STATES
