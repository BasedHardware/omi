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
