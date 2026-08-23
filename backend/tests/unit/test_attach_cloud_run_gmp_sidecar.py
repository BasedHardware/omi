from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

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
        project_number='1031333818730',
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


def test_secret_annotation_uses_a_project_number_gcloud_can_parse():
    """gcloud rejects a project ID in the run.googleapis.com/secrets annotation.

    Its parser is `^projects/[0-9]{1,19}/secrets/<name>(:v|/versions/v)?$`, so an
    ID there makes every later `gcloud run deploy` on the service crash with
    "Invalid secret path". Cloud Run accepts the attach either way, so the break
    only appears on the next deploy -- long after the change that caused it.
    """
    module = _load_module()

    patched = module.patch_service(
        _service(),
        project_number='1031333818730',
        base_revision='desktop-backend-base',
        latest_created_revision='desktop-backend-base',
        final_revision='desktop-backend-final',
        ingress_container_name='desktop-backend-1',
        config_secret='cloud-run-gmp-config',
        config_secret_version='7',
    )

    annotation = patched['spec']['template']['metadata']['annotations']['run.googleapis.com/secrets']
    assert annotation == 'cloud-run-gmp-config:projects/1031333818730/secrets/cloud-run-gmp-config'

    # verbatim from googlecloudsdk/command_lib/run/secrets_mapping.py
    gcloud_remote_secret_path = re.compile(
        r'^projects/(?P<project>[0-9]{1,19})'
        r'/secrets/(?P<secret>[a-zA-Z0-9-_]{1,255})'
        r'(?::(?P<version_short>.+)|/versions/(?P<version_long>.+))?$'
    )
    for entry in annotation.split(','):
        _alias, _sep, remote_path = entry.partition(':')
        assert gcloud_remote_secret_path.search(remote_path), remote_path


def test_project_number_passes_through_a_number_without_calling_gcloud(monkeypatch):
    module = _load_module()

    def fail(*_args, **_kwargs):
        raise AssertionError('a numeric project must not be resolved through gcloud')

    monkeypatch.setattr(module, '_run', fail)

    assert module._project_number('1031333818730') == '1031333818730'


def test_project_number_resolves_an_id_and_rejects_a_non_numeric_answer(monkeypatch):
    module = _load_module()
    calls: list[list[str]] = []

    def fake_run(args, *, capture_output=False):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='1031333818730\n', stderr='')

    monkeypatch.setattr(module, '_run', fake_run)
    assert module._project_number('based-hardware-dev') == '1031333818730'
    assert calls == [['gcloud', 'projects', 'describe', 'based-hardware-dev', '--format=value(projectNumber)']]

    monkeypatch.setattr(
        module,
        '_run',
        lambda args, *, capture_output=False: SimpleNamespace(returncode=0, stdout='not-a-number\n', stderr=''),
    )
    with pytest.raises(RuntimeError, match='project number'):
        module._project_number('based-hardware-dev')


def test_patch_service_names_an_initial_unnamed_singleton_ingress():
    module = _load_module()
    source = _service()
    containers = source['spec']['template']['spec']['containers']
    containers[:] = [containers[0]]
    containers[0].pop('name')
    source['spec']['template']['metadata']['annotations'].clear()

    patched = module.patch_service(
        source,
        project_number='1031333818730',
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
            project_number='1031333818730',
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
            project_number='1031333818730',
            base_revision='desktop-backend-base',
            latest_created_revision='another-revision',
            final_revision='desktop-backend-final',
            ingress_container_name='desktop-backend-1',
            config_secret='cloud-run-gmp-config',
            config_secret_version='7',
        )


def test_gcloud_export_loader_preserves_on_off_env_values_as_strings() -> None:
    """gcloud writes `value: on` unquoted; YAML 1.1 would make that a boolean.

    These bytes are copied from a real `gcloud run services describe
    --format=export` of the production backend service. Under yaml.safe_load
    the three flags come back as booleans and the dump back through
    `services replace` rewrites them to 'true'/'false', which is what broke
    development deploys at the post-deploy runtime-env validator.
    """
    module = _load_module()
    export = """\
spec:
  template:
    spec:
      containerConcurrency: 80
      containers:
      - name: backend-1
        env:
        - name: MEMORY_ENABLED
          value: on
        - name: ACCOUNT_CUTOVER_ENFORCEMENT
          value: off
        - name: PUBLIC_SHARED_CONVERSATION_CHAT_MODE
          value: off
        - name: MEMORY_V3_CURSOR_SECRET_VERSION
          value: prod-v1
        - name: REDIS_DB_PORT
          value: '13151'
        ports:
        - containerPort: 8080
        readinessProbe:
          periodSeconds: 240
"""
    loaded = yaml.load(export, Loader=module.GcloudExportLoader)
    container = loaded['spec']['template']['spec']['containers'][0]
    env = {entry['name']: entry['value'] for entry in container['env']}

    assert env['MEMORY_ENABLED'] == 'on'
    assert env['ACCOUNT_CUTOVER_ENFORCEMENT'] == 'off'
    assert env['PUBLIC_SHARED_CONVERSATION_CHAT_MODE'] == 'off'
    assert all(isinstance(value, str) for value in env.values())

    # structural numbers must still load as numbers, not strings
    assert container['ports'][0]['containerPort'] == 8080
    assert container['readinessProbe']['periodSeconds'] == 240
    assert loaded['spec']['template']['spec']['containerConcurrency'] == 80

    # and the round trip back out must reproduce what gcloud gave us
    round_tripped = yaml.load(yaml.safe_dump(loaded), Loader=module.GcloudExportLoader)
    assert round_tripped == loaded


def test_gcloud_export_loader_still_reads_real_booleans() -> None:
    """Only the YAML 1.1 extras are dropped; the 1.2 core set is intact."""
    module = _load_module()
    loaded = yaml.load('a: true\nb: false\nc: on\nd: off\ne: yes\nf: no\n', Loader=module.GcloudExportLoader)
    assert loaded == {'a': True, 'b': False, 'c': 'on', 'd': 'off', 'e': 'yes', 'f': 'no'}
