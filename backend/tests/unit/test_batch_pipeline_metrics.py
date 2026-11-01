from dataclasses import replace
from pathlib import Path

from prometheus_client import CollectorRegistry
from unittest.mock import Mock
import pytest
import yaml

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
    assert registry.get_sample_value('omi_batch_pipeline_owner_wait_seconds_sum') == 10
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
    # must fail toward tripping on the oldest hold's age - a fresh zero could
    # bless a ramp while a real commitment sits unmeasured just past the bound.
    # A FIFO that is exactly as long as the bound, or shorter, is not
    # truncated: zero is truthful.
    truncated = Client([Doc({**held, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)])
    assert oldest(truncated, 'omi', 2) == 0.0
    exactly_bound = Client([Doc({**held, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT)])
    assert oldest(exactly_bound, 'omi', 2) is None
    just_short = Client([Doc({**held, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT - 1)])
    assert oldest(just_short, 'omi', 2) is None


def _deep_oldest_age(registry):
    return registry.get_sample_value(
        'omi_batch_pipeline_oldest_age_seconds',
        {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
    )


def test_allowance_hold_through_an_unevaluated_reevaluation_does_not_flap_the_proxy():
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


def test_lease_that_bypasses_admission_ends_the_parked_hold():
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
    # The #23638 truncation sentinel still fails toward tripping on the oldest
    # hold when marker-only holds fill the scan bound.
    truncated = [Doc({**parked, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)]
    assert oldest(Client(truncated), 'omi', 1) == 0.0
    exact = [Doc({**parked, 'enqueued_at': float(n)}) for n in range(OLDEST_POLICY_HOLD_SCAN_LIMIT)]
    assert oldest(Client(exact), 'omi', 1) is None
