"""Fleet adoption evidence is the consumer's TTL read, served by its real registry."""

import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import subprocess
from threading import Event
import time
from urllib.request import urlopen

import pytest
import yaml
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.parser import text_string_to_metric_families

from config import batch_pipeline_vendor_routing, directory_routing
from config.policy import resolve_batch_policy
from database import rollout_cohorts as store
from utils.rollout import runtime_percent as rp

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def runtime(monkeypatch):
    for key in ('K_REVISION', 'ROLLOUT_POD_TEMPLATE_HASH', 'OMI_BACKEND_RELEASE_SHA', 'OMI_DEPLOYMENT'):
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        'OMI_ENV_STAGE': 'prod',
        'BATCH_PIPELINE_ENABLED': 'true',
        'BATCH_PIPELINE_PERCENT': '13',
        'BATCH_LIVE_STT_RETIRE_PERCENT': '7',
        'BATCH_VENDOR_ROUTING_PERCENT': '5',
        'DIRECTORY_ROUTING_NEW_OWNER_PERCENT': '9',
    }.items():
        monkeypatch.setenv(key, value)
    for gauge in (rp.RUNTIME_PERCENT_VALUE, rp.RUNTIME_PERCENT_SOURCE, rp.RUNTIME_PERCENT_ERROR_SECONDS):
        monkeypatch.setattr(gauge, '_metrics', {})
    now = [1000.0]
    monkeypatch.setattr(rp.time, 'monotonic', lambda: now[0])
    outcome = [None]
    calls = []

    def read():
        calls.append(1)
        if isinstance(outcome[0], Exception):
            raise outcome[0]
        return None if outcome[0] is None else store.normalize_ramp_document(outcome[0])

    monkeypatch.setattr(rp, '_cache', rp._RampCache(read))
    monkeypatch.setattr(rp, '_background_submitter', lambda fn: fn())
    monkeypatch.setattr(rp.policy, '_percent_resolver', None)
    monkeypatch.setattr(rp.policy, '_legacy_sync_resolver', None)
    rp.configure_runtime_percent()
    registry = CollectorRegistry()
    rp.register_runtime_percent(registry)
    rp.register_runtime_percent(registry)
    assert not calls  # registering/describing cannot do cloud IO
    return outcome, now, calls, registry


def document(**percents):
    return {
        'schema_version': 1,
        'revision': 42,
        'envs': {'prod': {'percents': percents, 'legacy_sync': 'on', 'locked_by': None}},
    }


def samples(registry):
    return [s for family in text_string_to_metric_families(generate_latest(registry).decode()) for s in family.samples]


def values(registry):
    return {s.labels['name']: s.value for s in samples(registry) if s.name == 'omi_runtime_percent'}


@pytest.mark.parametrize('remote', [False, True])
def test_all_flags_export_the_effective_runtime_values(runtime, remote):
    outcome, _, _, registry = runtime
    if remote:
        outcome[0] = document(
            **{
                'batch-pipeline': 37,
                'first-summary': 21,
                'batch-live-stt-retire': 31,
                'batch-vendor-routing': 29,
                'legacy-sync': 17,
                'new-owner-cell1': 19,
            }
        )
    exported = values(registry)
    assert set(exported) == set(store.RAMP_NAMES)
    batch = resolve_batch_policy('synthetic-owner')
    assert exported['batch-pipeline'] == batch.batch_percent == (37 if remote else 13)
    assert exported['batch-live-stt-retire'] == batch.retire_percent == (31 if remote else 7)
    assert exported['batch-vendor-routing'] == batch_pipeline_vendor_routing.vendor_routing_percent(batch.batch_percent)
    # First-summary deadlines graduated to every owner; the export reports the permanent value.
    assert exported['first-summary'] == 100.0
    assert exported['legacy-sync'] == rp.runtime_percent('legacy-sync', env_default=0)
    assert exported['new-owner-cell1'] == rp.policy.runtime_percent(
        'new-owner-cell1', env_default=directory_routing.new_owner_percent_env()
    )
    assert len([s for s in samples(registry) if s.name == 'omi_runtime_percent']) == len(store.RAMP_NAMES)


@pytest.mark.parametrize(
    'envs,revision,run_revision',
    [
        (
            {'K_REVISION': 'backend-sync-00001-abc', 'ROLLOUT_POD_TEMPLATE_HASH': 'hash'},
            'backend-sync-00001-abc',
            'backend-sync-00001-abc',
        ),
        ({'ROLLOUT_POD_TEMPLATE_HASH': '785b7cd7b', 'OMI_BACKEND_RELEASE_SHA': 'sha'}, '785b7cd7b', ''),
        ({'OMI_BACKEND_RELEASE_SHA': 'release-sha'}, 'release-sha', ''),
        ({}, 'unknown', ''),
    ],
)
def test_labels_retain_name_and_source_and_identify_revision(runtime, monkeypatch, envs, revision, run_revision):
    for key, value in envs.items():
        monkeypatch.setenv(key, value)
    rows = samples(runtime[3])
    for row in rows:
        assert row.labels['revision'] == revision
        assert row.labels['revision_name'] == run_revision  # the existing guard's Cloud Run join
        expected = (
            {'name', 'revision', 'revision_name'}
            if row.name == 'omi_runtime_percent'
            else (
                {'source', 'revision', 'revision_name'}
                if row.name == 'omi_runtime_percent_source'
                else {'revision', 'revision_name'}
            )
        )
        assert set(row.labels) == expected
    assert {s.labels['source']: s.value for s in rows if s.name == 'omi_runtime_percent_source'} == {
        'firestore': 0,
        'lkg': 0,
        'env_default': 1,
        'pending': 0,
    }


def test_scrape_refreshes_idle_consumer_after_ttl_and_removes_old_document_values(runtime):
    outcome, now, calls, registry = runtime
    outcome[0] = document(**{'batch-pipeline': 60, 'batch-live-stt-retire': 40})
    assert values(registry)['batch-live-stt-retire'] == 40
    outcome[0] = document(**{'batch-pipeline': 3})
    assert values(registry)['batch-live-stt-retire'] == 40
    assert len(calls) == 1
    now[0] += rp.TTL_SECONDS + 1
    assert values(registry)['batch-pipeline'] == 3
    assert values(registry)['batch-live-stt-retire'] == 3  # env 7 is nested under runtime 3
    assert len(calls) == 2
    outcome[0] = RuntimeError('unavailable')
    now[0] += rp.TTL_SECONDS + 1
    assert values(registry)['batch-pipeline'] == 3
    assert next(s.value for s in samples(registry) if s.labels.get('source') == 'lkg') == 1
    outcome[0] = None
    now[0] += rp.TTL_SECONDS + 1
    assert values(registry)['batch-pipeline'] == 13  # never leave removed values behind


def test_cold_sync_scrape_returns_without_waiting_for_slow_refresh(runtime, monkeypatch):
    started, release = Event(), Event()

    def slow_read():
        started.set()
        assert release.wait(timeout=5)
        return store.normalize_ramp_document(document(**{'batch-pipeline': 37}))

    monkeypatch.setattr(rp, '_cache', rp._RampCache(slow_read))
    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(rp, '_background_submitter', executor.submit)
        try:
            before = time.perf_counter()
            assert not samples(runtime[3])
            assert time.perf_counter() - before < 0.5
            assert started.wait(timeout=1)
            pending = rp._cache.inflight
            assert pending is not None and not pending.done()
            assert not samples(runtime[3])
        finally:
            release.set()
    assert pending.done()
    assert values(runtime[3])['batch-pipeline'] == 37


def test_scrape_exports_cached_snapshot_while_refresh_is_pending(runtime, monkeypatch):
    outcome, now, calls, registry = runtime
    outcome[0] = document(**{'batch-pipeline': 37})
    assert values(registry)['batch-pipeline'] == 37
    queued = []
    monkeypatch.setattr(rp, '_background_submitter', queued.append)
    outcome[0] = document(**{'batch-pipeline': 12})
    now[0] += rp.TTL_SECONDS + 1
    assert values(registry)['batch-pipeline'] == 37
    assert values(registry)['batch-pipeline'] == 37
    assert len(queued) == 1 and len(calls) == 1
    queued[0]()
    assert values(registry)['batch-pipeline'] == 12


def test_telemetry_error_cannot_change_runtime_admission(runtime, monkeypatch):
    runtime[0][0] = document(**{'batch-pipeline': 37})
    assert values(runtime[3])['batch-pipeline'] == 37

    def fail(*args, **kwargs):
        raise ValueError('broken collector')

    monkeypatch.setattr(rp, '_export_values', fail)
    assert rp.runtime_percent('batch-pipeline', env_default=0) == 37
    assert rp._cache.inflight is None
    assert not samples(runtime[3])  # a scrape cannot refresh stale adoption evidence
    assert all(s.value == 0 for m in rp.RUNTIME_PERCENT_SOURCE.collect() for s in m.samples)


def test_gpu_entrypoint_exports_private_registry_and_each_supervised_process(runtime):
    from diarizer import batch_pipeline_runtime as worker

    registry = CollectorRegistry()
    server = worker.health_server(worker.RuntimeState(), registry, 0, '127.0.0.1')
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/metrics', timeout=5) as response:
            page = response.read()
        merged = worker.merge_metrics([(0, page), (1, page)])
        rows = [
            s
            for f in text_string_to_metric_families(merged.decode())
            for s in f.samples
            if s.name == 'omi_runtime_percent'
        ]
        assert len(rows) == 2 * len(store.RAMP_NAMES)
        assert {s.labels['worker_process'] for s in rows} == {'0', '1'}
    finally:
        server.shutdown()
        server.server_close()


def calls_in(path):
    tree = ast.parse((BACKEND / path).read_text())
    return {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


@pytest.mark.parametrize(
    'path', ['main.py', 'pusher/main.py', 'diarizer/batch_pipeline_runtime.py', 'utils/sync/worker_job.py']
)
def test_consumer_entrypoints_bind_runtime_exporter(path):
    assert 'configure_rollout_runtime' in calls_in(path)
    assert 'configure_runtime_percent' in calls_in('utils/rollout_cohorts.py')
    assert 'register_runtime_percent' in calls_in('utils/rollout/runtime_percent.py')
    if path == 'main.py':
        # backend, sync, backfill and integration use this entrypoint and sidecar listener.
        assert 'start_metrics_sidecar_server' in calls_in(path)
        action = (BACKEND.parent / '.github/actions/deploy-backend-stack/action.yml').read_text()
        assert 'cloud_run_gmp_sync.yaml' in action and 'cloud_run_gmp_sidecar.yaml' in action


@pytest.mark.parametrize('config_name', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
def test_cloud_run_scrape_keeps_every_runtime_family(config_name):
    config = yaml.safe_load((BACKEND / 'deploy' / config_name).read_text())
    endpoint = config['spec']['endpoints'][0]
    assert endpoint['port'] == 9090 and endpoint['path'] == '/metrics'
    for name in ('omi_runtime_percent', 'omi_runtime_percent_source', 'omi_runtime_percent_read_error_seconds'):
        for rule in endpoint['metricRelabeling']:
            label_values = ';'.join({'__name__': name}.get(k, '') for k in rule['sourceLabels'])
            match = re.fullmatch(rule['regex'], label_values)
            assert (rule['action'] == 'keep' and match) or (rule['action'] == 'drop' and not match)


@pytest.mark.parametrize(
    'chart,suffix',
    [
        ('batch-pipeline-worker', 'batch-pipeline-worker'),
        ('sync-backfill-worker', 'sync_backfill_worker'),
        ('backend-listen', 'backend_listen'),
        ('pusher', 'pusher'),
    ],
)
def test_gke_podmonitoring_scrapes_consumer_port_and_revision(chart, suffix):
    helm = shutil.which('helm')
    if not helm:
        pytest.skip('helm is not installed')
    directory = BACKEND / 'charts' / chart
    values_file = directory / f'prod_omi_{suffix}_values.yaml'
    if chart == 'sync-backfill-worker':
        values_file = directory / 'values.yaml'
    command = [
        helm,
        'template',
        'synthetic',
        str(directory),
        '--namespace',
        'prod-omi-backend',
        '-f',
        str(values_file),
        '--set-string',
        'image.tag=synthetic' if chart == 'backend-listen' else 'image.tag=',
        '--set-string',
        'image.digest=sha256:' + 'a' * 64,
        '--set-string',
        'image.pullPolicy=IfNotPresent',
    ]
    if chart == 'sync-backfill-worker':
        command += [
            '--set-string',
            'image.repository=example/worker',
            '--set-string',
            'runtimeSecret=synthetic-runtime',
            '--set-string',
            'serviceAccount.gcpEmail=synthetic@example.iam.gserviceaccount.com',
            '--set-string',
            'worker.apiUrl=https://synthetic.run.app',
            '--set-string',
            'worker.audience=https://synthetic.run.app',
        ]
    rendered = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
    docs = [d for d in yaml.safe_load_all(rendered.stdout) if d]
    deployments = [
        d
        for d in docs
        if d['kind'] == 'Deployment'
        and d['spec']['template']['metadata']['labels'].get('app.kubernetes.io/name') == chart
    ]
    assert deployments
    for deployment in deployments:
        pod = deployment['spec']['template']
        container = pod['spec']['containers'][0]
        env = {e['name']: e for e in container['env']}
        assert (
            env['ROLLOUT_POD_TEMPLATE_HASH']['valueFrom']['fieldRef']['fieldPath']
            == "metadata.labels['pod-template-hash']"
        )
        monitoring = next(
            d
            for d in docs
            if d['kind'] == 'PodMonitoring'
            and d['spec']['selector']['matchLabels'].items() <= pod['metadata']['labels'].items()
        )
        endpoint = monitoring['spec']['endpoints'][0]
        assert endpoint['path'] == '/metrics'
        assert next(p['containerPort'] for p in container['ports'] if p['name'] == endpoint['port']) == 8080
