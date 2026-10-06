"""Rollout ownership/isolation contracts for the #20391 canary and #20696 stable flip."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
import websockets
import yaml
from websockets.legacy.server import serve

from config.live_stt_recovery import current_recovery_enabled, recovery_enabled
from deploy.compose_runtime_env import compose_manifest
from testing.live_stt_soak.manifest import render as soak_manifest
from testing.live_stt_soak.run import metric_samples, session, summarize, validate_pod, public_pcm, pod_generation
from testing.live_stt_soak.safety import validate_environment, validate_target
from testing.live_stt_soak.transport import ProviderConnections, fake_provider

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    'listen_canary_renderer', ROOT / 'backend/scripts/render_listen_canary.py'
)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)
IMAGE = 'gcr.io/based-hardware-dev/backend@sha256:' + 'a' * 64


@pytest.mark.parametrize('runtime_source', ['committed', 'composed'])
def test_stable_recovery_flag_is_scoped_to_prod_listen(runtime_source):
    flag = 'STT_FAILOVER_RECOVERY_ENABLED'
    # Use the equivalent safe C parser for the large committed manifest so
    # this scope contract fits the fast-unit CPU budget on CI runners.
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    manifest = (
        yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=loader)
        if runtime_source == 'committed'
        else compose_manifest()
    )

    def declarations(node, path=()):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == flag:
                    yield path, value
                else:
                    yield from declarations(value, (*path, key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from declarations(value, (*path, index))

    # Exhaustive paths also reject declarations (even false/secret-backed) on
    # pusher, sync, desktop-backend, jobs, shared config or any future service.
    assert dict(declarations(manifest)) == {
        ('environments', 'prod', 'gke', 'backend-listen', 'env'): {'value': 'true', 'category': 'rollout'},
        ('environments', 'dev', 'gke', 'backend-listen', 'env'): {'value': 'false', 'category': 'rollout'},
    }

    for environment, expected in (('prod', 'true'), ('dev', 'false')):
        values = yaml.load(
            (ROOT / f'backend/charts/backend-listen/{environment}_omi_backend_listen_values.yaml').read_text(),
            Loader=loader,
        )
        assert [entry for entry in values['env'] if entry['name'] == flag] == [{'name': flag, 'value': expected}]


@pytest.mark.parametrize('value', [None, 'false'], ids=['unset', 'false'])
def test_stable_recovery_code_default_remains_off(monkeypatch, value):
    flag = 'STT_FAILOVER_RECOVERY_ENABLED'
    if value is None:
        monkeypatch.delenv(flag, raising=False)
    else:
        monkeypatch.setenv(flag, value)
    token = current_recovery_enabled.set(None)
    try:
        assert recovery_enabled() is False
    finally:
        current_recovery_enabled.reset(token)


@pytest.mark.parametrize('environment', ['prod', 'dev'])
@pytest.mark.skipif(shutil.which('helm') is None, reason='Helm render contract requires helm')
def test_canary_renders_only_independent_pinned_deployment(environment):
    candidate = renderer.render(environment, IMAGE, 2, {'STT_FAILOVER_RECOVERY_ENABLED': 'true'})
    baseline = renderer.render(environment, IMAGE, 2, {})
    assert candidate['kind'] == 'Deployment'
    assert candidate['metadata']['name'] == f'{environment}-omi-backend-listen-canary'
    assert candidate['metadata']['namespace'] == f'{environment}-omi-backend'
    assert candidate['spec']['replicas'] == 2
    selector = candidate['spec']['selector']['matchLabels']
    assert selector == {
        'app.kubernetes.io/name': 'backend-listen',
        'app.kubernetes.io/instance': f'{environment}-omi-backend-listen',
        'track': 'canary',
    }
    pod = candidate['spec']['template']
    assert all(pod['metadata']['labels'][key] == value for key, value in selector.items())
    assert 'app.kubernetes.io/managed-by' not in candidate['metadata']['labels']
    assert pod['metadata']['annotations']['prometheus.io/scrape'] == 'true'
    container = pod['spec']['containers'][0]
    assert container['image'] == IMAGE
    assert container['resources'] == baseline['spec']['template']['spec']['containers'][0]['resources']
    assert pod['spec']['terminationGracePeriodSeconds'] == 120
    assert container['lifecycle']['preStop']['exec']['command'] == ['sh', '-c', 'sleep 15']
    assert [e for e in container['env'] if e['name'] == 'STT_FAILOVER_RECOVERY_ENABLED'] == [
        {'name': 'STT_FAILOVER_RECOVERY_ENABLED', 'value': 'true'}
    ]


def test_production_canary_telemetry_is_excluded_only_from_main_hpa():
    monitoring = ROOT / 'backend/charts/monitoring'
    values = yaml.safe_load((monitoring / 'kube-prometheus-stack/prod_omi_monitoring_values.yaml').read_text())
    jobs = values['prometheus']['prometheusSpec']['additionalScrapeConfigs']
    scrape = next(job for job in jobs if job['job_name'] == 'backend-listen-metrics')
    # Pod discovery can see track without any kube-state-metrics allowlist.
    assert scrape['kubernetes_sd_configs'] == [{'role': 'pod'}]
    relabels = scrape['relabel_configs']
    assert {'source_labels': ['__meta_kubernetes_pod_label_track'], 'target_label': 'listen_track'} in relabels
    assert {'source_labels': ['__meta_kubernetes_pod_name'], 'target_label': 'pod'} in relabels
    # Canary must still be scraped for rollout/fleet health queries.
    assert not any(
        'track' in source
        for rule in relabels
        if rule.get('action') in {'keep', 'drop'}
        for source in rule.get('source_labels', [])
    )
    assert not scrape.get('metric_relabel_configs')
    adapter = yaml.safe_load((monitoring / 'prometheus-adapter/prod_omi_prometheus_adapter.yaml').read_text())
    rule = next(
        rule
        for rule in adapter['rules']['external']
        if rule['name']['as'] == 'backend_listen_active_ws_connections_per_pod'
    )
    queries = (ROOT / 'backend/docs/runbooks/listen-stt-canary-queries.promql').read_text()
    assert rule['metricsQuery'] in queries
    assert (
        'up{job="backend-listen-metrics",namespace="prod-omi-backend",'
        'listen_track="canary",pod=~"${canary_pods:regex}"}'
    ) in queries


def _adapter_query_result(query, series):
    """Evaluate selectors/avg over an instant-vector fixture; reject other syntax."""
    average = query.startswith('avg(') and query.endswith(')')
    selector = query[4:-1] if average else query
    parsed = re.fullmatch(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?', selector)
    assert parsed, f'Unsupported selector: {selector}'
    metric, matchers = parsed.groups()
    predicates = []
    for matcher in matchers.split(',') if matchers else []:
        parsed_matcher = re.fullmatch(r'([a-zA-Z_][a-zA-Z0-9_]*)(!=|=)("[^"]*")', matcher)
        assert parsed_matcher, f'Unsupported matcher: {matcher}'
        label, operator, value = parsed_matcher.groups()
        predicates.append((label, operator, json.loads(value)))
    selected = {
        tuple(sorted(labels.items())): value
        for labels, value in series
        if labels['__name__'] == metric
        and all(
            (labels.get(label, '') == expected) if operator == '=' else (labels.get(label, '') != expected)
            for label, operator, expected in predicates
        )
    }
    if average:
        return {(): sum(selected.values()) / len(selected)} if selected else {}
    return selected


@pytest.fixture
def listen_adapter_series():
    # Discovery previously accepted every job/namespace; averaging filtered only job.
    variants = [
        ({'namespace': 'prod-omi-backend'}, 10),
        ({'namespace': 'prod-omi-backend', 'listen_track': 'main'}, 20),
        ({'namespace': 'dev-omi-backend'}, 30),
        ({'namespace': 'other-backend', 'listen_track': 'control'}, 40),
        ({'namespace': 'other-backend', 'listen_track': ''}, 50),
        ({}, 60),
        ({'namespace': 'other-backend', 'job': 'other-scrape'}, 700),
        ({'namespace': 'prod-omi-backend', 'job': 'other-scrape', 'listen_track': 'main'}, 800),
        ({'__name__': 'unrelated_metric'}, 900),
    ]
    return [
        (
            {
                '__name__': 'backend_listen_active_ws_connections',
                'job': 'backend-listen-metrics',
                'pod': f'pod-{index}',
                **labels,
            },
            value,
        )
        for index, (labels, value) in enumerate(variants)
    ]


@pytest.mark.parametrize('canary_value', [None, 0, 1000], ids=['no-canary', 'idle-canaries', 'busy-canaries'])
def test_adapter_queries_preserve_old_results_except_canaries(listen_adapter_series, canary_value):
    adapter = yaml.safe_load(
        (ROOT / 'backend/charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml').read_text()
    )
    rule = next(
        rule
        for rule in adapter['rules']['external']
        if rule['name']['as'] == 'backend_listen_active_ws_connections_per_pod'
    )
    series = list(listen_adapter_series)
    if canary_value is not None:
        for index, (namespace, job) in enumerate(
            [
                ('prod-omi-backend', 'backend-listen-metrics'),
                ('other-backend', 'backend-listen-metrics'),
                ('other-backend', 'other-scrape'),
            ]
        ):
            series.append(
                (
                    {
                        '__name__': 'backend_listen_active_ws_connections',
                        'job': job,
                        'namespace': namespace,
                        'pod': f'canary-{index}',
                        'listen_track': 'canary',
                    },
                    canary_value,
                )
            )
    old_queries = {
        'seriesQuery': 'backend_listen_active_ws_connections',
        'metricsQuery': 'avg(backend_listen_active_ws_connections{job="backend-listen-metrics"})',
    }
    # Baseline values also prove the fixture exercises the old discovery/average distinction.
    assert len(_adapter_query_result(old_queries['seriesQuery'], listen_adapter_series)) == 8
    assert _adapter_query_result(old_queries['metricsQuery'], listen_adapter_series) == {(): 35}
    non_canaries = [(labels, value) for labels, value in series if labels.get('listen_track') != 'canary']
    for key, old_query in old_queries.items():
        old_result = _adapter_query_result(old_query, series)
        new_result = _adapter_query_result(rule[key], series)
        assert new_result == _adapter_query_result(old_query, non_canaries)
        if canary_value is None:
            assert new_result == old_result
        else:
            assert new_result != old_result


@pytest.mark.parametrize('image', ['gcr.io/based-hardware/backend:latest', 'gcr.io/based-hardware/backend:abc1234'])
def test_mutable_canary_image_rejected(image):
    with pytest.raises(ValueError):
        renderer.detach({}, image, 2, {})


@pytest.mark.skipif(shutil.which('helm') is None, reason='Helm render contract requires helm')
def test_live_control_snapshot_preserves_manual_runtime_overrides_and_is_not_mutated():
    control = renderer.render('prod', IMAGE, 2, {})
    control['metadata']['name'] = 'prod-omi-backend-listen'
    control['spec']['selector']['matchLabels'].pop('track')
    control['spec']['template']['metadata']['labels'].pop('track')
    container = control['spec']['template']['spec']['containers'][0]
    container['env'] = [
        {'name': 'STT_SERVICE_MODELS', 'value': 'live-reviewed-order'},
        {'name': 'STT_FAILOVER_RECOVERY_ENABLED', 'value': 'false'},
    ]
    container['resources']['limits']['memory'] = '4Gi'
    before = copy.deepcopy(control)
    candidate = renderer.render('prod', IMAGE, 2, {'STT_FAILOVER_RECOVERY_ENABLED': 'true'}, control)
    out = candidate['spec']['template']['spec']['containers'][0]
    assert out['resources']['limits']['memory'] == '4Gi'
    assert out['env'] == [
        {'name': 'STT_SERVICE_MODELS', 'value': 'live-reviewed-order'},
        {'name': 'STT_FAILOVER_RECOVERY_ENABLED', 'value': 'true'},
    ]
    assert control == before
    control['metadata']['namespace'] = 'dev-omi-backend'
    with pytest.raises(ValueError):
        renderer.render('prod', IMAGE, 2, {}, control)


def test_dev_manifest_has_no_shared_identity_or_state():
    policy, deployment = soak_manifest(IMAGE, 'fake', 16, 12, 'parakeet-window,soniox,modulate-velma-2', None)
    pod = {
        'metadata': {'namespace': 'dev-stt-soak', 'labels': {'app': 'live-stt-soak'}},
        'spec': deployment['spec']['template']['spec'],
    }
    validate_pod(pod)
    assert policy['spec']['egress'] == []
    assert policy['spec']['ingress'] == []
    assert not any('envFrom' in c for c in pod['spec']['containers'])
    pod['spec']['containers'][0]['env'].append({'name': 'SERVICE_ACCOUNT_JSON', 'value': 'unexpected'})
    with pytest.raises(ValueError):
        validate_pod(pod)
    pod['spec']['containers'][0]['env'][-1] = {
        'name': 'SERVICE_ACCOUNT_JSON',
        'valueFrom': {'secretKeyRef': {'name': 'shared', 'key': 'ADC'}},
    }
    with pytest.raises(ValueError):
        validate_pod(pod)


def test_pod_restart_detected_even_if_all_initial_counters_were_zero():
    pod = {
        'metadata': {'uid': 'same-pod'},
        'status': {'containerStatuses': [{'name': 'listen', 'restartCount': 0, 'containerID': 'container-before'}]},
    }
    before = pod_generation(pod)
    pod['status']['containerStatuses'][0].update(restartCount=1, containerID='container-after')
    assert pod_generation(pod) != before


@pytest.mark.parametrize(
    'key,value',
    [
        ('REDIS_DB_HOST', 'prod-redis'),
        ('GOOGLE_CLOUD_PROJECT', 'based-hardware'),
        ('FIRESTORE_EMULATOR_HOST', '10.0.0.1:8085'),
    ],
)
def test_soak_fails_closed_on_shared_state(key, value):
    pod = soak_manifest(IMAGE, 'fake', 2, 12, 'soniox,modulate-velma-2', None)[1]
    env = {e['name']: e.get('value', '') for e in pod['spec']['template']['spec']['containers'][0]['env']}
    env[key] = value
    with pytest.raises(ValueError):
        validate_environment(env)


@pytest.mark.parametrize(
    'url',
    [
        'https://api.omi.me',
        'https://api.omiapi.com',
        'http://localhost:8080',
        'http://127.0.0.1',
        'http://127.0.0.1:8080/?token=foo',
    ],
)
def test_soak_rejects_unreviewed_targets(url):
    with pytest.raises(ValueError):
        validate_target(url)


def test_paid_egress_blocks_metadata_and_private_networks():
    policy = soak_manifest(IMAGE, 'paid', 2, 12, 'soniox,modulate-velma-2', 'scoped-existing-keys')[0]
    assert '169.254.0.0/16' in policy['spec']['egress'][1]['to'][0]['ipBlock']['except']
    assert policy['spec']['egress'][1]['ports'] == [{'protocol': 'TCP', 'port': 443}]
    with pytest.raises(ValueError):
        soak_manifest(IMAGE, 'paid', 2, 12, 'soniox,modulate-velma-2', None)


def test_reporting_keeps_fallback_exhaustion_distinct_from_user_harm():
    text = '''omi_fallback_total{component="stt_live_session",outcome="exhausted"} 8
omi_live_stt_terminal_failures_total{phase="send",provider="soniox"} 2
omi_stt_replay_wall_seconds_count{source="parakeet",successor="soniox"} 9
omi_stt_replay_wall_seconds_bucket{source="parakeet",successor="soniox",le="0.1"} 3
process_resident_memory_bytes 1000
'''
    report = summarize({}, metric_samples(text))
    assert report['live_fallback_outcomes']['exhausted'] == 8
    assert report['totals']['omi_live_stt_terminal_failures_total'] == 2
    assert report['positive_replays_over_100ms_lower_bound'] == 6
    assert report['missing_metrics']
    assert report['gate'] == 'HOLD'
    assert summarize(metric_samples(text), metric_samples(text.replace(' 8', ' 1')))['counter_resets']


def test_registered_but_unobserved_terminal_counter_is_zero_not_missing():
    samples = metric_samples('''# HELP omi_live_stt_terminal_failures_total Terminal failures
# TYPE omi_live_stt_terminal_failures_total counter
# HELP omi_live_session_terminal_after_text_total Failures after text
# TYPE omi_live_session_terminal_after_text_total counter
''')
    report = summarize({}, samples)
    assert report['totals']['omi_live_stt_terminal_failures_total'] == 0
    assert report['totals']['omi_live_session_terminal_after_text_total'] == 0
    assert 'omi_live_stt_terminal_failures_total' not in report['missing_metrics']
    assert 'omi_stt_recovery_attempts_total' in report['missing_metrics']
    assert report['gate'] == 'HOLD'


def test_client_observes_early_terminal_even_after_text():
    async def exercise():
        async def peer(ws, _path):
            auth = json.loads(await ws.recv())
            assert auth['type'] == 'auth'
            await ws.send(json.dumps({'type': 'service_status', 'status': 'ready'}))
            await ws.recv()
            await ws.send(json.dumps([{'text': 'public synthetic'}]))
            await ws.send(json.dumps({'type': 'service_status', 'status': 'stt_failed'}))
            await ws.close(code=1011)

        async with serve(peer, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            return await session(f'http://127.0.0.1:{port}', 0, 0.2, 'local-only-auth-key', public_pcm())

    result = asyncio.run(exercise())
    assert result['started'] and result['ready'] and result['terminal_status']
    assert result['transcript_batches'] == 1
    assert result['client_terminated_failure']


def test_fake_peer_protocols_keep_real_transport_fault_scoped(monkeypatch):
    async def exercise():
        original_connect = websockets.connect
        async with serve(fake_provider, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            connections = ProviderConnections('fake', 0.05, 1)

            async def redirected(uri, **kwargs):
                return await original_connect(uri.replace('127.0.0.1:9090', f'127.0.0.1:{port}'), **kwargs)

            monkeypatch.setattr(websockets, 'connect', redirected)
            primary = await connections.connect('wss://stt-rt.soniox.com/transcribe-websocket')
            await primary.send(b'\x01\x00' * 16000)
            await asyncio.wait_for(primary.wait_closed(), timeout=1)
            assert primary.close_code == 1011 and connections.injected == 1
            successor = await connections.connect('wss://modulate-developer-apis.com/api/velma-2-stt-streaming')
            await successor.send(b'\x01\x00' * 16000)
            assert json.loads(await asyncio.wait_for(successor.recv(), timeout=1))['type'] == 'utterance'
            await successor.close()
            await connections.shutdown()

    asyncio.run(exercise())
