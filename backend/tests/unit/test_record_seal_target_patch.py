"""Private CAS packet, exact inverse, server-delta verification and strict inputs."""

from copy import deepcopy
import json
from pathlib import Path
import runpy
import stat

import pytest
import yaml

from tests.unit.test_record_seal_cluster_repair_deploy import documents

TOOL = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'deploy/record-seal-repair/render_stock_drain_patch.py')
)
PATCH = TOOL['repair_patch']


def live_cron(fresh=True):
    live = deepcopy(documents('--set', 'recordSealRepair.shards=1')[('CronJob', 'record-seal-repair')])
    live['metadata'].update(namespace='prod-omi-backend', resourceVersion='123', uid='synthetic-cron')
    live['spec']['schedule'] = '*/5 * * * *'
    job = live['spec']['jobTemplate']['spec']
    for key in ('completionMode', 'completions', 'parallelism'):
        job.pop(key, None)
    pod = job['template']['spec']
    c = pod['containers'][0]
    pod['affinity'] = TOOL['node_affinity']('batch-pipeline-pool')
    pod['tolerations'] = [
        {'effect': 'NoSchedule', 'key': 'omi.ai/batch-pipeline', 'operator': 'Equal', 'value': 'true'},
        {'effect': 'NoSchedule', 'key': 'nvidia.com/gpu', 'operator': 'Equal', 'value': 'present'},
    ]
    c['resources']['requests']['cpu'] = '4'
    next(e for e in c['env'] if e['name'] == 'RECORD_SEAL_REPAIR_SERVER_FLAGS')['value'] = 'private-effective-policy'
    if not fresh:
        c['env'] = [e for e in c['env'] if e['name'] != TOOL['FRESH']]
    c['env'].append(
        {'name': 'OPERATOR_PRIVATE_GATE', 'valueFrom': {'secretKeyRef': {'name': 'private', 'key': 'gate'}}}
    )
    return live


def rendered():
    return list(documents('--set-string', 'recordSealRepair.imageDigest=sha256:' + 'b' * 64).values())


def image(live):
    return live['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]['image']


def apply(doc, patch):
    doc = deepcopy(doc)
    for op in patch:
        keys = op['path'].lstrip('/').split('/')
        parent = doc
        for key in keys[:-1]:
            parent = parent[key]
        if op['op'] == 'test':
            assert parent[keys[-1]] == op['value']
        else:
            parent[keys[-1]] = deepcopy(op['value'])
    return doc


@pytest.mark.parametrize('fresh', [False, True])
def test_target_packet_preserves_policy_and_exact_inverse_restores_entire_footprint(fresh):
    before = live_cron(fresh)
    patch, receipt, inverse = TOOL['prepare'](before, rendered(), image(before))
    after = apply(before, patch)
    TOOL['check'](after, receipt, 'after')
    before_c = TOOL['target'](before)[2]
    after_c = TOOL['target'](after)[2]
    assert after_c['env'] == before_c['env'] + ([] if fresh else [{'name': TOOL['FRESH'], 'value': 'true'}])
    assert receipt['beforeSpecSha256'] != receipt['afterSpecSha256']
    assert inverse[1]['value'] == '__FRESH_READBACK_RESOURCE_VERSION_REQUIRED__'
    after['metadata']['resourceVersion'] = '124'
    rollback = TOOL['rollback'](after, receipt)
    restored = apply(after, rollback)
    assert restored['spec'] == before['spec']  # Includes old image, placement, mode, cadence, tolerations.
    TOOL['check'](restored, receipt, 'before')
    assert rollback[1]['value'] == '124'


@pytest.mark.parametrize('change', ['name', 'namespace', 'kind', 'version', 'uid'])
def test_bad_live_target_is_refused(change):
    live = live_cron()
    if change == 'kind':
        live['kind'] = 'Deployment'
    elif change in ('version', 'uid'):
        live['metadata'].pop('resourceVersion' if change == 'version' else 'uid')
    else:
        live['metadata'][change] = 'different'
    with pytest.raises(ValueError):
        PATCH(live, rendered(), expected_image=image(live))


@pytest.mark.parametrize('phase', ['dry-run', 'readback', 'rollback'])
def test_any_unapproved_server_spec_change_blocks_forward_and_inverse(phase):
    before = live_cron()
    patch, receipt, _ = TOOL['prepare'](before, rendered(), image(before))
    after = apply(before, patch)
    after['spec']['suspend'] = not after['spec'].get('suspend', False)
    with pytest.raises(ValueError):
        if phase == 'rollback':
            TOOL['rollback'](after, receipt)
        else:
            TOOL['check'](after, receipt, 'after')


@pytest.mark.parametrize('explicit_mode', [False, True])
@pytest.mark.parametrize('explicit_version', [False, True])
def test_packet_includes_server_volume_defaults_with_either_rendered_spelling(explicit_mode, explicit_version):
    before = live_cron()
    before_container = TOOL['target'](before)[2]
    before_container.update(
        imagePullPolicy='IfNotPresent',
        terminationMessagePath='/dev/termination-log',
        terminationMessagePolicy='File',
    )
    manifests = rendered()
    cron = next(d for d in manifests if d['kind'] == 'CronJob' and d['metadata']['name'] == TOOL['NAME'])
    volume = next(
        v for v in cron['spec']['jobTemplate']['spec']['template']['spec']['volumes'] if v['name'] == 'partition'
    )['downwardAPI']
    assert volume['defaultMode'] == 420  # Chart also spells the API defaults explicitly.
    assert volume['items'][0]['fieldRef']['apiVersion'] == 'v1'
    if not explicit_mode:
        volume.pop('defaultMode')
    if not explicit_version:
        volume['items'][0]['fieldRef'].pop('apiVersion')
    original_manifests = deepcopy(manifests)
    patch, receipt, _ = TOOL['prepare'](before, manifests, image(before))
    assert manifests == original_manifests
    server_response = apply(before, patch)
    pod = TOOL['target'](server_response)[1]
    downward = next(v for v in pod['volumes'] if v['name'] == 'partition')['downwardAPI']
    # The v1.35 CronJob defaulter traverses this volume and ObjectFieldSelector.
    assert downward['defaultMode'] == 420
    assert downward['items'][0]['fieldRef']['apiVersion'] == 'v1'
    downward.setdefault('defaultMode', 420)
    downward['items'][0]['fieldRef'].setdefault('apiVersion', 'v1')
    TOOL['check'](server_response, receipt, 'after')
    after_container = TOOL['target'](server_response)[2]
    for key in ('imagePullPolicy', 'terminationMessagePath', 'terminationMessagePolicy'):
        assert after_container[key] == before_container[key]
    assert apply(server_response, TOOL['rollback'](server_response, receipt))['spec'] == before['spec']


@pytest.mark.parametrize('field,value', [('defaultMode', 384), ('apiVersion', 'v2'), ('extra', True)])
def test_conflicting_or_unapproved_partition_defaults_are_refused(field, value):
    before = live_cron()
    manifests = rendered()
    cron = next(d for d in manifests if d['kind'] == 'CronJob' and d['metadata']['name'] == TOOL['NAME'])
    downward = next(
        v for v in cron['spec']['jobTemplate']['spec']['template']['spec']['volumes'] if v['name'] == 'partition'
    )['downwardAPI']
    if field == 'apiVersion':
        downward['items'][0]['fieldRef'][field] = value
    else:
        downward[field] = value
    with pytest.raises(ValueError, match='unexpected partition volume'):
        TOOL['prepare'](before, manifests, image(before))


def test_inverse_refuses_replaced_object_and_changed_receipt():
    before = live_cron()
    patch, receipt, _ = TOOL['prepare'](before, rendered(), image(before))
    after = apply(before, patch)
    after['metadata']['uid'] = 'replacement'
    with pytest.raises(ValueError):
        TOOL['rollback'](after, receipt)
    after['metadata']['uid'] = before['metadata']['uid']
    receipt['beforeSpec']['schedule'] = 'unexpected'
    with pytest.raises(ValueError):
        TOOL['rollback'](after, receipt)


def test_cli_private_packet_before_apply_and_verified_rollback(tmp_path, monkeypatch, capsys):
    import sys

    before = live_cron()
    live, manifest = tmp_path / 'live.json', tmp_path / 'rendered.yaml'
    live.write_text(json.dumps(before))
    manifest.write_text(yaml.safe_dump_all(rendered()))
    args = [
        'packet',
        'prepare',
        '--live-json',
        str(live),
        '--rendered-yaml',
        str(manifest),
        '--expected-image',
        image(before),
        '--out',
        str(tmp_path),
    ]
    monkeypatch.setattr(sys, 'argv', args)
    TOOL['main']()
    for name in ('receipt.json', 'forward.json', 'rollback.template.json'):
        assert stat.S_IMODE((tmp_path / name).stat().st_mode) == 0o600
    patch = json.loads((tmp_path / 'forward.json').read_text())
    after = apply(before, patch)
    after['metadata']['resourceVersion'] = '124'
    live.write_text(json.dumps(after))
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'packet',
            'rollback',
            '--receipt',
            str(tmp_path / 'receipt.json'),
            '--object',
            str(live),
            '--output',
            str(tmp_path / 'rollback.json'),
        ],
    )
    TOOL['main']()
    assert apply(after, json.loads((tmp_path / 'rollback.json').read_text()))['spec'] == before['spec']
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize(
    'field',
    [
        'selector',
        'hostname',
        'command',
        'args',
        'deadline',
        'backoff',
        'per_index',
        'cpu',
        'memory',
        'affinity',
        'tolerations',
        'mount',
        'workers',
        'fresh_off',
        'image',
    ],
)
def test_incompatible_live_owned_fields_are_rejected_before_packet(field):
    live = live_cron()
    expected = image(live)
    job, pod, c = TOOL['target'](live)
    if field == 'selector':
        pod['nodeSelector'] = {'cloud.google.com/gke-nodepool': 'batch-pipeline-pool'}
    elif field == 'hostname':
        pod['hostname'] = 'unexpected'
    elif field == 'command':
        c['command'] = ['different']
    elif field == 'args':
        c['args'] = ['--unexpected']
    elif field == 'deadline':
        job['activeDeadlineSeconds'] = 1710
    elif field == 'backoff':
        job['backoffLimit'] = 10
    elif field == 'per_index':
        job['backoffLimitPerIndex'] = 2
    elif field == 'cpu':
        c['resources']['requests']['cpu'] = '8'
    elif field == 'memory':
        c['resources']['limits']['memory'] = '16Gi'
    elif field == 'affinity':
        pod['affinity'] = {}
    elif field == 'tolerations':
        pod['tolerations'] = []
    elif field == 'mount':
        c['volumeMounts'].append({'name': 'other', 'mountPath': '/etc/repair-partition'})
    elif field == 'workers':
        next(e for e in c['env'] if e['name'] == 'RECORD_SEAL_REPAIR_WORKERS')['value'] = '16'
    elif field == 'fresh_off':
        next(e for e in c['env'] if e['name'] == TOOL['FRESH'])['value'] = 'false'
    elif field == 'image':
        c['image'] = 'unexpected@sha256:' + 'c' * 64
    with pytest.raises(ValueError):
        TOOL['prepare'](live, rendered(), expected)
