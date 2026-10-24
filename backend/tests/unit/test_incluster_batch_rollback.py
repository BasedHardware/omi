"""No cloud access: exercise admission rollback, interruption recovery, and actual Helm wiring."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / 'charts/incluster-guards'
spec = importlib.util.spec_from_file_location('guard', CHART / 'files/guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
spec = importlib.util.spec_from_file_location('batch_guard', CHART / 'files/batch_guard.py')
batch = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'guard': guard}):
    spec.loader.exec_module(batch)


def template():
    return {
        'serviceAccount': 'backend-runtime@example.invalid',
        'timeout': '300s',
        'containers': [
            {
                'image': 'image@sha256:' + 'a' * 64,
                'resources': {'limits': {'memory': '2Gi'}},
                'env': [
                    {'name': batch.KEY, 'value': '5'},
                    {'name': 'KEEP', 'value': 'x,y'},
                    {'name': 'SECRET', 'valueSource': {'secretKeyRef': {'secret': 'ref', 'version': '1'}}},
                ],
            }
        ],
    }


class Cloud:
    def __init__(self):
        self.services, self.revisions, self.writes = {}, {}, []
        self.fail = None
        for key in batch.SERVICES:
            name = batch.ROOT + key
            rev = name + '/revisions/' + key + '-old'
            self.services[name] = {
                'name': name,
                'generation': '1',
                'observedGeneration': '1',
                'etag': '1',
                'terminalCondition': {'state': 'CONDITION_SUCCEEDED'},
                'reconciling': False,
                'template': template(),
                'latestCreatedRevision': rev,
                'latestReadyRevision': rev,
                'trafficStatuses': [{'revision': rev, 'percent': 100}],
            }
            self.revisions[rev] = dict(template(), name=rev, reconciling=False)

    def get(self, path):
        return deepcopy((self.revisions if '/revisions/' in path else self.services)[path])

    def patch(self, service, body, mask):
        if self.fail == service['name']:
            raise ValueError('fake_service_failure')
        old = self.services[service['name']]
        assert old['etag'] == service['etag']
        self.writes.append((service['name'], deepcopy(body), mask))
        if 'template' in body:
            new = deepcopy(body['template'])
            rev = service['name'] + '/revisions/' + new['revision']
            self.revisions[rev] = dict(new, name=rev, reconciling=False)
            old.update(template=new, latestCreatedRevision=rev, latestReadyRevision=rev)
        old['trafficStatuses'] = deepcopy(body['traffic'])
        for target in old['trafficStatuses']:
            if '/' not in target['revision']:
                target['revision'] = old['name'] + '/revisions/' + target['revision']
        old['etag'] = str(int(old['etag']) + 1)
        return {'name': 'operation-not-polled'}


class Kube:
    def __init__(self):
        self.cm = {'metadata': {'resourceVersion': '1'}, 'data': {'state': '{}'}}

    def path(self, resource):
        assert resource == 'state'
        return resource

    def kube(self, path, body=None):
        assert path == 'state'
        if body:
            assert body[0]['value'] == self.cm['metadata']['resourceVersion']
            self.cm['data'] = deepcopy(body[1]['value'])
            self.cm['metadata']['resourceVersion'] = str(int(self.cm['metadata']['resourceVersion']) + 1)
        return deepcopy(self.cm)

    @property
    def state(self):
        return json.loads(self.cm['data']['state'])


def sample(identity='id', since=0, now=1800):
    return {
        'schema_version': 1,
        'identity': identity,
        'since': since,
        'arm_since': since,
        'observed_at': now,
        'read_completed_at': now,
        'custody': {'missing': 0, 'unknown': 0},
        **dict.fromkeys(
            [
                'proven_terminal_loss_speech_seconds',
                'proven_failed_held_speech_seconds',
                'since_t0_projection_obligations_over_15m',
                'since_t0_stuck_jobs_over_30m',
                'terminal_unrecovered_speech_unknown_units',
                'since_t0_failed_held_unknown_duration',
                'terminal_unrecovered_speech_vad_fallback_units',
                'since_t0_failed_held_vad_fallback_units',
            ],
            0,
        ),
    }


def test_env_update_preserves_every_other_field_including_secret_refs():
    old = template()['containers']
    old.append({'name': 'metrics', 'image': 'metrics@sha256:frozen', 'env': [{'name': 'UNCHANGED', 'value': 'yes'}]})
    new = batch.containers_at_zero(old)
    assert batch.percent(old) == 5 and batch.percent(new) == 0
    new[0]['env'][0]['value'] = '5'
    assert new == old


def test_proto_default_false_fields_are_optional():
    cloud = Cloud()
    for service in cloud.services.values():
        service.pop('reconciling')
    for revision in cloud.revisions.values():
        revision.pop('reconciling')
    assert len(batch.snapshot(cloud)) == 4


def test_template_tag_resolves_to_frozen_serving_digest(tmp_path, monkeypatch):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    for service in cloud.services.values():
        service['template']['containers'][0]['image'] = 'image:mutable'
    batch.run(kube, cloud, path, now=100)
    data = sample(kube.state['identity'], since=100, now=1900)
    data['custody']['missing'] = 1
    path.write_text(json.dumps(data))
    assert batch.run(kube, cloud, path, now=1900) == 1
    for _, body, mask in cloud.writes:
        if mask != 'traffic':
            assert body['template']['containers'][0]['image'] == 'image@sha256:' + 'a' * 64


def test_cloud_uses_gke_metadata_token_and_etag_mask(monkeypatch):
    import io

    calls = []

    def opened(request, **kwargs):
        calls.append(request)
        if request.full_url.endswith('/token'):
            return io.BytesIO(b'{"access_token":"fake-gke-token"}')
        return io.BytesIO(b'{"name":"operation"}')

    monkeypatch.setattr(batch.urllib.request, 'urlopen', opened)
    batch.Cloud().patch({'name': batch.ROOT + 'backend', 'etag': 'expected'}, {'traffic': []}, 'traffic')
    assert calls[0].full_url.endswith('/default/token')
    assert calls[0].get_header('Metadata-flavor') == 'Google'
    assert calls[1].get_header('Authorization') == 'Bearer fake-gke-token'
    assert calls[1].full_url.endswith('/services/backend?updateMask=traffic')
    assert json.loads(calls[1].data)['etag'] == 'expected'


def test_registered_logging_entrypoint_dispatches_batch(monkeypatch):
    from types import SimpleNamespace

    called = []

    def batch_main():
        called.append(True)
        return 17

    monkeypatch.setattr(sys, 'argv', ['guard.py', '--batch'])
    with patch.dict(sys.modules, {'batch_guard': SimpleNamespace(main=batch_main)}):
        assert guard.main() == 17
    assert called == [True]


@pytest.mark.parametrize(
    'bad',
    [
        [],
        [{'name': batch.KEY, 'value': '101'}],
        [{'name': batch.KEY, 'valueSource': {'secretKeyRef': {}}}],
        [{'name': batch.KEY, 'value': '5'}] * 2,
    ],
)
def test_invalid_percent_refuses(bad):
    containers = template()['containers']
    containers[0]['env'] = bad
    with pytest.raises(ValueError):
        batch.containers_at_zero(containers)


@pytest.mark.parametrize(
    'field',
    [
        'proven_terminal_loss_speech_seconds',
        'proven_failed_held_speech_seconds',
        'since_t0_projection_obligations_over_15m',
        'since_t0_stuck_jobs_over_30m',
        'custody',
    ],
)
def test_p90_three_trip_classes_only_after_full_new_window(field):
    data = sample()
    if field == 'custody':
        data['custody']['missing'] = 1
    else:
        data[field] = 1
    assert batch.decision(data, 'id', 0, 1799)[0] == 'BLIND'  # Future sample rejected.
    data['observed_at'] = data['read_completed_at'] = 1799
    assert batch.decision(data, 'id', 0, 1799)[0] == 'WARMUP'
    assert batch.decision(data, 'id', 0, 1800)[0] == 'TRIP'


@pytest.mark.parametrize('bad', [None, float('nan'), -1, True])
def test_unknown_never_clean_or_trip(bad):
    data = sample()
    data['proven_terminal_loss_speech_seconds'] = bad
    assert batch.decision(data, 'id', 0, 1800)[0] == 'BLIND'
    data['custody']['missing'] = 1
    assert batch.decision(data, 'id', 0, 1800)[0] == 'TRIP'


def test_fallback_unknown_stale_mismatch_and_quality_watch():
    data = sample()
    assert batch.decision(data, 'id', 0, 1800)[0] == 'CLEAN'
    data['watches'] = {'quality_p95': 9999, 'first_summary_status': 'UNAVAILABLE'}
    assert batch.decision(data, 'id', 0, 1800)[0] == 'CLEAN'
    assert batch.decision(data, 'id', 0, 2401)[0] == 'BLIND'
    assert batch.decision(data, 'other', 0, 1800)[0] == 'BLIND'
    assert batch.decision(data, 'id', 1, 1800)[0] == 'BLIND'
    data['since_t0_failed_held_vad_fallback_units'] = 1
    assert batch.decision(data, 'id', 0, 1800)[0] == 'BLIND'


def test_first_write_scope_precedes_all_serving_arming_and_cannot_move():
    data = sample(since=600, now=2399)
    data['since'] = 100  # Obligations during partial apply remain in scope.
    data['custody']['missing'] = 1
    assert batch.decision(data, 'id', 600, 2399, 100)[0] == 'WARMUP'
    assert batch.decision(data, 'id', 600, 2400, 100)[0] == 'TRIP'
    data['since'] = 101
    assert batch.decision(data, 'id', 600, 2400, 100)[0] == 'BLIND'
    data['since'] = 601
    assert batch.decision(data, 'id', 600, 2400)[0] == 'BLIND'


@pytest.mark.parametrize('drift', ['split', 'tag', 'template', 'latest', 'reconciling'])
def test_snapshot_refuses_split_tag_unserved_or_reconciling(drift):
    cloud = Cloud()
    service = cloud.services[batch.ROOT + 'backend']
    if drift == 'split':
        service['trafficStatuses'] *= 2
    if drift == 'tag':
        service['trafficStatuses'][0]['tag'] = 'canary'
    if drift == 'template':
        service['template']['containers'][0]['env'][1]['value'] = 'unserved'
    if drift == 'latest':
        service['latestCreatedRevision'] = 'unserved'
    if drift == 'reconciling':
        service['reconciling'] = True
    with pytest.raises(ValueError):
        batch.snapshot(cloud)
    assert not cloud.writes


def no_sleep(_):
    pass


def prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(batch.time, 'sleep', no_sleep)
    # Defaults capture time.sleep at definition; inject it at the worker boundary.
    original = batch.rollback_one
    monkeypatch.setattr(batch, 'rollback_one', lambda *args: original(*args, sleep=no_sleep))
    cloud, kube = Cloud(), Kube()
    path = tmp_path / 'snapshot.json'
    assert batch.run(kube, cloud, path, now=0) == 1  # Missing input, never clean.
    data = sample(kube.state['identity'])
    data['custody']['missing'] = 1
    path.write_text(json.dumps(data))
    return cloud, kube, path


@pytest.mark.parametrize('dry', [True, False])
def test_real_run_preserves_env_pins_old_traffic_promotes_and_reads_back(tmp_path, monkeypatch, dry):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    assert batch.run(kube, cloud, path, dry_run=dry, now=1800) == 1
    if dry:
        assert not cloud.writes and not kube.state.get('pending')
        return
    assert len(cloud.writes) == 8
    for service_id in batch.SERVICES:
        writes = [w for w in cloud.writes if w[0] == batch.ROOT + service_id]
        assert writes[0][1]['traffic'][0]['revision'].endswith(service_id + '-old')
        assert writes[0][2] == 'template.containers,template.revision,traffic'
        new = deepcopy(writes[0][1]['template'])
        new.pop('revision')
        new['containers'][0]['env'][0]['value'] = '5'
        assert new == template()
        assert writes[1][2] == 'traffic'
    assert {s['percent'] for s in batch.snapshot(cloud).values()} == {0}
    assert not kube.state.get('pending') and kube.cm['data']['verdict'] == 'ROLLED_BACK'


def test_partial_failure_retries_remaining_after_signal_disappears(tmp_path, monkeypatch):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    cloud.fail = batch.ROOT + 'backend-sync'
    assert batch.run(kube, cloud, path, now=1800) == 2
    assert kube.state['pending'] and kube.cm['data']['verdict'] == 'ROLLBACK_FAILED'
    assert len(cloud.writes) == 6
    path.unlink()
    cloud.fail = None
    assert batch.run(kube, cloud, path, now=2100) == 1
    assert len(cloud.writes) == 8
    assert not kube.state.get('pending')


def test_candidate_created_before_interruption_is_promoted_without_recreation(tmp_path, monkeypatch):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    original = batch.rollback_one

    def interrupted(cloud, key, pin, deadline):
        if key == 'backend':
            real = cloud.patch

            def stop(service, body, mask):
                if mask == 'traffic':
                    raise ValueError('simulated_interruption_before_promotion')
                return real(service, body, mask)

            with patch.object(cloud, 'patch', side_effect=stop):
                return original(cloud, key, pin, deadline)
        raise ValueError('other_services_interrupted')

    monkeypatch.setattr(batch, 'rollback_one', interrupted)
    assert batch.run(kube, cloud, path, now=1800) == 2
    assert len(cloud.writes) == 1
    monkeypatch.setattr(batch, 'rollback_one', original)
    assert batch.run(kube, cloud, path, now=2100) == 1
    assert len(cloud.writes) == 8


def test_identity_change_resets_window(tmp_path, monkeypatch):
    cloud, kube, path = prepare(tmp_path, monkeypatch)
    # A new revision with identical env still restarts arming; cannot reuse old snapshots.
    service = cloud.services[batch.ROOT + 'backend']
    old_name = service['latestReadyRevision']
    new_name = old_name + '-new'
    cloud.revisions[new_name] = dict(cloud.revisions[old_name], name=new_name)
    service.update(
        latestReadyRevision=new_name,
        latestCreatedRevision=new_name,
        trafficStatuses=[{'revision': new_name, 'percent': 100}],
    )
    assert batch.run(kube, cloud, path, now=1800) == 1
    assert kube.state['since'] == 1800 and not cloud.writes


def test_helm_dedicated_identity_state_only_rbac_and_cpu_placement():
    docs = list(
        yaml.safe_load_all(
            subprocess.check_output(
                [
                    'helm',
                    'template',
                    'prod-omi-incluster-guards',
                    str(CHART),
                    '--namespace',
                    'prod-omi-backend',
                    '-f',
                    str(CHART / 'prod_omi_incluster_guards_values.yaml'),
                ],
                text=True,
            )
        )
    )
    resources = {d['kind']: d for d in docs if d and d['metadata']['name'] == 'prod-omi-incluster-guards-batch'}
    assert resources['ServiceAccount']['metadata']['annotations'] == {
        'iam.gke.io/gcp-service-account': 'omi-batch-rollback-guard@based-hardware.iam.gserviceaccount.com'
    }
    assert resources['Role']['rules'] == [
        {
            'apiGroups': [''],
            'resources': ['configmaps'],
            'resourceNames': ['prod-omi-incluster-guards-batch-state'],
            'verbs': ['get', 'patch'],
        }
    ]
    job = resources['CronJob']['spec']['jobTemplate']['spec']
    assert job['backoffLimit'] == 0 and job['activeDeadlineSeconds'] == 840
    pod = job['template']['spec']
    assert pod['serviceAccountName'] == 'prod-omi-incluster-guards-batch'
    assert pod['nodeSelector'] == {'iam.gke.io/gke-metadata-server-enabled': 'true'}
    assert pod['tolerations'] == [] and pod['affinity']
    assert pod['volumes'][1]['configMap']['optional'] is True
    assert pod['containers'][0]['command'] == ['python3', '/guard/guard.py', '--batch']
    assert all(d['kind'] not in {'ClusterRole', 'ClusterRoleBinding', 'Secret'} for d in docs)


def test_selector_covers_new_suite():
    root = CHART.parents[2]
    spec = importlib.util.spec_from_file_location(
        'batch_selector', root / 'backend/scripts/select_backend_unit_tests.py'
    )
    selector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selector)
    selected, _ = selector.tests_for_changed_paths(
        ['backend/charts/incluster-guards/files/batch_guard.py'],
        ['tests/unit/test_incluster_guards.py', 'tests/unit/test_incluster_batch_rollback.py'],
    )
    assert 'tests/unit/test_incluster_batch_rollback.py' in selected
