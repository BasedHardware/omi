"""The lab must refuse writes even if a new product seam attempts one."""

from types import SimpleNamespace

import pytest

from testing.owner_lab.final_pass_repro import write_fence, WriteBlocked


@pytest.mark.parametrize('method', ['set', 'update', 'delete', 'create'])
def test_firestore_document_batch_and_transaction_writes_fenced(method):
    from google.cloud.firestore_v1.document import DocumentReference
    from google.cloud.firestore_v1.batch import WriteBatch
    from google.cloud.firestore_v1.transaction import Transaction
    from google.cloud.firestore_v1.async_document import AsyncDocumentReference

    with write_fence():
        for cls in (DocumentReference, AsyncDocumentReference, WriteBatch, Transaction):
            with pytest.raises(WriteBlocked):
                getattr(cls, method)(None)


def test_firestore_transport_refuses_buffered_writes_but_allows_readonly_commit(monkeypatch):
    from google.cloud.firestore_v1.services.firestore import FirestoreClient

    calls = []
    monkeypatch.setattr(FirestoreClient, 'commit', lambda *a, **kw: calls.append(True))
    with write_fence():
        for request in ({'writes': [{}]}, SimpleNamespace(writes=[object()])):
            with pytest.raises(WriteBlocked):
                FirestoreClient.commit(None, request)
        FirestoreClient.commit(None, {'writes': []})
    assert calls == [True]


@pytest.mark.parametrize(
    'method',
    ['upload_from_file', 'upload_from_filename', 'upload_from_string', 'delete', 'patch', 'compose', 'rewrite'],
)
def test_gcs_writes_fenced(method):
    from google.cloud.storage import Blob

    with write_fence(), pytest.raises(WriteBlocked):
        getattr(Blob, method)(None)


@pytest.mark.parametrize('command', ['SET', 'DEL', 'EVAL', 'HSET', 'INCR', 'EXPIRE', 'PUBLISH', 'XADD', 'UNKNOWN'])
def test_redis_writes_including_scripts_and_unknown_commands_fenced(command):
    from redis.client import Redis, Pipeline
    from redis.connection import Connection
    from redis.asyncio.client import Redis as AsyncRedis

    with write_fence():
        for cls in (Redis, Pipeline, AsyncRedis):
            with pytest.raises(WriteBlocked):
                cls.execute_command(None, command, 'synthetic-key')
        with pytest.raises(WriteBlocked):
            Connection.send_command(None, command, 'synthetic-key')


def test_already_buffered_redis_pipeline_cannot_write():
    from redis.client import Pipeline

    with write_fence(), pytest.raises(WriteBlocked):
        Pipeline.execute(SimpleNamespace(command_stack=[(('SET', 'synthetic-key', 'value'), {})]))


@pytest.mark.parametrize(
    'metric',
    [
        'omi_transcription_final_pass_total',
        'omi_transcription_final_pass_unit_skips_total',
        'omi_transcription_final_pass_retry_terminal_total',
        'omi_transcription_final_pass_retry_terminal_observed_at_seconds',
        'omi_transcription_final_pass_agreement_bucket',
        'omi_transcription_final_pass_agreement_sum',
        'omi_transcription_final_pass_agreement_count',
        'omi_transcription_final_pass_latency_seconds_bucket',
        'omi_transcription_final_pass_latency_seconds_sum',
        'omi_transcription_final_pass_latency_seconds_count',
        'omi_transcription_final_pass_owner_delta_ratio_bucket',
        'omi_transcription_final_pass_owner_delta_ratio_sum',
        'omi_transcription_final_pass_owner_delta_ratio_count',
    ],
)
def test_sync_scrape_keeps_batch_final_pass_terminal_metric(metric):
    import re
    from pathlib import Path
    import yaml

    config = yaml.safe_load((Path(__file__).resolve().parents[2] / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    rules = config['spec']['endpoints'][0]['metricRelabeling']
    for rule in rules:
        values = [metric if label == '__name__' else '' for label in rule['sourceLabels']]
        matches = re.fullmatch(rule['regex'], ';'.join(values)) is not None
        assert not ((rule['action'] == 'keep' and not matches) or (rule['action'] == 'drop' and matches))


def test_final_pass_gate_inventory_includes_source_backed_metric_names():
    import json
    from pathlib import Path

    inventory = json.loads(
        (Path(__file__).resolve().parents[2] / 'charts/monitoring/metric-inventory.prod.json').read_text()
    )
    expected = {
        'omi_transcription_final_pass_owner_delta_ratio_bucket',
        'omi_transcription_final_pass_owner_delta_ratio_sum',
        'omi_transcription_final_pass_owner_delta_ratio_count',
        'omi_transcription_final_pass_unit_skips_total',
        'omi_transcription_final_pass_retry_terminal_total',
        'omi_transcription_final_pass_retry_terminal_observed_at_seconds',
    }
    assert expected <= set(inventory['metrics']) | set(inventory['declared_metrics'])


def test_readonly_redis_pipeline_is_not_changed_by_the_fence():
    import fakeredis

    client = fakeredis.FakeRedis()
    client.set('synthetic-key', 'original')
    pipeline = client.pipeline()
    pipeline.get('synthetic-key')
    with write_fence():
        assert pipeline.execute() == [b'original']
        assert client.pipeline().get('synthetic-key').execute() == [b'original']


def test_prebuffered_redis_write_is_refused_without_changing_data():
    import fakeredis

    client = fakeredis.FakeRedis()
    client.set('synthetic-key', 'original')
    pipeline = client.pipeline()
    pipeline.set('synthetic-key', 'changed')
    with write_fence(), pytest.raises(WriteBlocked):
        pipeline.execute()
    assert client.get('synthetic-key') == b'original'


def test_metric_isolation_covers_existing_values_new_labels_and_lazy_collectors():
    from prometheus_client import REGISTRY, Counter, Histogram
    from testing.owner_lab.final_pass_repro import isolated_metrics

    counter = Counter('owner_lab_isolation_test', 'Synthetic metric', ['case'])
    histogram = Histogram('owner_lab_isolation_seconds', 'Synthetic latency')
    live = counter.labels(case='live')
    live.inc(2)
    try:
        before = (list(counter.collect()), list(histogram.collect()))
        with pytest.raises(RuntimeError, match='synthetic replay error'):
            with isolated_metrics():
                live.inc(10)
                counter.labels(case='replay').inc()
                histogram.observe(10)
                Counter('owner_lab_lazy_test', 'Imported inside replay').inc()
                raise RuntimeError('synthetic replay error')
        assert (list(counter.collect()), list(histogram.collect())) == before
        assert 'owner_lab_lazy_test' not in REGISTRY._names_to_collectors
        live.inc()
        assert live._value.get() == 3  # Restoration also runs on exceptional exit.
    finally:
        REGISTRY.unregister(counter)
        REGISTRY.unregister(histogram)


def test_metric_isolation_preserves_unrelated_thread_observations():
    from concurrent.futures import ThreadPoolExecutor
    from prometheus_client import REGISTRY, Counter
    from testing.owner_lab.final_pass_repro import isolated_metrics

    counter = Counter('owner_lab_other_thread_test', 'Synthetic metric', ['caller'])
    try:
        with ThreadPoolExecutor(max_workers=1) as pool, isolated_metrics():
            counter.labels(caller='replay').inc()
            pool.submit(lambda: counter.labels(caller='serving').inc()).result(timeout=2)
        assert set(counter._metrics) == {('serving',)}
        assert counter.labels(caller='serving')._value.get() == 1
    finally:
        REGISTRY.unregister(counter)
