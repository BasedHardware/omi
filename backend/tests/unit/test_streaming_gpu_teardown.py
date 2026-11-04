"""Deletion fences for the lead-only streaming capacity retirement tool."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest

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
