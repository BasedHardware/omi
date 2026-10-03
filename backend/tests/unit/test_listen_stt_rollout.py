"""Rollout ownership/isolation contracts for the #20391 careful canary."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import shutil
from pathlib import Path

import pytest
import websockets
from websockets.legacy.server import serve

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
