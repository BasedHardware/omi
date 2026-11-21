"""Deletion fences for the lead-only streaming capacity retirement tool."""

import importlib.util
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/retire_streaming_gpu.py'
spec = importlib.util.spec_from_file_location('retire_streaming_gpu', SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def node(pool='parakeet-pool-v2'):
    return {'metadata': {'name': 'test-node', 'labels': {'cloud.google.com/gke-nodepool': pool}}}


def pod(app='parakeet', owner='prod-omi-parakeet-123', kind='ReplicaSet', namespace='prod-omi-backend'):
    return {
        'metadata': {
            'namespace': namespace,
            'labels': {'app.kubernetes.io/name': app},
            'ownerReferences': [{'kind': kind, 'name': owner}],
        },
        'spec': {'nodeName': 'test-node'},
    }


@pytest.mark.parametrize(
    'foreign',
    [
        pod('batch-pipeline-worker'),
        pod('diarizer'),
        pod(owner='unrelated-123'),
        pod(namespace='other'),
        pod(kind='Job'),
    ],
)
def test_never_delete_a_borrowed_pool_or_trust_a_spoofed_streaming_label(foreign):
    with pytest.raises(RuntimeError, match='non-retired workload'):
        tool.assert_no_foreign_pods([node()], [foreign])


def test_drain_requires_streaming_pods_to_leave_but_permits_system_daemons():
    tool.assert_no_foreign_pods([node()], [pod()])
    with pytest.raises(RuntimeError, match='non-retired workload'):
        tool.assert_no_foreign_pods([node()], [pod()], drained=True)
    tool.assert_no_foreign_pods([node()], [pod('gpu-driver', kind='DaemonSet')], drained=True)


@pytest.mark.parametrize(
    'volume', [{'persistentVolumeClaim': {'claimName': 'audio'}}, {'hostPath': {'path': '/audio'}}]
)
def test_persistent_streaming_audio_blocks_even_workload_scale_down(volume):
    p = pod()
    p['spec']['volumes'] = [volume]
    with pytest.raises(RuntimeError, match='storage'):
        tool.assert_no_foreign_pods([node()], [p])


def test_pending_batch_targeting_a_borrowed_pool_also_blocks_deletion():
    pending = pod('batch-pipeline-worker')
    pending['spec'] = {'nodeSelector': {'cloud.google.com/gke-nodepool': 'parakeet-pool-v2'}}
    with pytest.raises(RuntimeError, match='non-retired workload'):
        tool.assert_no_foreign_pods([], [pending])


@pytest.mark.parametrize(
    'pool',
    [
        'batch-pipeline-pool',
        'batch-pipeline-pool-spot',
        'diarizer-pool',
        'diarizer-batch-pool',
        'diarizer-batch-pool-v2',
        'vad-pool',
        'vad-pool-v2',
    ],
)
def test_batch_and_diarizer_capacity_is_outside_deletion_allowlist(pool):
    assert tool.selected_nodes([node(pool)]) == {}


def test_second_run_preserves_original_rollback_capacity(tmp_path):
    path = tmp_path / 'replicas.json'
    tool.save_once(path, {'replicas': 4})
    tool.save_once(path, {'replicas': 0})
    assert path.read_text().strip() == '{\n  "replicas": 4\n}'


def test_missing_warm_baseline_blocks_before_any_cloud_call(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, 'execute', lambda *args: pytest.fail('cloud called without rollback baseline'))
    with pytest.raises(RuntimeError, match='Positive rollback baseline missing'):
        tool.apply(tmp_path)


@pytest.mark.parametrize(
    'labels', [{}, {'service': 'batch-pipeline', 'env': 'prod'}, {'service': 'parakeet', 'env': 'dev'}]
)
def test_empty_but_repurposed_or_unowned_pool_is_also_preserved(labels):
    with pytest.raises(RuntimeError, match='ownership is unknown'):
        tool.assert_pool_role('parakeet-pool-v2', {'config': {'labels': labels}})


def test_exclusive_streaming_pool_role_is_admitted():
    tool.assert_pool_role('parakeet-pool-v2', {'config': {'labels': {'service': 'parakeet', 'env': 'prod'}}})


@pytest.mark.parametrize(
    'spec,expected',
    [
        ({'minNodeCount': 1, 'maxNodeCount': 3}, ['--min-nodes=0', '--max-nodes=0']),
        ({'totalMinNodeCount': 0, 'totalMaxNodeCount': 10}, ['--total-min-nodes=0', '--total-max-nodes=0']),
    ],
)
def test_zero_cap_preserves_regional_or_per_zone_autoscaling_scope(spec, expected):
    assert tool.autoscaling_bounds({'autoscaling': spec}, zero=True) == expected
    assert tool.autoscaling_bounds({'autoscaling': spec})[-1].endswith(
        str(spec.get('maxNodeCount', spec.get('totalMaxNodeCount')))
    )


@pytest.mark.parametrize('mutation', ['none', 'missing', 'gap', 'nonzero', 'truncated'])
def test_legacy_ingress_deletion_needs_a_complete_24h_zero_metric_window(mutation):
    start = datetime(2026, 11, 3, tzinfo=timezone.utc)
    end = start + timedelta(hours=24)
    points = [
        {'interval': {'endTime': (start + timedelta(minutes=i + 1)).isoformat()}, 'value': {'int64Value': '0'}}
        for i in range(1440)
    ]
    if mutation == 'missing':
        points = []
    elif mutation == 'gap':
        del points[500]
    elif mutation == 'nonzero':
        points[100]['value']['int64Value'] = '1'
    elif mutation == 'truncated':
        points = points[-60:]
    assert tool.complete_zero_window(points, start, end) is (mutation == 'none')


@pytest.mark.parametrize('proven', [False, True])
def test_legacy_cleanup_preserves_ingress_until_metric_gate_passes(tmp_path, monkeypatch, proven):
    ingress = {
        'apiVersion': 'networking.k8s.io/v1',
        'kind': 'Ingress',
        'metadata': {'name': 'deepgram-api-ingress'},
        'spec': {},
    }
    deletes = []

    def kube(*args):
        if args[:2] == ('get', 'deployments'):
            return {'items': []}
        if args[:2] == ('get', 'ingress'):
            return {} if ('ingress', 'deepgram-api-ingress') in deletes else ingress
        if args[0] == 'delete':
            deletes.append((args[1], args[2]))
        return {}

    monkeypatch.setattr(tool, 'legacy_kubectl', kube)
    monkeypatch.setattr(
        tool, 'legacy_traffic_proof', lambda _: {'zero_proven': proven, 'reason': 'test', 'from': 'start', 'to': 'end'}
    )
    tool.retire_legacy_deepgram(tmp_path)
    assert ('hpa', 'deepgram-api-hpa') in deletes
    assert ('hpa', 'deepgram-engine-hpa') in deletes
    assert (('ingress', 'deepgram-api-ingress') in deletes) is proven


def test_default_plan_runs_without_cloud_or_kubernetes_tools(monkeypatch):
    monkeypatch.setenv('PATH', '/no-tools')
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'PLAN ONLY' in result.stdout and 'No commands executed' in result.stdout


def test_apply_without_explicit_lead_gates_cannot_reach_cloud(monkeypatch):
    monkeypatch.setenv('PATH', '/no-tools')
    result = subprocess.run([sys.executable, str(SCRIPT), '--apply'], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'requires --caller-drain-approved' in result.stderr


@pytest.mark.parametrize('tier', ['', 'ro-prod', 'ro-dev', 'human', 'dev-operator'])
def test_apply_refuses_default_human_and_other_tiers_before_cloud(monkeypatch, tier):
    monkeypatch.setenv('PATH', '/no-tools')
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            '--apply',
            '--caller-drain-approved',
            '--host-writers-retired',
            '--borrowed-pools-reviewed',
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert 'approved prod-operator' in result.stderr


def guard_script_cm():
    script = tool.GUARD_SCRIPT.read_text()
    return {
        'metadata': {
            'name': tool.GUARD + '-script',
            'annotations': {tool.GUARD_SCRIPT_HASH_ANNOTATION: hashlib.sha256(script.encode()).hexdigest()},
        },
        'data': {'guard.py': script},
    }


def retired_guard(flag='true', *, suspended=False):
    env = [] if flag is None else [{'name': 'PARAKEET_SUSPENDED', 'value': flag}]
    pod_spec = {
        'containers': [
            {
                'name': 'guard',
                'env': env,
                'command': ['python3', '/guard/guard.py'],
                'volumeMounts': [{'name': 'script', 'mountPath': '/guard', 'readOnly': True}],
            }
        ],
        'volumes': [{'name': 'script', 'configMap': {'name': tool.GUARD + '-script', 'defaultMode': 420}}],
    }
    template = {'metadata': {'annotations': guard_script_cm()['metadata']['annotations']}, 'spec': pod_spec}
    return {'spec': {'suspend': suspended, 'jobTemplate': {'spec': {'template': template}}}}


def guard_role(*verbs):
    return {'rules': [{'resources': ['horizontalpodautoscalers'], 'verbs': list(verbs)}]}


def guard_job(flag):
    return {'spec': retired_guard(flag)['spec']['jobTemplate']['spec']}


@pytest.mark.parametrize('suspended', [False, True])
@pytest.mark.parametrize('flag', ['true', 'false', None])
def test_retirement_requires_running_cronjob_and_parakeet_skip(flag, suspended):
    guard = retired_guard(flag, suspended=suspended)
    if suspended:
        with pytest.raises(RuntimeError, match='must not be suspended'):
            tool.assert_parakeet_guard_retired(guard, guard_role('get'), [], guard_script_cm())
    elif flag == 'true':
        tool.assert_parakeet_guard_retired(guard, guard_role('get'), [], guard_script_cm())
    else:
        with pytest.raises(RuntimeError, match='PARAKEET_SUSPENDED=true'):
            tool.assert_parakeet_guard_retired(guard, guard_role('get'), [], guard_script_cm())


@pytest.mark.parametrize('flag', ['true', 'false', None])
def test_active_batch_observer_is_allowed_but_pre_retirement_guard_job_blocks(flag):
    jobs = [guard_job(flag)]
    if flag == 'true':
        tool.assert_parakeet_guard_retired(retired_guard(), guard_role('get'), jobs, guard_script_cm())
    else:
        with pytest.raises(RuntimeError, match='pre-retirement Parakeet guard Jobs'):
            tool.assert_parakeet_guard_retired(retired_guard(), guard_role('get'), jobs, guard_script_cm())


def test_parakeet_skip_does_not_bypass_the_hpa_write_permission_fence():
    with pytest.raises(RuntimeError, match='HPA write permission'):
        tool.assert_parakeet_guard_retired(retired_guard(), guard_role('get', 'patch'), [], guard_script_cm())


@pytest.mark.parametrize('fault', [None, 'active-job', 'suspended', 'stale-script'])
def test_apply_checks_guard_before_reaching_capacity_changes(tmp_path, monkeypatch, fault):
    for name in tool.DEPLOYMENTS:
        tool.save_once(tmp_path / f'{name}-replicas.json', {'replicas': 4})
    guard = retired_guard(suspended=fault == 'suspended')
    script_cm = guard_script_cm()
    if fault == 'stale-script':
        script_cm['data']['guard.py'] = '# Old script ignores PARAKEET_SUSPENDED\n'
    guard['status'] = {'active': [{'name': 'existing-guard-job'}]}
    calls = []

    def kube(*args):
        calls.append(args)
        assert args[0] == 'get', 'guard qualification must precede every capacity write'
        if args[1] == 'deployments':
            return {'items': []}
        if args[1] == 'cronjob':
            return guard
        if args[1] == 'role':
            return guard_role('get')
        if args[1] == 'job':
            assert args[2] == 'existing-guard-job'
            return guard_job(None if fault == 'active-job' else 'true')
        if args[1] == 'cm':
            assert args[2] == tool.GUARD + '-script'
            return script_cm
        if args[1] == 'deployment':
            raise RuntimeError('qualified guard reached capacity reader')
        pytest.fail(f'unexpected Kubernetes read: {args}')

    monkeypatch.setattr(tool, 'kubectl', kube)
    monkeypatch.setattr(tool, 'assert_callers', lambda _: None)
    monkeypatch.setattr(tool, 'assert_cloud_run', lambda: None)
    monkeypatch.setattr(tool, 'cluster_state', lambda: ([], []))
    error = {
        None: 'qualified guard reached capacity reader',
        'active-job': 'pre-retirement Parakeet guard Jobs',
        'suspended': 'must not be suspended',
        'stale-script': 'reviewed guard script ConfigMap',
    }[fault]
    with pytest.raises(RuntimeError, match=error):
        tool.apply(tmp_path)
    assert ('get', 'job', 'existing-guard-job', '-o', 'json') in calls
    assert ('get', 'cm', tool.GUARD + '-script', '-o', 'json') in calls
    assert any(args[1] == 'deployment' for args in calls) is (fault is None)


@pytest.mark.parametrize(
    'fault', ['missing-script', 'old-script', 'old-self-consistent-hash', 'missing-hash', 'wrong-name']
)
def test_retirement_checks_actual_configmap_content_against_reviewed_script(fault):
    cm = guard_script_cm()
    if fault == 'missing-script':
        cm['data'] = {}
    elif fault in {'old-script', 'old-self-consistent-hash'}:
        cm['data']['guard.py'] = '# ignores PARAKEET_SUSPENDED\n'
        if fault == 'old-self-consistent-hash':
            cm['metadata']['annotations'][tool.GUARD_SCRIPT_HASH_ANNOTATION] = hashlib.sha256(
                cm['data']['guard.py'].encode()
            ).hexdigest()
    elif fault == 'missing-hash':
        cm['metadata']['annotations'] = {}
    else:
        cm['metadata']['name'] = 'unmounted-script'
    with pytest.raises(RuntimeError, match='reviewed guard script ConfigMap'):
        tool.assert_parakeet_guard_retired(retired_guard(), guard_role('get'), [], cm)


@pytest.mark.parametrize('target', ['cronjob', 'active-job'])
@pytest.mark.parametrize(
    'fault',
    [
        'missing-hash',
        'old-hash',
        'other-configmap',
        'remapped-key',
        'other-mount',
        'subpath',
        'shadowed-script',
        'other-command',
    ],
)
def test_retirement_requires_reviewed_script_to_be_mounted_by_each_template(target, fault):
    guard, job = retired_guard(), guard_job('true')
    template = guard['spec']['jobTemplate']['spec']['template'] if target == 'cronjob' else job['spec']['template']
    pod_spec = template['spec']
    container = pod_spec['containers'][0]
    if fault == 'missing-hash':
        template['metadata']['annotations'] = {}
    elif fault == 'old-hash':
        template['metadata']['annotations'][tool.GUARD_SCRIPT_HASH_ANNOTATION] = '0' * 64
    elif fault == 'other-configmap':
        pod_spec['volumes'][0]['configMap']['name'] = 'old-script'
    elif fault == 'remapped-key':
        pod_spec['volumes'][0]['configMap']['items'] = [{'key': 'old.py', 'path': 'guard.py'}]
    elif fault == 'other-mount':
        container['volumeMounts'][0]['name'] = 'old-script'
    elif fault == 'subpath':
        container['volumeMounts'][0]['subPath'] = 'old-script'
    elif fault == 'shadowed-script':
        container['volumeMounts'].append({'name': 'old-script', 'mountPath': '/guard/guard.py'})
    else:
        container['command'] = ['python3', '/old/guard.py']
    error = 'reviewed script mount/hash' if target == 'cronjob' else 'pre-retirement Parakeet guard Jobs'
    with pytest.raises(RuntimeError, match=error):
        tool.assert_parakeet_guard_retired(guard, guard_role('get'), [job], guard_script_cm())


@pytest.mark.parametrize('retired', [True, False])
def test_retirement_fence_accepts_only_retired_live_rendered_chart(retired):
    chart = tool.GUARD_SCRIPT.parents[1]
    command = [
        'helm',
        'template',
        tool.GUARD,
        str(chart),
        '--namespace',
        tool.NAMESPACE,
        '-f',
        str(chart / 'prod_omi_incluster_guards_values.yaml'),
        '--set',
        f'parakeetSuspended={str(retired).lower()}',
    ]
    docs = [doc for doc in yaml.safe_load_all(subprocess.check_output(command, text=True)) if doc]
    guard = next(doc for doc in docs if doc['kind'] == 'CronJob')
    cm = next(doc for doc in docs if doc['metadata']['name'] == tool.GUARD + '-script')
    role = next(doc for doc in docs if doc['kind'] == 'Role')
    if retired:
        tool.assert_parakeet_guard_retired(guard, role, [], cm)
    else:
        with pytest.raises(RuntimeError, match='PARAKEET_SUSPENDED=true'):
            tool.assert_parakeet_guard_retired(guard, role, [], cm)
