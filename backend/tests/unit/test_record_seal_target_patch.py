"""Repair-only rollout preserves effective policy and cannot target GPU resources."""

from copy import deepcopy
from pathlib import Path
import runpy

import pytest

from tests.unit.test_record_seal_cluster_repair_deploy import documents

PATCH = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'deploy/record-seal-repair/render_stock_drain_patch.py')
)['repair_patch']


def live_cron():
    live = deepcopy(documents('--set', 'recordSealRepair.shards=1')[('CronJob', 'record-seal-repair')])
    live['metadata'].update(namespace='prod-omi-backend', resourceVersion='123')
    env = live['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]['env']
    next(e for e in env if e['name'] == 'RECORD_SEAL_REPAIR_SERVER_FLAGS')['value'] = 'private-effective-policy'
    next(e for e in env if e['name'] == 'RECORD_SEAL_REPAIR_FRESH_ENABLED')['value'] = 'false'
    env.append({'name': 'OPERATOR_PRIVATE_GATE', 'valueFrom': {'secretKeyRef': {'name': 'private', 'key': 'gate'}}})
    return live


@pytest.mark.parametrize('shards', [1, 5])
def test_target_only_patch_preserves_every_gate_policy_and_other_pod_field(shards):
    live = live_cron()
    rendered = documents(
        '--set', f'recordSealRepair.shards={shards}', '--set-string', 'recordSealRepair.imageDigest=sha256:' + 'b' * 64
    )
    original = deepcopy(live)
    patch = PATCH(live, list(rendered.values()))
    assert live == original
    assert [op['path'] for op in patch] == ['/metadata/resourceVersion', '/spec/schedule', '/spec/jobTemplate']
    assert patch[0]['op'] == 'test' and patch[0]['value'] == '123'
    job = patch[-1]['value']['spec']
    assert job['completions'] == job['parallelism'] == shards
    pod = job['template']['spec']
    before = original['spec']['jobTemplate']['spec']['template']['spec']
    for key in ('serviceAccountName', 'securityContext', 'restartPolicy'):
        assert pod[key] == before[key]
    assert pod['containers'][0]['env'] == before['containers'][0]['env']
    assert pod['containers'][0]['image'].endswith('b' * 64)
    assert 'tolerations' not in pod


@pytest.mark.parametrize('change', ['name', 'namespace', 'kind', 'version'])
def test_bad_live_target_is_refused(change):
    live = live_cron()
    if change == 'kind':
        live['kind'] = 'Deployment'
    elif change == 'version':
        live['metadata'].pop('resourceVersion')
    else:
        live['metadata'][change] = 'different'
    with pytest.raises(ValueError):
        PATCH(live, list(documents().values()))


def test_cli_tightens_output_permissions_and_prints_no_private_policy(tmp_path, monkeypatch, capsys):
    import json
    import stat
    import sys
    import yaml

    live, rendered, output = tmp_path / 'live.json', tmp_path / 'rendered.yaml', tmp_path / 'patch.json'
    live.write_text(json.dumps(live_cron()))
    rendered.write_text(yaml.safe_dump_all(list(documents().values())))
    output.write_text('old')
    output.chmod(0o644)
    monkeypatch.setattr(
        sys, 'argv', ['render', '--live-json', str(live), '--rendered-yaml', str(rendered), '--output', str(output)]
    )
    PATCH.__globals__['main']()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text())[0]['op'] == 'test'
    assert capsys.readouterr().out == ''
