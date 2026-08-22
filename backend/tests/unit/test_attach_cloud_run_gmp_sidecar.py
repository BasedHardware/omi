from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'attach_cloud_run_gmp_sidecar.py'


def _load_module():
    spec = importlib.util.spec_from_file_location('attach_cloud_run_gmp_sidecar', SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _service(*, latest_traffic: bool = False):
    return {
        'apiVersion': 'serving.knative.dev/v1',
        'kind': 'Service',
        'metadata': {'name': 'desktop-backend', 'resourceVersion': 'discard-me'},
        'spec': {
            'template': {
                # `gcloud run services describe --format=export` omits the
                # latest revision name from the template metadata.
                'metadata': {
                    'annotations': {'run.googleapis.com/container-dependencies': '{"logger":["desktop-backend-1"]}'}
                },
                'spec': {
                    'containers': [
                        {
                            'image': 'example/app@sha256:abc',
                            'name': 'desktop-backend-1',
                            'env': [
                                {'name': 'SAFE', 'value': 'kept'},
                                {'name': 'BOOLEAN_LOOKING', 'value': False},
                            ],
                        },
                        {'image': 'example/logger@sha256:def', 'name': 'logger'},
                    ],
                    'volumes': [{'name': 'existing', 'secret': {'secretName': 'existing'}}],
                },
            },
            'traffic': [{'latestRevision': latest_traffic, 'revisionName': 'desktop-backend-serving', 'percent': 100}],
        },
        'status': {'url': 'https://example.invalid'},
    }


def test_ensure_config_secret_accepts_a_concurrent_first_create(monkeypatch, tmp_path):
    module = _load_module()
    config = tmp_path / 'config.yaml'
    config.write_text('kind: RunMonitoring\n', encoding='utf-8')
    config_hash = module.hashlib.sha256(config.read_bytes()).hexdigest()[:63]
    responses = iter(
        (
            module.subprocess.CompletedProcess([], 1, '', 'not found'),
            module.subprocess.CompletedProcess([], 1, '', 'already exists'),
            module.subprocess.CompletedProcess([], 0, f'{{"labels": {{"config-sha": "{config_hash}"}}}}', ''),
            module.subprocess.CompletedProcess([], 0, 'projects/1/secrets/cloud-run-gmp-config/versions/7\n', ''),
        )
    )
    calls = []

    def fake_run(args, *, capture_output=False):
        calls.append(list(args))
        return next(responses)

    monkeypatch.setattr(module, '_run', fake_run)

    version = module.ensure_config_secret(project='example-project', secret='cloud-run-gmp-config', config_path=config)

    assert version == '7'
    assert len(calls) == 4
    assert calls[1][1:3] == ['secrets', 'create']
    assert calls[2][1:3] == ['secrets', 'describe']
    assert calls[3][1:4] == ['secrets', 'versions', 'describe']


def test_patch_service_adds_pinned_sidecar_without_losing_ingress_contract():
    module = _load_module()
    source = _service()

    patched = module.patch_service(
        source,
        project='example-project',
        base_revision='desktop-backend-base',
        latest_created_revision='desktop-backend-base',
        final_revision='desktop-backend-final',
        ingress_container_name='desktop-backend-1',
        config_secret='cloud-run-gmp-config',
        config_secret_version='7',
    )

    template = patched['spec']['template']
    assert template['metadata']['name'] == 'desktop-backend-final'
    assert template['metadata']['annotations']['run.googleapis.com/execution-environment'] == 'gen2'
    assert template['metadata']['annotations']['run.googleapis.com/cpu-throttling'] == 'false'
    assert template['metadata']['annotations']['run.googleapis.com/container-dependencies'] == (
        '{"collector":["desktop-backend-1"],"logger":["desktop-backend-1"]}'
    )
    ingress, logger, collector = template['spec']['containers']
    assert ingress['name'] == 'desktop-backend-1'
    assert ingress['env'] == [
        {'name': 'SAFE', 'value': 'kept'},
        {'name': 'BOOLEAN_LOOKING', 'value': 'false'},
    ]
    assert logger == {'image': 'example/logger@sha256:def', 'name': 'logger'}
    assert collector['image'] == module.SIDECAR_IMAGE
    assert '@sha256:' in collector['image']
    assert collector['resources']['limits'] == {'cpu': '1', 'memory': '512Mi'}
    assert {volume['name'] for volume in template['spec']['volumes']} == {
        'existing',
        'cloud-run-gmp-config',
    }
    config_volume = next(volume for volume in template['spec']['volumes'] if volume['name'] == 'cloud-run-gmp-config')
    assert config_volume['secret']['items'] == [{'key': '7', 'path': 'config.yaml'}]
    assert 'status' not in patched
    assert 'resourceVersion' not in patched['metadata']
    assert 'name' not in source['spec']['template']['metadata']


def test_patch_service_names_an_initial_unnamed_singleton_ingress():
    module = _load_module()
    source = _service()
    containers = source['spec']['template']['spec']['containers']
    containers[:] = [containers[0]]
    containers[0].pop('name')
    source['spec']['template']['metadata']['annotations'].clear()

    patched = module.patch_service(
        source,
        project='example-project',
        base_revision='desktop-backend-base',
        latest_created_revision='desktop-backend-base',
        final_revision='desktop-backend-final',
        ingress_container_name='desktop-backend-1',
        config_secret='cloud-run-gmp-config',
        config_secret_version='7',
    )

    assert patched['spec']['template']['spec']['containers'][0]['name'] == 'desktop-backend-1'


def test_patch_service_refuses_latest_revision_traffic():
    module = _load_module()

    with pytest.raises(ValueError, match='traffic follows latestRevision'):
        module.patch_service(
            _service(latest_traffic=True),
            project='example-project',
            base_revision='desktop-backend-base',
            latest_created_revision='desktop-backend-base',
            final_revision='desktop-backend-final',
            ingress_container_name='desktop-backend-1',
            config_secret='cloud-run-gmp-config',
            config_secret_version='7',
        )


def test_patch_service_refuses_a_different_latest_created_revision():
    module = _load_module()

    with pytest.raises(ValueError, match="expected base revision 'desktop-backend-base', found 'another-revision'"):
        module.patch_service(
            _service(),
            project='example-project',
            base_revision='desktop-backend-base',
            latest_created_revision='another-revision',
            final_revision='desktop-backend-final',
            ingress_container_name='desktop-backend-1',
            config_secret='cloud-run-gmp-config',
            config_secret_version='7',
        )
