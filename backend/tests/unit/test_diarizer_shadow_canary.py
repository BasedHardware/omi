"""Render the real chart and follow every production route to its pod selector."""

from pathlib import Path
import subprocess
import asyncio
from types import SimpleNamespace

import pytest
import yaml

from scripts import diarizer_shadow_replay as replay
from scripts import render_diarizer_shadow_job as job

ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / 'backend/charts/diarizer'
DIGEST = 'sha256:' + 'a' * 64
RELEASE = 'prod-omi-diarizer-batch-canary'


def render(shadow, *overrides, release=None):
    args = [
        'helm',
        'template',
        release or (RELEASE if shadow else 'prod-omi-diarizer-batch'),
        str(CHART),
        '--namespace',
        'prod-omi-backend',
    ]
    for name in ('prod_omi_diarizer_values.yaml', 'prod_omi_diarizer_batch_values.yaml'):
        args += ['-f', str(CHART / name)]
    if shadow:
        args += ['-f', str(CHART / 'prod_omi_diarizer_batch_canary_values.yaml')]
    args += ['--set-string', 'image.digest=' + DIGEST]
    for override in overrides:
        # Helm merges --set-string AFTER --set, regardless of argv ordering.
        # Digest mutations must replace the string pin rather than be masked by it.
        args += ['--set-string' if override.startswith('image.') else '--set', override]
    return subprocess.run(args, capture_output=True, text=True)


def objects(shadow):
    result = render(shadow)
    assert result.returncode == 0, result.stderr
    return [o for o in yaml.safe_load_all(result.stdout) if o]


def selects(selector, labels):
    return all(labels.get(key) == value for key, value in selector.items())


def test_prod_services_gateway_and_hpa_cannot_reach_shadow():
    prod, shadow = objects(False), objects(True)
    [deployment] = [o for o in shadow if o['kind'] == 'Deployment']
    pod_labels = deployment['spec']['template']['metadata']['labels']
    services = {o['metadata']['name']: o for o in prod if o['kind'] == 'Service'}
    assert len(services) == 2  # ClusterIP and the ILB Gateway backend.
    for service in services.values():
        assert service['spec']['selector']
        assert not selects(service['spec']['selector'], pod_labels)
    routes = [o for o in prod if o['kind'] == 'HTTPRoute']
    assert routes
    for route in routes:
        for rule in route['spec']['rules']:
            for backend in rule['backendRefs']:
                assert not selects(services[backend['name']]['spec']['selector'], pod_labels)
    for controller in [o for o in prod if o['kind'] == 'Deployment']:
        assert not selects(controller['spec']['selector']['matchLabels'], pod_labels)
    for hpa in [o for o in prod if o['kind'] == 'HorizontalPodAutoscaler']:
        assert hpa['spec']['scaleTargetRef']['name'] != deployment['metadata']['name']
    assert not any(
        o['kind']
        in {
            'HTTPRoute',
            'Ingress',
            'HorizontalPodAutoscaler',
            'PodMonitoring',
            'BackendConfig',
            'GCPBackendPolicy',
            'HealthCheckPolicy',
        }
        for o in shadow
    )
    [service] = [o for o in shadow if o['kind'] == 'Service']
    assert service['spec']['type'] == 'ClusterIP'
    assert 'annotations' not in service['metadata']  # no NEG/ILB side effects
    assert selects(service['spec']['selector'], pod_labels)
    for controller in [o for o in prod if o['kind'] == 'Deployment']:
        assert not selects(service['spec']['selector'], controller['spec']['template']['metadata']['labels'])
    assert deployment['spec']['replicas'] == 1
    container = deployment['spec']['template']['spec']['containers'][0]
    assert container['image'] == 'gcr.io/based-hardware/diarizer@' + DIGEST
    prod_pod = next(o for o in prod if o['kind'] == 'Deployment')['spec']['template']['spec']
    canary_pod = deployment['spec']['template']['spec']
    for key in ('nodeSelector', 'tolerations', 'affinity'):
        assert canary_pod[key] == prod_pod[key]
    assert container['resources'] == prod_pod['containers'][0]['resources']
    # Production route, HPA cap, monitoring and fallback remain intact.
    assert next(o for o in prod if o['kind'] == 'HorizontalPodAutoscaler')['spec']['maxReplicas'] == 5
    assert len([o for o in prod if o['kind'] == 'Deployment']) == 2
    assert next(o for o in prod if o['kind'] == 'BackendConfig')


@pytest.mark.parametrize(
    'override',
    [
        'image.digest=',
        'image.digest=sha256:bad',
        'image.tag=mutable',
        'autoscaling.enabled=true',
        'warmFallback.enabled=true',
        'replicaCount=2',
        'maintenanceMode=true',
        'gateway.enabled=true',
        'ingress.enabled=true',
        'backendConfig.enabled=true',
        'podMonitoring.enabled=true',
        'service.type=LoadBalancer',
        'fullnameOverride=prod-omi-diarizer-batch',
        r'podLabels.omi\.ai/diarizer-batch-route=prod',
        r'service.selectorLabels.omi\.ai/diarizer-batch-route=prod',
        r'podLabels.app\.kubernetes\.io/instance=prod-omi-diarizer-batch',
    ],
)
def test_unsafe_shadow_override_fails_render(override):
    assert render(True, override).returncode != 0


def test_shadow_cannot_install_over_production_release():
    assert render(True, release='prod-omi-diarizer-batch').returncode != 0


def test_replay_job_is_bounded_public_only_and_requires_pins():
    result = job.render('gcr.io/based-hardware/backend@' + DIGEST, 'gcr.io/based-hardware/diarizer@' + DIGEST)
    config, manifest = result['items']
    assert config['immutable'] is True
    assert 'bench_diarizer_batch.py' in config['data']
    spec = manifest['spec']
    assert spec['backoffLimit'] == 0
    assert spec['activeDeadlineSeconds'] == 93600
    pod = spec['template']['spec']
    assert pod['automountServiceAccountToken'] is False
    assert not any('secret' in json_key.lower() for json_key in pod)
    assert len(pod['containers']) == 1
    assert pod['containers'][0]['command'] == ['python', '/replay/diarizer_shadow_replay.py']
    with pytest.raises(ValueError, match='digest'):
        job.render('gcr.io/based-hardware/backend:latest', 'gcr.io/based-hardware/diarizer@' + DIGEST)


@pytest.mark.parametrize(
    'rtf,peak,outcome,passed',
    [
        (0.059, 1.62, 'ok', True),
        (0.068, 1.62, 'ok', False),
        (None, 1.62, 'ok', False),
        (float('nan'), 1.62, 'ok', False),
        (0.059, 2.01, 'ok', False),
        (0.059, 1.62, 'failed', False),
    ],
)
def test_replay_gates_fail_closed_without_claiming_upstream_coverage(rtf, peak, outcome, passed):
    summary = replay.summarize([dict(inference_rtf=rtf, outcome=outcome)], peak)
    assert summary['replay_passed'] is passed
    assert summary['incomplete_coverage']['measured'] is False
    assert summary['incomplete_coverage']['share'] is None
    assert summary['full_qualification'].startswith('PENDING')


@pytest.mark.parametrize('outcome', ['ok', 'failed'])
def test_replay_drives_fixed_shadow_and_stops_after_error_or_soak(monkeypatch, tmp_path, capsys, outcome):
    import json

    (tmp_path / 'corpus.pcm').write_bytes(b'\0\0' * 16000)
    monkeypatch.setattr(replay.bench, 'prepare', lambda _: None)
    monkeypatch.setattr(replay.bench, 'load_corpus', lambda _: {'sha256': 'public-fixture', 'source': 'OpenSLR'})
    monkeypatch.setattr(replay.bench, 'MINUTES', (5,))
    snapshots = iter([({}, 1.62), ({}, 1.62), ({'ok': 1}, 1.62), ({'ok': 1}, 1.62)])

    def metrics(base):
        assert base == replay.BASE
        return next(snapshots)

    calls = []
    instant = [0.0]
    monkeypatch.setattr(replay, 'time', SimpleNamespace(monotonic=lambda: instant[0]))

    async def wave(pcm, concurrency, timeout):
        calls.append(concurrency)
        instant[0] += 1  # finish beyond this test's shortened soak
        return dict(
            app_peak_gib_sampled=1.62,
            requests=[
                dict(
                    outcome=outcome,
                    audio_seconds=1,
                    wall_seconds=0.07,
                    inference_rtf=0.059 if outcome == 'ok' else None,
                )
            ],
        )

    monkeypatch.setattr(replay, 'metrics', metrics)
    monkeypatch.setattr(replay, 'observed_wave', wave)
    args = SimpleNamespace(
        corpus=tmp_path, target_image='digest', client_image='digest', soak_hours=0.000003, timeout=1200, interval=1
    )
    assert asyncio.run(replay.run(args)) == (0 if outcome == 'ok' else 1)
    assert calls == [1]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    summary = events[-1]
    assert summary['event'] == 'summary'
    assert summary['requests'] == 1
    assert summary['incomplete_coverage']['share'] is None
