from __future__ import annotations

import importlib.util
import json
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
                expected_env_state=expected_state,
                tag='',
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


def test_attach_accepts_a_literal_cloud_run_omits_for_being_empty(monkeypatch, tmp_path) -> None:
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
            return module.subprocess.CompletedProcess(args, 0, '{}', '')
        if '--format=value(status.url)' in args:
            return module.subprocess.CompletedProcess(args, 0, 'https://backend.example\n', '')
        raise AssertionError(args)

    monkeypatch.setattr(module, 'ensure_config_secret', lambda **kwargs: '7')
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
            expected_env_state=expected_state,
            tag='',
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
