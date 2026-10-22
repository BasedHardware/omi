"""Fleet contracts: stockout-safe placement, conservative scaling and retirement."""

from functools import lru_cache
from copy import deepcopy
import io
import importlib.util
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
CHARTS = ROOT / 'backend/charts'
spec = importlib.util.spec_from_file_location(
    'audit_audio_fleet_callers', ROOT / 'backend/scripts/audit_audio_fleet_callers.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@lru_cache(maxsize=None)
def render_resources(chart, environment='prod', git_ref=None):
    with TemporaryDirectory() as scratch:
        directory = CHARTS / chart
        if git_ref is not None:
            archive = subprocess.check_output(['git', 'archive', git_ref, f'backend/charts/{chart}'], cwd=ROOT)
            with tarfile.open(fileobj=io.BytesIO(archive)) as source:
                source.extractall(scratch, filter='data')
            directory = Path(scratch) / 'backend/charts' / chart
        output = subprocess.check_output(
            [
                'helm',
                'template',
                f'{environment}-omi-{chart}',
                str(directory),
                '-f',
                str(directory / f'{environment}_omi_{chart.replace("-", "_")}_values.yaml'),
                '--set-string',
                'image.tag=fleet-contract-test',
            ],
            text=True,
        )
    return tuple(obj for obj in yaml.load_all(output, Loader=yaml.CSafeLoader) if obj)


def render(chart, environment='prod'):
    return {obj['kind']: obj for obj in render_resources(chart, environment)}


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_parakeet_helm_apply_changes_only_hpa_against_origin_main(environment):
    current = deepcopy(render_resources('parakeet', environment))
    baseline = deepcopy(render_resources('parakeet', environment, git_ref='origin/main'))
    allowed = {'PARAKEET_PACKING_ENABLED', 'PARAKEET_EXPLICIT_CUDA_GRAPHS'}
    for objects, require_flags in ((current, True), (baseline, False)):
        deployment = next(obj for obj in objects if obj['kind'] == 'Deployment')
        container = next(c for c in deployment['spec']['template']['spec']['containers'] if c['name'] == 'parakeet')
        flags = [entry for entry in container['env'] if entry['name'] in allowed]
        # Only these exact literals may be added; duplicate/valueFrom/true entries fail.
        assert len(flags) == len({entry['name'] for entry in flags})
        assert all(entry == {'name': entry['name'], 'value': 'false'} for entry in flags)
        if require_flags:
            assert {entry['name'] for entry in flags} == allowed
        container['env'] = [entry for entry in container['env'] if entry['name'] not in allowed]
        # The language gate's one Ingress path may be added, and only onto the transcribe backend.
        ingress = next(obj for obj in objects if obj['kind'] == 'Ingress')
        paths = ingress['spec']['rules'][0]['http']['paths']
        gate = [entry for entry in paths if entry['path'] == '/v2/language']
        transcribe = next(entry for entry in paths if entry['path'] == '/v2/transcribe')
        assert len(gate) == 1 if require_flags else len(gate) <= 1
        assert all(entry == dict(transcribe, path='/v2/language') for entry in gate)
        ingress['spec']['rules'][0]['http']['paths'] = [entry for entry in paths if entry['path'] != '/v2/language']
    # All remaining pod-template fields and non-HPA objects must match main exactly.
    stable = lambda objects: {
        (obj['kind'], obj['metadata']['name']): obj for obj in objects if obj['kind'] != 'HorizontalPodAutoscaler'
    }
    assert stable(current) == stable(baseline)


@pytest.mark.parametrize(
    'mutation', ['enable_flag', 'duplicate_flag', 'other_env', 'image', 'affinity', 'gate_path_backend', 'other_path']
)
def test_parakeet_template_gate_rejects_changes_beside_dark_flags(monkeypatch, mutation):
    original_render = render_resources

    def changed_render(chart, environment='prod', git_ref=None):
        objects = deepcopy(original_render(chart, environment, git_ref))
        if git_ref is None:
            deployment = next(obj for obj in objects if obj['kind'] == 'Deployment')
            pod = deployment['spec']['template']['spec']
            container = next(c for c in pod['containers'] if c['name'] == 'parakeet')
            if mutation == 'enable_flag':
                next(e for e in container['env'] if e['name'] == 'PARAKEET_PACKING_ENABLED')['value'] = 'true'
            elif mutation == 'duplicate_flag':
                container['env'].append({'name': 'PARAKEET_PACKING_ENABLED', 'value': 'false'})
            elif mutation == 'other_env':
                container['env'].append({'name': 'UNREVIEWED_SETTING', 'value': 'false'})
            elif mutation == 'image':
                container['image'] = 'unreviewed-image:latest'
            elif mutation == 'affinity':
                pod['affinity'] = {}
            else:
                ingress = next(obj for obj in objects if obj['kind'] == 'Ingress')
                paths = ingress['spec']['rules'][0]['http']['paths']
                if mutation == 'gate_path_backend':
                    gate = next(entry for entry in paths if entry['path'] == '/v2/language')
                    gate['backend'] = {'service': {'name': 'unreviewed-service', 'port': {'number': 8080}}}
                else:
                    paths.append(dict(paths[0], path='/v9/unreviewed'))
        return objects

    monkeypatch.setitem(globals(), 'render_resources', changed_render)
    with pytest.raises(AssertionError):
        test_parakeet_helm_apply_changes_only_hpa_against_origin_main('prod')


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_parakeet_callers_stay_on_main_bindings_until_separate_qualification(environment):
    baseline = yaml.load(
        subprocess.check_output(['git', 'show', 'origin/main:backend/deploy/runtime_env.yaml'], cwd=ROOT),
        Loader=yaml.CSafeLoader,
    )['environments'][environment]
    current = manifest()['environments'][environment]
    for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        assert (
            current['cloud_run']['services'][service]['env']['HOSTED_PARAKEET_API_URL']
            == baseline['cloud_run']['services'][service]['env']['HOSTED_PARAKEET_API_URL']
        )
    for chart in ('backend-listen', 'pusher'):
        current_env = render(chart, environment)['Deployment']['spec']['template']['spec']['containers'][0]['env']
        main_values = yaml.load(
            subprocess.check_output(
                [
                    'git',
                    'show',
                    f'origin/main:backend/charts/{chart}/{environment}_omi_{chart.replace("-", "_")}_values.yaml',
                ],
                cwd=ROOT,
            ),
            Loader=yaml.CSafeLoader,
        )
        binding = lambda env: next(entry for entry in env if entry['name'] == 'HOSTED_PARAKEET_API_URL')
        assert binding(current_env) == binding(main_values['env'])


@lru_cache(maxsize=1)
def manifest():
    return yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)


@pytest.mark.parametrize('chart', ['backend-listen', 'pusher', 'parakeet'])
def test_prod_pool_placement_preserves_current_cpu_pools(chart):
    objects = render(chart)
    pod = objects['Deployment']['spec']['template']['spec']
    assert not pod.get('nodeSelector')
    terms = pod['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms']
    expressions = terms[0]['matchExpressions']
    labels = {e['key']: e['values'] for e in expressions}
    assert labels['service'] == [chart]
    assert labels['env'] == ['prod']
    assert 'cloud.google.com/gke-nodepool' not in labels
    if chart == 'parakeet':
        (constraint,) = pod['topologySpreadConstraints']
        assert constraint['whenUnsatisfiable'] == 'ScheduleAnyway'
        assert constraint['topologyKey'] == 'topology.kubernetes.io/zone'
        assert constraint['labelSelector']['matchLabels'] == objects['Deployment']['spec']['selector']['matchLabels']
        assert labels == {'service': ['parakeet'], 'env': ['prod']}
    else:
        assert 'topologySpreadConstraints' not in pod
        assert not pod.get('tolerations')
        expected = {'service': [chart], 'env': ['prod']}
        expected.update({'type': ['high-cpu']} if chart == 'backend-listen' else {'version': ['v3']})
        assert labels == expected


def test_parakeet_scales_conservatively_without_relaxing_admission():
    objects = render('parakeet')
    hpa = objects['HorizontalPodAutoscaler']['spec']
    assert hpa['minReplicas'] == 3
    assert hpa['maxReplicas'] == 12
    assert hpa['behavior']['scaleDown']['stabilizationWindowSeconds'] == 900
    metrics = hpa['metrics']
    assert next(m['pods']['target']['averageValue'] for m in metrics if m['type'] == 'Pods') == '2'
    external = {
        m['external']['metric']['name']: m['external']['target']['value'] for m in metrics if m['type'] == 'External'
    }
    assert external == {'parakeet_gpu_utilization': '35', 'parakeet_request_latency_p99': '3'}
    env = {e['name']: e.get('value') for e in objects['Deployment']['spec']['template']['spec']['containers'][0]['env']}
    assert env['PARAKEET_MAX_INFLIGHT'] == '1'


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_serving_charts_have_no_deepgram_callers(environment):
    for chart in ('backend-listen', 'pusher'):
        pod = render(chart, environment)['Deployment']['spec']['template']['spec']
        assert audit.classify(pod['containers'][0]['env']) == []


@pytest.mark.parametrize(
    'binding',
    [
        {'name': 'DEEPGRAM_SELF_HOSTED_ENABLED', 'value': 'true'},
        {'name': 'OTHER_ENDPOINT', 'value': 'https://dg.omi.me/v1/listen'},
        {'name': 'OTHER_ENDPOINT', 'value': 'http://deepgram-api-external:8080'},
        {'name': 'OTHER_ENDPOINT', 'value': 'http://deepgram-engine-internal:8080'},
        {'name': 'OTHER_ENDPOINT', 'value': 'http://deepgram-api.prod-omi-dg-self-hosted.svc:8080'},
        {'name': 'DEEPGRAM_SELF_HOSTED_URL', 'valueFrom': {'secretKeyRef': {'name': 'opaque', 'key': 'url'}}},
    ],
)
def test_runtime_audit_blocks_retired_or_unresolved_bindings_without_printing_values(binding):
    findings = audit.classify([binding])
    assert findings
    assert binding.get('value', 'unprinted-value') not in str(findings)


def test_runtime_audit_accepts_cloud_and_blocks_uninspected_envfrom():
    assert audit.classify([{'name': 'ENDPOINT', 'value': 'https://api.deepgram.com'}]) == []
    assert audit.classify([], [{'secretRef': {'name': 'opaque'}}]) == ['unresolved_envFrom']


def test_configmap_envfrom_is_resolved_and_direct_bindings_take_precedence(monkeypatch):
    monkeypatch.setattr(
        audit,
        'read_json',
        lambda _: {
            'data': {
                'DEEPGRAM_SELF_HOSTED_ENABLED': 'true',
                'ENDPOINT': 'https://api.deepgram.com',
            }
        },
    )
    env, unresolved = audit.effective_env(
        ['kubectl', '--context=explicit'],
        'prod',
        {
            'envFrom': [{'configMapRef': {'name': 'config'}}],
            'env': [{'name': 'DEEPGRAM_SELF_HOSTED_ENABLED', 'value': 'false'}],
        },
        {},
    )
    assert audit.classify(env, unresolved) == []


def test_cloud_run_manifest_forbids_stale_self_hosted_bindings_in_both_environments():
    runtime = manifest()
    for environment in ('dev', 'prod'):
        services = runtime['environments'][environment]['cloud_run']['services']
        for name in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
            assert {'DEEPGRAM_SELF_HOSTED_ENABLED', 'DEEPGRAM_SELF_HOSTED_URL'} <= set(services[name]['forbidden_env'])


def test_optional_missing_configmap_is_not_an_unresolved_runtime_binding(monkeypatch):
    monkeypatch.setattr(audit, 'read_json', lambda _: None)
    container = {
        'envFrom': [{'configMapRef': {'name': 'absent', 'optional': True}}],
        'env': [
            {'name': 'ABSENT', 'valueFrom': {'configMapKeyRef': {'name': 'absent', 'key': 'absent', 'optional': True}}}
        ],
    }
    assert audit.effective_env(['kubectl', '--context=explicit'], 'prod', container, {}) == ([], [])
    container['env'][0]['valueFrom']['configMapKeyRef']['optional'] = False
    with pytest.raises(RuntimeError):
        audit.effective_env(['kubectl', '--context=explicit'], 'prod', container, {})
