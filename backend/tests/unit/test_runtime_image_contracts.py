import importlib.util
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


def test_registered_runtime_image_workflows_smoke_their_declared_dockerfile(contracts_module):
    assert contracts_module.workflow_contract_errors(contracts_module.load_contracts()) == []


def test_memory_maintenance_import_smoke_supplies_its_required_nonproduction_config(contracts_module):
    memory_maintenance_job = _contract(contracts_module, 'memory-maintenance-job')

    assert dict(memory_maintenance_job.smoke_environment) == {
        'ENCRYPTION_SECRET': '0123456789abcdef0123456789abcdef',
        'OPENAI_API_KEY': 'fake-memory-maintenance-image-smoke-only',
    }


def test_pusher_contract_rejects_omitted_shared_package(contracts_module, tmp_path):
    pusher = _contract(contracts_module, 'pusher')
    dockerfile = _dockerfile_without(
        pusher.dockerfile,
        'COPY backend/services/ ./services/\n',
        tmp_path / 'Dockerfile',
    )

    errors = contracts_module.source_closure_errors(replace(pusher, dockerfile=dockerfile))

    assert any('services.conversation_finalization' in error for error in errors)


def test_agent_proxy_contract_rejects_omitted_individual_file(contracts_module, tmp_path):
    agent_proxy = _contract(contracts_module, 'agent-proxy')
    dockerfile = _dockerfile_without(
        agent_proxy.dockerfile,
        'COPY backend/utils/executors.py ./utils/executors.py\n',
        tmp_path / 'Dockerfile',
    )

    errors = contracts_module.source_closure_errors(replace(agent_proxy, dockerfile=dockerfile))

    assert any('utils.executors' in error for error in errors)


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
