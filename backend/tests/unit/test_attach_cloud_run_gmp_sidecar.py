from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
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


@pytest.mark.parametrize('exists', [True, False])
def test_config_uses_existing_secret_when_secrets_create_is_denied(monkeypatch, tmp_path, exists):
    module = _load_module()
    config = tmp_path / 'config.yaml'
    config.write_text('kind: RunMonitoring\n', encoding='utf-8')
    calls = []

    def fake_run(args, *, capture_output=False):
        calls.append(list(args))
        if args[1:3] == ['secrets', 'create']:
            return module.subprocess.CompletedProcess(args, 1, '', 'secretmanager.secrets.create denied')
        if args[1:3] == ['secrets', 'describe']:
            return module.subprocess.CompletedProcess(args, 0 if exists else 1, '{}', '' if exists else 'NOT_FOUND')
        if args[1:4] == ['secrets', 'versions', 'add']:
            return module.subprocess.CompletedProcess(
                args, 0, 'projects/1/secrets/cloud-run-gmp-config/versions/7\n', ''
            )
        raise AssertionError(args)

    monkeypatch.setattr(module, '_run', fake_run)
    if exists:
        assert module.ensure_config_secret(project='example', secret='cloud-run-gmp-config', config_path=config) == '7'
    else:
        with pytest.raises(RuntimeError, match='required existing GMP config secret'):
            module.ensure_config_secret(project='example', secret='cloud-run-gmp-config', config_path=config)
        assert len(calls) == 1
    assert not any(call[1:3] == ['secrets', 'create'] for call in calls)


@pytest.mark.parametrize('config_name', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
@pytest.mark.parametrize('annotation_project', ['123', 'based-hardware'])
def test_env_config_is_revision_local_and_removes_only_unused_collector_secrets(config_name, annotation_project):
    module = _load_module()
    config = module.read_run_monitoring_config(SCRIPT.parents[1] / 'deploy' / config_name)
    service = _service()
    secret_annotation = 'run.googleapis.com/secrets'
    references = (
        f'cloud-run-gmp-config:projects/{annotation_project}/secrets/cloud-run-gmp-config,'
        f'existing:projects/{annotation_project}/secrets/existing'
    )
    service['metadata']['annotations'] = {secret_annotation: references}
    service['spec']['template']['metadata']['annotations'][secret_annotation] = references
    service['spec']['template']['spec']['volumes'].append(
        {'name': module.CONFIG_VOLUME_NAME, 'secret': {'secretName': 'cloud-run-gmp-config'}}
    )
    patched = module.patch_service(
        service,
        project_number='123',
        base_revision='base',
        latest_created_revision='base',
        final_revision='final',
        ingress_container_name='desktop-backend-1',
        config_secret='cloud-run-gmp-config',
        config_secret_version='',
        config_content=config,
    )
    template = patched['spec']['template']
    collector = template['spec']['containers'][-1]
    assert collector['command'] == ['/bin/sh', '-c']
    assert collector['args'] == [module.CONFIG_ENV_COMMAND]
    assert collector['env'] == [{'name': module.CONFIG_ENV_NAME, 'value': config}]
    assert 'volumeMounts' not in collector
    assert template['spec']['volumes'] == [{'name': 'existing', 'secret': {'secretName': 'existing'}}]
    for metadata in (patched['metadata'], template['metadata']):
        assert metadata['annotations'][secret_annotation] == 'existing:projects/123/secrets/existing'
    assert module.CONFIG_VOLUME_NAME in references
    assert len(service['spec']['template']['spec']['volumes']) == 2


@pytest.mark.parametrize('config_name', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
def test_env_attachment_succeeds_when_all_secret_writes_are_denied(monkeypatch, tmp_path, config_name):
    module = _load_module()
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    config = SCRIPT.parents[1] / 'deploy' / config_name
    expected = tmp_path / 'expected.json'
    expected.write_text(
        json.dumps(
            {
                'services': {
                    'desktop-backend': {
                        'env': [
                            {'name': 'SAFE', 'value': 'kept'},
                            {'name': 'BOOLEAN_LOOKING', 'value': 'false'},
                        ]
                    }
                }
            }
        )
    )
    calls = []
    replacements = []

    def fake_run(arguments, *, capture_output=False):
        calls.append(arguments)
        if arguments[1:3] == ['secrets', 'create']:
            return module.subprocess.CompletedProcess(arguments, 1, '', 'secretmanager.secrets.create denied')
        if arguments[1] == 'secrets':
            return module.subprocess.CompletedProcess(arguments, 1, '', 'Secret Manager denied')
        if '--format=export' in arguments:
            output = yaml.safe_dump(_service())
        elif '--format=value(status.latestCreatedRevisionName)' in arguments:
            output = 'base'
        elif '--format=value(status.url)' in arguments:
            output = 'https://example.invalid'
        elif arguments[1:4] == ['run', 'services', 'replace']:
            replacements.append(yaml.safe_load(Path(arguments[4]).read_text()))
            output = '{}'
        else:
            raise AssertionError(arguments)
        return module.subprocess.CompletedProcess(arguments, 0, output, '')

    monkeypatch.setattr(module, '_run', fake_run)
    module.attach_sidecar(
        SimpleNamespace(
            project='123',
            region='us-central1',
            service='desktop-backend',
            base_revision='base',
            final_revision='final',
            ingress_container='desktop-backend-1',
            config=config,
            config_env=True,
            config_secret='cloud-run-gmp-config',
            config_secret_version=None,
            expected_env_state=expected,
            tag='',
            desktop_backend_liveness_probe=False,
        )
    )
    assert not any(arguments[1] == 'secrets' for arguments in calls)
    assert len(replacements) == 1
    collector = replacements[0]['spec']['template']['spec']['containers'][-1]
    assert collector['env'] == [{'name': module.CONFIG_ENV_NAME, 'value': config.read_text()}]
    assert replacements[0]['spec']['traffic'] == _service()['spec']['traffic']


def test_env_config_wrapper_preserves_literal_bytes_and_executes_entrypoint(tmp_path):
    module = _load_module()
    config = 'kind: RunMonitoring\nvalue: "$(touch injected) ${NOT_EXPANDED} \\ %s"\n'
    directory = tmp_path / 'rungmp'
    entrypoint = tmp_path / 'entrypoint'
    receipt = tmp_path / 'entrypoint-receipt'
    entrypoint.write_text('#!/bin/sh\nprintf ready > "$RECEIPT"\n')
    entrypoint.chmod(0o755)
    command = module.CONFIG_ENV_COMMAND.replace('/etc/rungmp', str(directory)).replace(
        '/run-gmp-entrypoint', str(entrypoint)
    )
    result = subprocess.run(
        ['/bin/sh', '-c', command],
        cwd=tmp_path,
        env={**os.environ, module.CONFIG_ENV_NAME: config, 'RECEIPT': str(receipt)},
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert (directory / 'config.yaml').read_text() == config
    assert receipt.read_text() == 'ready'
    assert not (tmp_path / 'injected').exists()


def test_env_config_wrapper_does_not_start_on_missing_config(tmp_path):
    module = _load_module()
    command = module.CONFIG_ENV_COMMAND.replace('/etc/rungmp', str(tmp_path))
    result = subprocess.run(
        ['/bin/sh', '-c', command],
        env={key: value for key, value in os.environ.items() if key != module.CONFIG_ENV_NAME},
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert 'RunMonitoring config missing' in result.stderr


@pytest.mark.parametrize(
    'content', ['kind: Wrong\n', '[]', 'x' * 32769], ids=['wrong-kind', 'wrong-shape', 'too-large']
)
def test_env_config_validation_fails_before_cloud_calls(monkeypatch, tmp_path, content):
    module = _load_module()
    config = tmp_path / 'config.yaml'
    config.write_text(content)
    monkeypatch.setattr(module, '_run', lambda *args, **kwargs: pytest.fail('unexpected cloud call'))
    with pytest.raises(ValueError):
        module.attach_sidecar(SimpleNamespace(config=config, config_env=True))


def test_config_versions_pin_own_add_response_despite_concurrent_writer(monkeypatch, tmp_path):
    module = _load_module()
    backend = tmp_path / 'backend.yaml'
    sync = tmp_path / 'sync.yaml'
    backend.write_text('interval: 30s\n')
    sync.write_text('interval: 60s\n')
    payloads = {}
    versions = {}

    def fake_run(args, *, capture_output=False):
        if args[1:3] == ['secrets', 'describe']:
            # A legacy hash label is deliberately present: it cannot route to latest.
            return module.subprocess.CompletedProcess(args, 0, '{"labels":{"config-sha":"stale"}}', '')
        assert args[1:4] == ['secrets', 'versions', 'add'], args
        config = Path(next(a.split('=', 1)[1] for a in args if a.startswith('--data-file=')))
        number = str(len(payloads) + 7)
        payloads[number] = config.read_text()
        if config == backend:
            # The sync write finishes before backend's response returns. latest is
            # now sync, but backend must still pin its own version 7.
            versions['sync'] = module.ensure_config_secret(
                project='example', secret='cloud-run-gmp-config', config_path=sync
            )
        return module.subprocess.CompletedProcess(
            args, 0, f'projects/1/secrets/cloud-run-gmp-config/versions/{number}\n', ''
        )

    monkeypatch.setattr(module, '_run', fake_run)
    versions['backend'] = module.ensure_config_secret(
        project='example', secret='cloud-run-gmp-config', config_path=backend
    )
    assert versions == {'backend': '7', 'sync': '8'}
    assert payloads[versions['backend']] == backend.read_text()
    assert payloads[versions['sync']] == sync.read_text()


@pytest.mark.parametrize('resource', ['', 'latest', 'projects/1/secrets/other/versions/7'])
def test_config_add_requires_own_numeric_response(monkeypatch, tmp_path, resource):
    module = _load_module()
    config = tmp_path / 'config.yaml'
    config.write_text('kind: RunMonitoring\n')
    responses = iter(
        [
            module.subprocess.CompletedProcess([], 0, '{}', ''),
            module.subprocess.CompletedProcess([], 0, resource, ''),
        ]
    )
    monkeypatch.setattr(module, '_run', lambda *args, **kwargs: next(responses))
    with pytest.raises(RuntimeError, match='numeric version resource'):
        module.ensure_config_secret(project='example', secret='cloud-run-gmp-config', config_path=config)


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
    assert collector['resources']['limits'] == {'cpu': '0.25', 'memory': '512Mi'}
    assert {volume['name'] for volume in template['spec']['volumes']} == {
        'existing',
        'cloud-run-gmp-config',
    }
    config_volume = next(volume for volume in template['spec']['volumes'] if volume['name'] == 'cloud-run-gmp-config')
    assert config_volume['secret']['items'] == [{'key': '7', 'path': 'config.yaml'}]
    assert 'status' not in patched
    assert 'resourceVersion' not in patched['metadata']
    assert 'name' not in source['spec']['template']['metadata']


def test_patch_service_drops_ingress_startup_probe_initial_delay_and_keeps_the_rest():
    module = _load_module()
    source = _service()
    source['spec']['template']['spec']['containers'][0]['startupProbe'] = {
        'initialDelaySeconds': 60,
        'timeoutSeconds': 240,
        'periodSeconds': 240,
        'failureThreshold': 3,
        'tcpSocket': {'port': 8080},
    }

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

    ingress = patched['spec']['template']['spec']['containers'][0]
    assert ingress['startupProbe'] == {
        'timeoutSeconds': 240,
        'periodSeconds': 240,
        'failureThreshold': 3,
        'tcpSocket': {'port': 8080},
    }
    # The export the deploy read is not mutated in place.
    assert source['spec']['template']['spec']['containers'][0]['startupProbe']['initialDelaySeconds'] == 60


def test_desktop_backend_liveness_probe_survives_service_yaml_round_trip_and_keeps_startup_probe():
    module = _load_module()
    source = _service()
    ingress = source['spec']['template']['spec']['containers'][0]
    ingress['startupProbe'] = {
        'tcpSocket': {'port': 8080},
        'timeoutSeconds': 240,
        'periodSeconds': 240,
        'failureThreshold': 1,
    }
    ingress['livenessProbe'] = {'tcpSocket': {'port': 8080}}

    patched = module.patch_service(
        source,
        project_number='1031333818730',
        base_revision='desktop-backend-base',
        latest_created_revision='desktop-backend-base',
        final_revision='desktop-backend-final',
        ingress_container_name='desktop-backend-1',
        config_secret='cloud-run-gmp-config',
        config_secret_version='7',
        desktop_backend_liveness_probe=True,
    )
    rendered = yaml.load(yaml.safe_dump(patched), Loader=module.GcloudExportLoader)
    final_ingress = rendered['spec']['template']['spec']['containers'][0]
    assert final_ingress['startupProbe'] == ingress['startupProbe']
    assert final_ingress['livenessProbe'] == {
        'httpGet': {'path': '/healthz/live', 'port': 8080},
        'periodSeconds': 10,
        'timeoutSeconds': 5,
        'failureThreshold': 3,
    }
    assert rendered['spec']['template']['spec']['containers'][-1]['livenessProbe']['httpGet']['path'] == '/liveness'
    assert ingress['livenessProbe'] == {'tcpSocket': {'port': 8080}}


def test_liveness_probe_is_opt_in_for_shared_sidecar_script():
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
    assert 'livenessProbe' not in patched['spec']['template']['spec']['containers'][0]


def test_patch_service_leaves_an_absent_startup_probe_to_cloud_run_defaults():
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

    assert 'startupProbe' not in patched['spec']['template']['spec']['containers'][0]


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


def test_attach_refuses_to_replace_when_export_retypes_expected_env(monkeypatch, tmp_path) -> None:
    module = _load_module()
    expected_state = tmp_path / 'runtime-env-state.json'
    expected_state.write_text(
        json.dumps(
            {
                'services': {
                    'backend': {
                        'env': [
                            {'name': 'PUBLIC_SHARED_CONVERSATION_CHAT_MODE', 'value': 'off'},
                        ]
                    }
                }
            }
        ),
        encoding='utf-8',
    )
    config = tmp_path / 'cloud-run-gmp-sidecar.yaml'
    config.write_text('kind: RunMonitoring\n', encoding='utf-8')
    calls: list[list[str]] = []
    secret_calls: list[dict[str, object]] = []

    export = """\
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: backend
spec:
  template:
    metadata: {}
    spec:
      containers:
      - name: backend-1
        env:
        - name: PUBLIC_SHARED_CONVERSATION_CHAT_MODE
          value: off
  traffic:
  - latestRevision: false
    revisionName: backend-serving
    percent: 100
"""

    def fake_run(args, *, capture_output=False):
        calls.append(list(args))
        if '--format=export' in args:
            return module.subprocess.CompletedProcess(args, 0, export, '')
        if '--format=value(status.latestCreatedRevisionName)' in args:
            return module.subprocess.CompletedProcess(args, 0, 'backend-base\n', '')
        if args[1:4] == ['run', 'services', 'replace']:
            return module.subprocess.CompletedProcess(args, 0, '{}', '')
        if '--format=value(status.url)' in args:
            return module.subprocess.CompletedProcess(args, 0, 'https://backend.example\n', '')
        raise AssertionError(args)

    def fake_ensure_config_secret(**kwargs):
        secret_calls.append(kwargs)
        return '7'

    monkeypatch.setattr(module, 'ensure_config_secret', fake_ensure_config_secret)
    monkeypatch.setattr(module, '_project_number', lambda _project: '1031333818730')
    monkeypatch.setattr(module, '_run', fake_run)
    # Simulate the exact regression: parsing gcloud's YAML 1.2 export with
    # PyYAML's YAML 1.1 resolver turns the literal string `off` into False.
    monkeypatch.setattr(module, 'GcloudExportLoader', yaml.SafeLoader)

    with pytest.raises(ValueError, match="expected 'off', found 'false'"):
        module.attach_sidecar(
            SimpleNamespace(
                project='based-hardware',
                region='us-central1',
                service='backend',
                base_revision='backend-base',
                final_revision='backend-final',
                ingress_container='backend-1',
                config=config,
                config_secret='cloud-run-gmp-config',
                config_secret_version=None,
                expected_env_state=expected_state,
                tag='',
                desktop_backend_liveness_probe=False,
            )
        )

    assert not any(args[1:4] == ['run', 'services', 'replace'] for args in calls)
    assert secret_calls == []


def test_ingress_literal_env_treats_a_missing_value_key_as_empty_string():
    """Cloud Run's export omits the `value` key entirely for an empty-string literal.

    It never writes `value: ''`. Before the fix, an entry without a `value` key
    was skipped outright, so a var legitimately set to '' vanished from the
    literal-env map instead of resolving to ''. This is the exact shape of
    OMI_PARITY_PACK_ALLOWED_PRINCIPALS in the live dev backend service.
    """
    module = _load_module()
    service = {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'name': 'backend-1',
                            'env': [
                                {'name': 'SAFE', 'value': 'kept'},
                                {'name': 'OMI_PARITY_PACK_ALLOWED_PRINCIPALS'},
                            ],
                        }
                    ]
                }
            }
        }
    }

    actual = module._ingress_literal_env(service, ingress_container_name='backend-1')

    assert actual == {'SAFE': 'kept', 'OMI_PARITY_PACK_ALLOWED_PRINCIPALS': ''}


def test_ingress_literal_env_excludes_valueFrom_secret_references():
    """A secret-backed env var is not a literal and must not be coerced to ''.

    Before the fix these were excluded only by accident, because they never
    carry a `value` key either. The exclusion must stay deliberate now that a
    missing `value` key means '' for a real literal.
    """
    module = _load_module()
    service = {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'name': 'backend-1',
                            'env': [
                                {
                                    'name': 'OPENAI_API_KEY',
                                    'valueFrom': {'secretKeyRef': {'name': 'openai-api-key', 'key': 'latest'}},
                                },
                            ],
                        }
                    ]
                }
            }
        }
    }

    actual = module._ingress_literal_env(service, ingress_container_name='backend-1')

    assert actual == {}
    assert 'OPENAI_API_KEY' not in actual


@pytest.mark.parametrize('name', ['SYNC_TASKS_HANDLER_URL', 'SYNC_TASKS_OIDC_AUDIENCE'])
@pytest.mark.parametrize(
    ('service_name', 'actual_value', 'accepted'),
    [
        (
            'backend-sync-backfill',
            'https://backend-sync-backfill-208440318997.us-central1.run.app/v2/sync-jobs/run',
            True,
        ),
        ('backend-sync-backfill', 'https://backend-sync-backfill-hhibjajaja-uc.a.run.app/v2/sync-jobs/run', True),
        ('backend-sync-backfill', 'https://third-party.example/v2/sync-jobs/run', False),
        (
            'backend-sync-backfill',
            'https://backend-sync-backfill-208440318997.us-central1.run.app.evil/v2/sync-jobs/run',
            False,
        ),
        ('backend-sync-backfill', 'https://backend-sync-backfill-208440318997.us-central1.run.app/wrong', False),
        (
            'backend-sync-backfill',
            'http://backend-sync-backfill-208440318997.us-central1.run.app/v2/sync-jobs/run',
            False,
        ),
        (
            'backend-sync-backfill',
            'https://backend-sync-backfill-other-208440318997.us-central1.run.app/v2/sync-jobs/run?x=1',
            False,
        ),
        ('backend-sync-backfill', None, False),
        ('backend-sync', 'https://backend-sync-hhibjajaja-uc.a.run.app/v2/sync-jobs/run', True),
        ('backend-sync', 'https://backend-sync-backfill-208440318997.us-central1.run.app/v2/sync-jobs/run', False),
        ('backend', 'https://backend-sync-backfill-208440318997.us-central1.run.app/v2/sync-jobs/run', False),
    ],
)
def test_validate_expected_literal_env_backfill_url_overlay(name, service_name, actual_value, accepted):
    module = _load_module()
    service = _service()
    service['metadata']['name'] = service_name
    service['spec']['template']['spec']['containers'][0]['env'] = (
        [] if actual_value is None else [{'name': name, 'value': actual_value}]
    )
    kwargs = {
        'expected': {name: 'https://backend-sync-hhibjajaja-uc.a.run.app/v2/sync-jobs/run'},
        'ingress_container_name': 'desktop-backend-1',
        'phase': 'exported base revision',
    }

    if accepted:
        module._validate_expected_literal_env(service, **kwargs)
        patched = module.patch_service(
            service,
            project_number='208440318997',
            base_revision='desktop-backend-base',
            latest_created_revision='desktop-backend-base',
            final_revision='desktop-backend-final',
            ingress_container_name='desktop-backend-1',
            config_secret='cloud-run-gmp-config',
            config_secret_version='7',
        )
        serialized = yaml.load(yaml.safe_dump(patched), Loader=module.GcloudExportLoader)
        kwargs['phase'] = 'rendered sidecar replacement'
        module._validate_expected_literal_env(serialized, **kwargs)
        assert module._ingress_literal_env(serialized, ingress_container_name='desktop-backend-1')[name] == actual_value
    else:
        with pytest.raises(ValueError, match=f'env {name} mismatch'):
            module._validate_expected_literal_env(service, **kwargs)


def test_validate_expected_literal_env_backfill_overlay_does_not_exempt_other_vars():
    module = _load_module()
    service = _service()
    service['metadata']['name'] = 'backend-sync-backfill'
    service['spec']['template']['spec']['containers'][0]['env'] = [
        {
            'name': 'AUDIO_MERGE_HANDLER_URL',
            'value': 'https://backend-sync-backfill-208440318997.us-central1.run.app/v2/sync-jobs/run',
        }
    ]

    with pytest.raises(ValueError, match='env AUDIO_MERGE_HANDLER_URL mismatch'):
        module._validate_expected_literal_env(
            service,
            expected={
                'AUDIO_MERGE_HANDLER_URL': 'https://backend-sync-hhibjajaja-uc.a.run.app/v2/audio-merge-jobs/run'
            },
            ingress_container_name='desktop-backend-1',
            phase='exported base revision',
        )


def test_validate_expected_literal_env_accepts_empty_string_matching_a_missing_value_key():
    module = _load_module()
    service = {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {'name': 'backend-1', 'env': [{'name': 'OMI_PARITY_PACK_ALLOWED_PRINCIPALS'}]},
                    ]
                }
            }
        }
    }

    # Must not raise.
    module._validate_expected_literal_env(
        service,
        expected={'OMI_PARITY_PACK_ALLOWED_PRINCIPALS': ''},
        ingress_container_name='backend-1',
        phase='exported base revision',
    )


def test_validate_expected_literal_env_still_fails_closed_for_a_genuinely_absent_var():
    """This guard exists to catch real env drift before a sidecar replace.

    The fix must make it read Cloud Run correctly, not make it more permissive
    about genuine drift: a var that is not present in the export at all must
    still report <missing> and raise.
    """
    module = _load_module()
    service = {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {'name': 'backend-1', 'env': [{'name': 'SAFE', 'value': 'kept'}]},
                    ]
                }
            }
        }
    }

    with pytest.raises(ValueError, match="expected '', found '<missing>'"):
        module._validate_expected_literal_env(
            service,
            expected={'OMI_PARITY_PACK_ALLOWED_PRINCIPALS': ''},
            ingress_container_name='backend-1',
            phase='exported base revision',
        )


@pytest.mark.parametrize('prepared_version', [None, '11'])
def test_attach_accepts_a_literal_cloud_run_omits_for_being_empty(monkeypatch, tmp_path, prepared_version) -> None:
    """End-to-end regression for the production failure blocking dev deploys.

    ``ValueError: exported base revision env OMI_PARITY_PACK_ALLOWED_PRINCIPALS
    mismatch ... expected '', found '<missing>'`` -- the export legitimately
    omits `value` for this var because it is set to '', and Cloud Run never
    writes `value: ''`. attach_sidecar must complete instead of refusing.
    """
    module = _load_module()
    expected_state = tmp_path / 'runtime-env-state.json'
    expected_state.write_text(
        json.dumps(
            {
                'services': {
                    'backend': {
                        'env': [
                            {'name': 'OMI_PARITY_PACK_ALLOWED_PRINCIPALS', 'value': ''},
                        ]
                    }
                }
            }
        ),
        encoding='utf-8',
    )
    config = tmp_path / 'cloud-run-gmp-sidecar.yaml'
    config.write_text('kind: RunMonitoring\n', encoding='utf-8')

    export = """\
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: backend
spec:
  template:
    metadata: {}
    spec:
      containers:
      - name: backend-1
        env:
        - name: OMI_PARITY_PACK_ALLOWED_PRINCIPALS
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: openai-api-key
              key: latest
  traffic:
  - latestRevision: false
    revisionName: backend-serving
    percent: 100
"""

    calls: list[list[str]] = []

    def fake_run(args, *, capture_output=False):
        calls.append(list(args))
        if '--format=export' in args:
            return module.subprocess.CompletedProcess(args, 0, export, '')
        if '--format=value(status.latestCreatedRevisionName)' in args:
            return module.subprocess.CompletedProcess(args, 0, 'backend-base\n', '')
        if args[1:4] == ['run', 'services', 'replace']:
            rendered = yaml.load(Path(args[4]).read_text(), Loader=module.GcloudExportLoader)
            volumes = rendered['spec']['template']['spec']['volumes']
            config_volume = next(v for v in volumes if v['name'] == module.CONFIG_VOLUME_NAME)
            assert config_volume['secret']['items'][0]['key'] == (prepared_version or '7')
            return module.subprocess.CompletedProcess(args, 0, '{}', '')
        if '--format=value(status.url)' in args:
            return module.subprocess.CompletedProcess(args, 0, 'https://backend.example\n', '')
        raise AssertionError(args)

    def ensure_version(**kwargs):
        assert prepared_version is None, 'prepared attachment must not write or resolve latest'
        return '7'

    monkeypatch.setattr(module, 'ensure_config_secret', ensure_version)
    monkeypatch.setattr(module, '_project_number', lambda _project: '1031333818730')
    monkeypatch.setattr(module, '_run', fake_run)

    module.attach_sidecar(
        SimpleNamespace(
            project='based-hardware',
            region='us-central1',
            service='backend',
            base_revision='backend-base',
            final_revision='backend-final',
            ingress_container='backend-1',
            config=config,
            config_secret='cloud-run-gmp-config',
            config_secret_version=prepared_version,
            expected_env_state=expected_state,
            tag='',
            desktop_backend_liveness_probe=False,
        )
    )

    assert any(args[1:4] == ['run', 'services', 'replace'] for args in calls)


# A project ID in run.googleapis.com/secrets crashes the NEXT gcloud run deploy.
# Cloud Run accepts the ID and stores it, so nothing fails at attach time and the
# breakage lands on whoever deploys next. Production carried
# `cloud-run-gmp-config:projects/based-hardware/secrets/cloud-run-gmp-config` and
# every deploy died with "Invalid secret path" until the live service was repaired.
PROJECT_NUMBER = '208440318997'


def test_project_id_path_is_rewritten_to_project_number():
    module = _load_module()
    repaired = module._normalize_secret_annotation(
        'cloud-run-gmp-config:projects/based-hardware/secrets/cloud-run-gmp-config',
        project_number=PROJECT_NUMBER,
    )
    assert repaired == f'cloud-run-gmp-config:projects/{PROJECT_NUMBER}/secrets/cloud-run-gmp-config'


def test_already_numeric_path_needs_no_change():
    module = _load_module()
    annotation = f'cloud-run-gmp-config:projects/{PROJECT_NUMBER}/secrets/cloud-run-gmp-config'
    assert module._normalize_secret_annotation(annotation, project_number=PROJECT_NUMBER) is None


def test_every_entry_is_repaired_not_just_the_sidecar_secret():
    module = _load_module()
    repaired = module._normalize_secret_annotation(
        'other-secret:projects/based-hardware/secrets/other-secret,'
        f'cloud-run-gmp-config:projects/{PROJECT_NUMBER}/secrets/cloud-run-gmp-config',
        project_number=PROJECT_NUMBER,
    )
    assert repaired == (
        f'cloud-run-gmp-config:projects/{PROJECT_NUMBER}/secrets/cloud-run-gmp-config,'
        f'other-secret:projects/{PROJECT_NUMBER}/secrets/other-secret'
    )


@pytest.mark.parametrize('value', ['not-an-entry', '', None])
def test_unrecognised_annotation_is_left_alone_rather_than_guessed_at(value):
    module = _load_module()
    assert module._normalize_secret_annotation(value, project_number=PROJECT_NUMBER) is None


def test_attach_merge_heals_a_stale_entry_for_another_secret():
    module = _load_module()
    merged = module._merge_secret_annotation(
        'other-secret:projects/based-hardware/secrets/other-secret',
        project_number=PROJECT_NUMBER,
        secret='cloud-run-gmp-config',
    )
    assert 'projects/based-hardware/' not in merged
    assert f'other-secret:projects/{PROJECT_NUMBER}/secrets/other-secret' in merged


def test_repair_is_a_no_op_when_the_annotation_is_already_correct(monkeypatch):
    """Idempotence: a second repair run must not issue a services replace."""
    module = _load_module()
    good = f'cloud-run-gmp-config:projects/{PROJECT_NUMBER}/secrets/cloud-run-gmp-config'
    service = {
        'metadata': {'name': 'backend'},
        'spec': {'template': {'metadata': {'annotations': {module.SECRET_ANNOTATION: good}}}},
    }
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if 'describe' in argv:
            return SimpleNamespace(returncode=0, stdout=yaml.safe_dump(service), stderr='')
        raise AssertionError(f'unexpected gcloud call: {argv}')

    monkeypatch.setattr(module, '_run', fake_run)
    monkeypatch.setattr(module, '_project_number', lambda project: PROJECT_NUMBER)
    args = SimpleNamespace(project='based-hardware', region='us-central1', service='backend', dry_run=False)
    assert module.repair_secret_annotations(args) == 0
    assert not any('replace' in argv for argv in calls)


# gcloud's own validation rule, copied verbatim from googlecloudsdk's secret-path
# parser so a vendor upgrade that tightens it fails here rather than on the next
# production deploy. This is the strict consumer that FC-metadata-format-validated-
# only-on-next-read exists for: Cloud Run's API accepts a project ID here, gcloud
# does not, and the mismatch surfaces on an unrelated later deploy.
GCLOUD_SECRET_PATH_RULE = re.compile(r'^projects/[0-9]{1,19}/secrets/[^/:]+$')


@pytest.mark.parametrize(
    'existing',
    [
        None,
        '',
        'cloud-run-gmp-config:projects/based-hardware/secrets/cloud-run-gmp-config',
        'other-secret:projects/based-hardware/secrets/other-secret',
        f'cloud-run-gmp-config:projects/{PROJECT_NUMBER}/secrets/cloud-run-gmp-config',
    ],
)
def test_every_written_entry_satisfies_gclouds_actual_rule(existing):
    module = _load_module()
    merged = module._merge_secret_annotation(existing, project_number=PROJECT_NUMBER, secret='cloud-run-gmp-config')
    for entry in merged.split(','):
        _, _, resource = entry.partition(':')
        assert GCLOUD_SECRET_PATH_RULE.match(resource), f'gcloud would reject {resource!r}'


def test_repair_drops_a_stale_pinned_revision_name_before_replace():
    """A failed deploy leaves its revision name pinned in the export.

    `services replace` then fails with ALREADY_EXISTS because it would recreate
    that exact name with different configuration. Repair must drop the pin.
    """
    module = _load_module()
    service = {
        'spec': {
            'template': {
                'metadata': {
                    'name': 'backend-465cd0f-32620507075-1',
                    'annotations': {module.SECRET_ANNOTATION: 'x:projects/p/secrets/x'},
                }
            }
        }
    }
    removed = module._drop_pinned_revision_name(service)
    assert removed == 'backend-465cd0f-32620507075-1'
    assert 'name' not in service['spec']['template']['metadata']
    # Annotations must survive untouched.
    assert service['spec']['template']['metadata']['annotations'][module.SECRET_ANNOTATION]


def test_dropping_a_pin_that_is_absent_is_not_an_error():
    module = _load_module()
    service = {'spec': {'template': {'metadata': {'annotations': {}}}}}
    assert module._drop_pinned_revision_name(service) is None
    assert module._drop_pinned_revision_name({}) is None


def _job():
    return {
        'apiVersion': 'run.googleapis.com/v1',
        'kind': 'Job',
        'metadata': {'name': 'notifications-job'},
        'spec': {
            'template': {
                'metadata': {
                    'annotations': {
                        'run.googleapis.com/vpc-access-connector': 'keep',
                        'run.googleapis.com/secrets': 'existing:projects/123/secrets/existing',
                    }
                },
                'spec': {
                    'taskCount': 1,
                    'template': {
                        'spec': {
                            'timeoutSeconds': '600',
                            'maxRetries': 0,
                            'serviceAccountName': 'runtime',
                            'containers': [{'image': 'app:sha', 'env': [{'name': 'FLAG', 'value': 'on'}]}],
                        },
                    },
                },
            }
        },
    }


@pytest.mark.parametrize('existing_startup_probe', [False, True])
def test_job_sidecar_preserves_task_settings_and_is_idempotent_without_startup_probes(existing_startup_probe):
    module = _load_module()
    job = _job()
    if existing_startup_probe:
        job['spec']['template']['spec']['template']['spec']['containers'][0]['startupProbe'] = {
            'tcpSocket': {'port': 9090},
            'periodSeconds': 1,
            'timeoutSeconds': 1,
            'failureThreshold': 240,
        }
    kwargs = dict(project_number='123', config_secret='cloud-run-gmp-config', config_secret_version='7')
    patched = module.patch_job(job, **kwargs)
    assert module.patch_job(patched, **kwargs) == patched
    task = patched['spec']['template']['spec']['template']
    assert task['spec']['timeoutSeconds'] == '600'
    assert task['spec']['serviceAccountName'] == 'runtime'
    app, collector = task['spec']['containers']
    assert all('startupProbe' not in container for container in task['spec']['containers'])
    assert {'name': 'FLAG', 'value': 'on'} in app['env']
    assert {'name': 'PROMETHEUS_SIDECAR_PORT', 'value': '9090'} in app['env']
    assert collector['image'] == module.SIDECAR_IMAGE
    assert not collector.get('env'), 'do not deploy reserved service environment variables on a job'
    assert 'export K_SERVICE="${CLOUD_RUN_JOB:?' in collector['args'][0]
    assert 'sleep 35; kill -TERM' in collector['args'][0]
    # depends_on requires a startup probe on the depended-upon container, and
    # jobs cannot carry a reachable one — the dependency annotation must go.
    assert 'run.googleapis.com/container-dependencies' not in patched['spec']['template']['metadata']['annotations']
    assert job['spec']['template']['spec']['template']['spec']['containers'][0].get('name') is None
    assert 'metadata' not in task, 'job task templates must not acquire service annotations'
    annotations = patched['spec']['template']['metadata']['annotations']
    assert annotations['run.googleapis.com/vpc-access-connector'] == 'keep'
    assert annotations['run.googleapis.com/secrets'] == (
        'cloud-run-gmp-config:projects/123/secrets/cloud-run-gmp-config,existing:projects/123/secrets/existing'
    )


def test_detach_job_preserves_runtime_and_repeated_attach_deploy_cycles():
    module = _load_module()
    job = _job()
    task = job['spec']['template']['spec']['template']['spec']
    task['volumes'] = [{'name': 'runtime-secret', 'secret': {'secretName': 'existing'}}]
    task['containers'][0]['volumeMounts'] = [{'name': 'runtime-secret', 'mountPath': '/runtime'}]
    task['containers'][0]['env'].append(
        {'name': 'TOKEN', 'valueFrom': {'secretKeyRef': {'name': 'existing', 'key': '1'}}}
    )
    kwargs = dict(project_number='123', config_secret='cloud-run-gmp-config', config_secret_version='7')
    assert module.detach_job(job) == job
    for sha in ('first', 'second', 'third'):
        attached = module.patch_job(job, **kwargs)
        detached = module.detach_job(attached)
        assert len(attached['spec']['template']['spec']['template']['spec']['containers']) == 2
        assert module.detach_job(detached) == detached
        singleton = detached['spec']['template']['spec']['template']['spec']
        assert len(singleton['containers']) == 1
        assert singleton['containers'][0]['env'] == task['containers'][0]['env']
        assert singleton['containers'][0]['volumeMounts'] == task['containers'][0]['volumeMounts']
        assert singleton['volumes'] == task['volumes']
        assert singleton['timeoutSeconds'] == '600'
        assert singleton['maxRetries'] == 0
        assert singleton['serviceAccountName'] == 'runtime'
        assert detached['spec']['template']['spec']['taskCount'] == 1
        annotations = detached['spec']['template']['metadata']['annotations']
        assert annotations['run.googleapis.com/vpc-access-connector'] == 'keep'
        assert 'run.googleapis.com/container-dependencies' not in annotations
        # Model the action updating only the sole app image before reattaching.
        singleton['containers'][0]['image'] = f'app:{sha}'
        job = detached


@pytest.mark.parametrize('kind, extra', [('Service', False), ('Job', True)])
def test_detach_job_refuses_unexpected_layout(kind, extra):
    module = _load_module()
    job = _job()
    job['kind'] = kind
    if extra:
        job['spec']['template']['spec']['template']['spec']['containers'].append({'name': 'unknown', 'image': 'other'})
    with pytest.raises(ValueError):
        module.detach_job(job)


@pytest.mark.parametrize('initial', ['missing', 'singleton', 'attached'])
def test_detach_cli_skips_missing_and_singleton_and_replaces_attached(monkeypatch, initial):
    module = _load_module()
    state = None if initial == 'missing' else _job()
    if initial == 'attached':
        state = module.patch_job(
            state, project_number='123', config_secret='cloud-run-gmp-config', config_secret_version='7'
        )
    calls = []

    def fake_run(argv, *, capture_output=False):
        nonlocal state
        calls.append(argv)
        assert capture_output
        if argv[3] == 'list':
            assert '--filter=metadata.name=notifications-job' in argv
            output = 'notifications-job\n' if state else ''
        elif argv[3] == 'describe':
            output = yaml.safe_dump(state)
        elif argv[3] == 'replace':
            path = Path(argv[4])
            assert path.stat().st_mode & 0o777 == 0o600
            state = yaml.safe_load(path.read_text())
            output = ''
        else:
            raise AssertionError(argv)
        return SimpleNamespace(returncode=0, stdout=output, stderr='')

    monkeypatch.setattr(module, '_run', fake_run)
    args = SimpleNamespace(service='notifications-job', project='test-project', region='us-central1')
    module.detach_job_sidecar(args)
    module.detach_job_sidecar(args)
    assert sum(argv[3] == 'replace' for argv in calls) == (1 if initial == 'attached' else 0)
    assert all(argv[3] in ('list', 'describe', 'replace') for argv in calls)


@pytest.mark.parametrize('phase', ['list', 'describe', 'replace'])
def test_detach_cli_propagates_gcloud_failures(monkeypatch, phase):
    module = _load_module()
    attached = module.patch_job(
        _job(), project_number='123', config_secret='cloud-run-gmp-config', config_secret_version='7'
    )

    def fake_run(argv, *, capture_output=False):
        if argv[3] == phase:
            return SimpleNamespace(returncode=1, stdout='', stderr='PERMISSION_DENIED')
        output = 'notifications-job\n' if argv[3] == 'list' else yaml.safe_dump(attached)
        return SimpleNamespace(returncode=0, stdout=output, stderr='')

    monkeypatch.setattr(module, '_run', fake_run)
    with pytest.raises(RuntimeError, match='PERMISSION_DENIED'):
        module.detach_job_sidecar(SimpleNamespace(service='notifications-job', project='test', region='us-central1'))


@pytest.mark.parametrize(
    'service_name',
    ['backend-sync', 'backend-sync-backfill', 'backend-integration', 'backend', 'desktop-backend', 'other-service'],
)
@pytest.mark.parametrize('backend_collector_cpu', ['0.25', '1'])
@pytest.mark.parametrize('desktop_collector_cpu', ['0.25', '1'])
def test_collector_resource_profile_survives_render_without_changing_app(
    service_name, backend_collector_cpu, desktop_collector_cpu
):
    module = _load_module()
    source = _service()
    source['metadata']['name'] = service_name
    app = source['spec']['template']['spec']['containers'][0]
    app['resources'] = {'limits': {'cpu': '2', 'memory': '8Gi'}}
    app['env'] = [{'name': 'SAFE', 'value': 'on'}]
    app['startupProbe'] = {'tcpSocket': {'port': 8080}, 'periodSeconds': 10}
    patched = module.patch_service(
        source,
        project_number='123',
        base_revision='base',
        latest_created_revision='base',
        final_revision='final',
        ingress_container_name=app['name'],
        config_secret='cloud-run-gmp-config',
        config_secret_version='7',
        backend_collector_cpu=backend_collector_cpu,
        desktop_collector_cpu=desktop_collector_cpu,
    )
    rendered = yaml.load(yaml.safe_dump(patched), Loader=module.GcloudExportLoader)
    template = rendered['spec']['template']
    assert template['spec']['containers'][0] == app
    collector = next(c for c in template['spec']['containers'] if c['name'] == 'collector')
    assert collector['resources']['limits'] == (
        {'cpu': '0.08', 'memory': '128Mi'}
        if service_name in {'backend-sync', 'backend-sync-backfill', 'backend-integration'}
        else {
            'cpu': {'backend': backend_collector_cpu, 'desktop-backend': desktop_collector_cpu}.get(service_name, '1'),
            'memory': '512Mi',
        }
    )
    assert template['metadata']['annotations']['run.googleapis.com/cpu-throttling'] == 'false'
    assert rendered['spec']['traffic'] == source['spec']['traffic']
    volume = next(v for v in template['spec']['volumes'] if v['name'] == module.CONFIG_VOLUME_NAME)
    assert volume['secret'] == {
        'secretName': 'cloud-run-gmp-config',
        'items': [{'key': '7', 'path': 'config.yaml'}],
    }


def test_desktop_collector_rejects_unqualified_allocation():
    module = _load_module()
    with pytest.raises(ValueError, match='desktop collector CPU must be 0.25 or 1'):
        module.patch_service(
            _service(),
            project_number='123',
            base_revision='base',
            latest_created_revision='base',
            final_revision='final',
            ingress_container_name='desktop-backend-1',
            config_secret='cloud-run-gmp-config',
            config_secret_version='7',
            desktop_collector_cpu='0.08',
        )


def test_sync_scrape_retains_exporter_and_direct_sentinel_consumers():
    root = SCRIPT.parents[2]
    config = yaml.safe_load((root / 'backend/deploy/cloud_run_gmp_sync.yaml').read_text())
    endpoint = config['spec']['endpoints'][0]
    assert endpoint['interval'] == '60s'
    rules = endpoint['metricRelabeling']

    def kept(name, component=''):
        labels = {'__name__': name, 'component': component}
        for rule in rules:
            matched = re.fullmatch(rule['regex'], ';'.join(labels.get(k, '') for k in rule['sourceLabels']))
            if rule['action'] == 'keep' and not matched or rule['action'] == 'drop' and matched:
                return False
        return True

    # The existing dev/prod sync exporter is the authoritative bridge consumer.
    for env in ('dev', 'prod'):
        exporter = yaml.safe_load(
            (
                root
                / f'backend/charts/monitoring/prometheus-stackdriver-exporter/{env}_sync_omi_cloud_run_metrics_exporter.yaml'
            ).read_text()
        )
        for prefix in exporter['stackdriver']['metrics']['prefixes']:
            family = prefix.removeprefix('prometheus.googleapis.com/').rstrip('/')
            assert kept(family + ('events_total' if family.endswith('_') else ''))
            if family.endswith('_'):
                assert kept(family + 'duration_seconds_bucket')
    # Direct GMP consumers: sentinel batch_metrics.py/completion_telemetry.py.
    # fleet_gate/david_gate use logs, durable state and native request_count.
    for name in (
        'omi_batch_pipeline_events_total',
        'omi_batch_pipeline_oldest_age_seconds',
        'omi_batch_ramp_heavy_owner_excluded_total',
        # Shadow admission/CPU recovery outcomes must survive the same filter
        # as the GPU metrics; otherwise gate readouts lose paid/failed units.
        'omi_batch_shadow_outcome_total',
        'omi_batch_shadow_speech_seconds_total',
        'omi_batch_shadow_speech_loss_seconds_total',
        'omi_batch_shadow_gpu_seconds_total',
        'omi_batch_shadow_paid_calls_total',
        'omi_batch_shadow_paid_audio_seconds_total',
        'omi_accept_to_summary_seconds_bucket',
        'omi_accept_to_summary_seconds_count',
        'omi_accept_to_summary_seconds_sum',
        'omi_summary_terminal_total',
        'omi_summary_debt_overdue',
        'omi_summary_debt_oldest_age_seconds',
        'omi_summary_debt_sample_timestamp_seconds',
        'omi_live_session_transcript_outcome_total',
        'omi_firestore_documents_per_operation_bucket',
        # Cost lever G1: Parakeet pool request time by caller.
        'omi_parakeet_request_seconds_bucket',
        'omi_parakeet_request_seconds_sum',
        'omi_parakeet_request_seconds_count',
        # Firestore reads loop: caller/origin attribution and the singleton_loops lease gate.
        'omi_firestore_billed_reads_by_caller_total',
        'omi_firestore_billed_reads_by_origin_total',
        'omi_firestore_caller_label_overflow_total',
        'omi_fsr_leader_lease_total',
        # Legacy dark: drain_census and the soak gates (contract (h)).
        'omi_legacy_sync_mode',
        'omi_legacy_sync_admissions_total',
        'omi_legacy_dark_ack_total',
        'omi_legacy_sync_mode_read_total',
        # A2 job-store shadow: lane 12 parity_read.sh (the A2 sample gate).
        'omi_jobstore_shadow_parity_total',
        # Held-audio recovery gates: narrowing state, cohort resolution and pacing decisions.
        'omi_stt_cap_recovery_cohort_narrowed',
        'omi_stt_cap_cohort_source',
        'omi_stt_cap_cohort_percent',
        'omi_held_recovery_pacing_intents_total',
        'omi_held_recovery_pacing_audio_seconds_total',
        # #23388 cap enforcement: the watch readout for finite allowances
        # (stt-cap-dispatch.md) — decisions and metered provider audio.
        'omi_stt_cap_dispatch_decisions_total',
        'omi_stt_cap_provider_audio_seconds_total',
        # C5 exact-input reuse (2026-10-26): the dedupe hit/miss/checkpoint
        # counters are the soak readout on backend-sync/backfill/backend-integration.
        'conversation_llm_input_dedupe_skipped_total',
        'conversation_llm_input_dedupe_misses_total',
        'conversation_llm_input_dedupe_checkpoint_errors_total',
    ):
        assert kept(name), name
    for component in ('sync', 'summary_delivery', 'storage'):
        assert kept('omi_fallback_total', component)
    for name, component in (
        ('omi_stt_cost_routing_settlements_total', ''),
        ('omi_subscription_events_total', ''),
        ('omi_product_event_total', ''),
        ('omi_vertex_non_dream_flash_after_cutover_attempts_total', ''),
        ('omi_fallback_total', 'stt_live_session'),
        ('omi_fallback_total', 'stt_selection'),
    ):
        assert not kept(name, component)
    shared = yaml.safe_load((root / 'backend/deploy/cloud_run_gmp_sidecar.yaml').read_text())
    # RunMonitoring name becomes native GMP job; direct shadow mappings pin it.
    assert config['metadata']['name'] == shared['metadata']['name']
    assert shared['spec']['endpoints'][0]['interval'] == '30s'
    assert shared['spec']['endpoints'][0]['metricRelabeling'][0]['regex'] == 'omi_.*|conversation_llm_input_dedupe_.*'


def test_legacy_config_preparation_does_not_log_secret_metadata(monkeypatch, tmp_path, capsys):
    module = _load_module()
    config = tmp_path / 'monitoring.yaml'
    config.write_text('kind: RunMonitoring\n')
    calls = []
    monkeypatch.setattr(module, 'ensure_config_secret', lambda **kwargs: calls.append(kwargs) or '918273')
    monkeypatch.setattr(
        module.os.sys,
        'argv',
        [str(SCRIPT), '--project=test', '--prepare-config', f'--config={config}'],
    )
    assert module.main() == 0
    assert len(calls) == 1
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('version', ['', 'latest', '0', '-1'])
def test_prepared_config_rejects_aliases_before_cloud_calls(monkeypatch, version):
    module = _load_module()
    monkeypatch.setattr(module, '_run', lambda *a, **kw: pytest.fail('invalid version reached gcloud'))
    monkeypatch.setattr(
        module.os.sys,
        'argv',
        [str(SCRIPT), '--project=test', '--service=backend', f'--config-secret-version={version}'],
    )
    with pytest.raises(SystemExit, match='positive numeric version'):
        module.main()
