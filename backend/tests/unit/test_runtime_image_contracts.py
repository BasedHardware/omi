import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_DIR / 'scripts' / 'runtime_image_contracts.py'


def _load_contract_module():
    spec = importlib.util.spec_from_file_location('runtime_image_contracts_for_test', SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def contracts_module():
    return _load_contract_module()


def _contract(contracts_module, name):
    return next(contract for contract in contracts_module.load_contracts() if contract.name == name)


def _dockerfile_without(source: Path, omitted_line: str, destination: Path) -> Path:
    text = source.read_text(encoding='utf-8')
    assert omitted_line in text
    destination.write_text(text.replace(omitted_line, ''), encoding='utf-8')
    return destination


def test_registered_runtime_image_sources_are_closed(contracts_module):
    assert contracts_module.check_source_closures(contracts_module.load_contracts()) == []


def test_source_copy_skips_local_openapi_venv(contracts_module, tmp_path):
    source = tmp_path / 'backend'
    source.mkdir()
    (source / 'main.py').write_text('ok\n', encoding='utf-8')
    venv = source / '.openapi-venv'
    venv.mkdir()
    (venv / 'payload').write_text('huge\n', encoding='utf-8')
    dest = tmp_path / 'staged'
    contracts_module._copy_source(source, dest)
    assert (dest / 'main.py').is_file()
    assert not (dest / '.openapi-venv').exists()


def _contract_with_dockerfile(contracts_module, tmp_path, dockerfile_text):
    dockerfile = tmp_path / 'Dockerfile'
    dockerfile.write_text(dockerfile_text, encoding='utf-8')
    return replace(_contract(contracts_module, 'pusher'), dockerfile=dockerfile)


def test_final_stage_rejects_copy_removed_in_a_later_layer(contracts_module, tmp_path):
    contract = _contract_with_dockerfile(
        contracts_module,
        tmp_path,
        'FROM python AS builder\n'
        'RUN mkdir -p /tmp/wheels\n'
        'FROM python\n'
        'COPY --from=builder /tmp/wheels /tmp/wheels\n'
        'RUN pip install /tmp/wheels/*.whl && rm -rf /tmp/wheels\n',
    )

    errors = contracts_module.final_stage_layer_errors(contract)

    assert len(errors) == 1
    assert 'remain in the image manifest' in errors[0]


def test_final_stage_rejects_install_shadowed_by_late_venv_copy(contracts_module, tmp_path):
    contract = _contract_with_dockerfile(
        contracts_module,
        tmp_path,
        'FROM python AS builder\n'
        'RUN python -m venv /opt/venv\n'
        'FROM python\n'
        'ENV PATH="/opt/venv/bin:$PATH"\n'
        'RUN pip install /tmp/package.whl\n'
        'COPY --from=builder /opt/venv /opt/venv\n',
    )

    errors = contracts_module.final_stage_layer_errors(contract)

    assert len(errors) == 1
    assert 'install is shadowed at runtime' in errors[0]


def test_registered_runtime_image_workflows_smoke_their_declared_dockerfile(contracts_module):
    assert contracts_module.workflow_contract_errors(contracts_module.load_contracts()) == []


def test_memory_maintenance_import_smoke_supplies_its_required_nonproduction_config(contracts_module):
    memory_maintenance_job = _contract(contracts_module, 'memory-maintenance-job')

    assert dict(memory_maintenance_job.smoke_environment) == {
        'ENCRYPTION_SECRET': '0123456789abcdef0123456789abcdef',
        'OPENAI_API_KEY': 'fake-memory-maintenance-image-smoke-only',
    }


def test_registered_import_smokes_declare_their_import_time_environment(contracts_module):
    assert contracts_module.import_smoke_environment_errors(contracts_module.load_contracts()) == []


def test_import_smoke_reaching_encryption_without_its_secret_is_rejected(contracts_module):
    notifications_job = _contract(contracts_module, 'notifications-job')
    assert 'utils.encryption' in contracts_module.first_party_import_closure(
        notifications_job, notifications_job.smoke_entrypoints
    )

    undeclared = replace(notifications_job, smoke_environment=())

    errors = contracts_module.import_smoke_environment_errors([undeclared])

    assert len(errors) == 1
    assert 'utils.encryption' in errors[0]
    assert 'ENCRYPTION_SECRET' in errors[0]


def test_pusher_contract_rejects_omitted_shared_package(contracts_module, tmp_path):
    pusher = _contract(contracts_module, 'pusher')
    dockerfile = _dockerfile_without(
        pusher.dockerfile,
        'COPY backend/services/ ./services/\n',
        tmp_path / 'Dockerfile',
    )

    errors = contracts_module.source_closure_errors(replace(pusher, dockerfile=dockerfile))

    assert any('services.conversation_finalization' in error for error in errors)


def test_modal_contract_rejects_omitted_shared_package(contracts_module, tmp_path):
    models = _contract(contracts_module, 'models')
    dockerfile = _dockerfile_without(
        models.dockerfile,
        'COPY backend/utils /app/utils\n',
        tmp_path / 'Dockerfile',
    )

    errors = contracts_module.source_closure_errors(replace(models, dockerfile=dockerfile))

    assert any('utils.stt.speech_profile' in error for error in errors)


def test_relative_import_resolution_keeps_the_current_package(contracts_module):
    level_one = contracts_module.ast.parse('from ._client import db')
    level_two = contracts_module.ast.parse('from ..shared import client')
    source_roots = (BACKEND_DIR,)

    assert 'database._client' in contracts_module._imported_modules(
        level_one, 'database.tasks', source_roots, current_is_package=False
    )
    assert 'database.shared' in contracts_module._imported_modules(
        level_two, 'database.sub.tasks', source_roots, current_is_package=False
    )


def test_pusher_dependency_probe_includes_jsonschema(contracts_module):
    dependencies = contracts_module.third_party_dependency_modules(_contract(contracts_module, 'pusher'))

    assert 'jsonschema' in dependencies
    assert not any(
        dependency == 'omi_plugin_sdk' or dependency.startswith('omi_plugin_sdk.') for dependency in dependencies
    )


def test_dependency_probe_checks_dotted_module_when_namespace_exists(contracts_module, monkeypatch, tmp_path):
    contract = replace(
        _contract(contracts_module, 'pusher'),
        entrypoints=('entrypoint',),
        entrypoint_source_root=tmp_path,
        source_root=tmp_path,
    )
    (tmp_path / 'entrypoint.py').write_text('from google.cloud import tasks_v2\n', encoding='utf-8')

    dependencies = contracts_module.third_party_dependency_modules(contract)

    assert 'google.cloud.tasks_v2' in dependencies

    monkeypatch.setattr(
        importlib.util,
        'find_spec',
        lambda module: object() if module == 'google' else None,
    )
    monkeypatch.setattr(importlib, 'import_module', lambda _: SimpleNamespace())

    with pytest.raises(AssertionError, match='google.cloud.tasks_v2'):
        exec(contracts_module._dependency_probe_code(('google.cloud.tasks_v2',)), {})


def test_image_smoke_is_network_isolated_and_uses_registered_entrypoint(contracts_module, monkeypatch):
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setattr(contracts_module, 'third_party_dependency_modules', lambda _: ('jsonschema',))
    monkeypatch.setattr(contracts_module.subprocess, 'run', lambda command, check: calls.append(command) or Result())

    assert contracts_module.smoke_image('omi-pusher:test', [_contract(contracts_module, 'pusher')]) == 0

    assert len(calls) == 2
    for call in calls:
        assert call[:6] == ['docker', 'run', '--rm', '--network=none', '--entrypoint', 'python']
        assert '--network=none' in call
    assert 'jsonschema' in calls[0][-1]
    assert 'importlib.util.find_spec' in calls[0][-1]
    assert 'importlib.import_module(parent)' in calls[0][-1]
    assert calls[1][-1] == (
        "import importlib, sys; sys.path.insert(0, '/app'); "
        "import tiktoken; tiktoken.encoding_for_model = lambda _: None; "
        "importlib.import_module('routers.pusher')"
    )


def test_image_smoke_uses_registered_python_executable(contracts_module, monkeypatch):
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setattr(contracts_module, 'third_party_dependency_modules', lambda _: ('torch',))
    monkeypatch.setattr(contracts_module.subprocess, 'run', lambda command, check: calls.append(command) or Result())

    assert contracts_module.smoke_image('omi-nllb:test', [_contract(contracts_module, 'nllb-translation')]) == 0

    assert calls[0][:6] == ['docker', 'run', '--rm', '--network=none', '--entrypoint', 'python3']


def test_memory_maintenance_smoke_uses_a_non_production_openai_key(contracts_module, monkeypatch):
    calls = []

    class Result:
        returncode = 0

    memory_job = _contract(contracts_module, 'memory-maintenance-job')
    assert memory_job.smoke_environment == (
        ('ENCRYPTION_SECRET', '0123456789abcdef0123456789abcdef'),
        ('OPENAI_API_KEY', 'fake-memory-maintenance-image-smoke-only'),
    )

    monkeypatch.setattr(contracts_module, 'third_party_dependency_modules', lambda _: ())
    monkeypatch.setattr(contracts_module.subprocess, 'run', lambda command, check: calls.append(command) or Result())

    assert contracts_module.smoke_image('omi-memory-maintenance:test', [memory_job]) == 0
    assert all('--network=none' in call for call in calls)
    assert all('ENCRYPTION_SECRET=0123456789abcdef0123456789abcdef' in call for call in calls)
    assert all('OPENAI_API_KEY=fake-memory-maintenance-image-smoke-only' in call for call in calls)


def test_build_smoke_uses_the_registered_dockerfile_and_context(contracts_module, monkeypatch):
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setattr(contracts_module, 'third_party_dependency_modules', lambda _: ('jsonschema',))
    monkeypatch.setattr(contracts_module.subprocess, 'run', lambda command, check: calls.append(command) or Result())

    assert contracts_module.build_and_smoke_image('omi-pusher:test', _contract(contracts_module, 'pusher')) == 0

    assert calls[0] == ['docker', 'build', '--file', 'backend/pusher/Dockerfile', '--tag', 'omi-pusher:test', '.']
    assert calls[1][0:11] == [
        'docker',
        'run',
        '--rm',
        '--network=none',
        '--entrypoint',
        'python',
        '--env',
        'ENCRYPTION_SECRET=0123456789abcdef0123456789abcdef',
        '--env',
        'OPENAI_API_KEY=sk-runtime-image-contract-test',
        'omi-pusher:test',
    ]


def test_load_contracts_dockerfile_filter_skips_non_matching_entries(contracts_module, monkeypatch, tmp_path):
    """The ``smoke`` command loads contracts against a deploy-staged source tree
    that may contain only the requested image's source surface.  Non-matching
    entries (e.g. ``plugins``) must be skipped before filesystem validation so
    an absent ``plugins/Dockerfile`` does not fail a backend smoke."""
    staged_registry = tmp_path / 'runtime_images.json'
    staged_registry.write_text(
        json.dumps(
            {
                'schema_version': 1,
                'images': [
                    {
                        'name': 'backend',
                        'dockerfile': 'backend/Dockerfile',
                        'deployment_workflows': ['.github/workflows/gcp_backend.yml'],
                        'build_context': '.',
                        'source_root': 'backend',
                        'workdir': '/app',
                        'entrypoints': ['main'],
                        'image_import_smoke': False,
                        'dependency_probe_smoke': True,
                        'pull_request_smoke': True,
                    },
                    {
                        'name': 'plugins',
                        'dockerfile': 'plugins/Dockerfile',
                        'deployment_workflows': ['.github/workflows/gcp_plugins.yml'],
                        'build_context': '.',
                        'source_root': 'plugins',
                        'workdir': '/app',
                        'entrypoints': ['main'],
                        'image_import_smoke': True,
                        'dependency_probe_smoke': True,
                        'pull_request_smoke': True,
                    },
                ],
            }
        ),
        encoding='utf-8',
    )

    # Stage only the backend + .github surfaces (mirrors deploy-backend-stack)
    staged_root = tmp_path / 'repo'
    (staged_root / 'backend').mkdir(parents=True)
    (staged_root / 'backend' / 'Dockerfile').write_text('FROM python:3.11\n', encoding='utf-8')
    (staged_root / '.github' / 'workflows').mkdir(parents=True)
    (staged_root / '.github' / 'workflows' / 'gcp_backend.yml').write_text('name: backend\n', encoding='utf-8')
    # plugins/Dockerfile is intentionally absent — it is not part of the staged
    # backend deploy surface.

    monkeypatch.setattr(contracts_module, 'REPOSITORY_ROOT', staged_root)

    backend_filter = staged_root / 'backend' / 'Dockerfile'
    filtered = contracts_module.load_contracts(staged_registry, dockerfile_filter=backend_filter)

    assert [c.name for c in filtered] == ['backend']
