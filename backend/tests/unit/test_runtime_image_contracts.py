import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
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


@pytest.fixture(scope='module')
def dependencies_module():
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    try:
        import runtime_image_dependencies
    finally:
        sys.path.remove(str(SCRIPT_PATH.parent))
    return runtime_image_dependencies


def _contract(contracts_module, name):
    return next(contract for contract in contracts_module.load_contracts() if contract.name == name)


def _dockerfile_without(source: Path, omitted_line: str, destination: Path) -> Path:
    text = source.read_text(encoding='utf-8')
    assert omitted_line in text
    destination.write_text(text.replace(omitted_line, ''), encoding='utf-8')
    return destination


# The registered-source closure walk used to live here as one ~183s test; it
# moved to test_runtime_image_source_closures_half_{a,b}.py (parity of the
# sorted contract name) so no single shard lane carries the whole walk.


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


@pytest.mark.parametrize('scratch', ['_temp', '_samples', '_speech_profiles', '_segments'])
def test_source_copy_skips_untracked_scratch_directories(contracts_module, tmp_path, scratch):
    source = tmp_path / 'backend'
    source.mkdir()
    (source / 'main.py').write_text('ok\n', encoding='utf-8')
    (source / scratch).mkdir()
    (source / scratch / 'written-by-a-test.bin').write_text('transient\n', encoding='utf-8')
    dest = tmp_path / 'staged'
    contracts_module._copy_source(source, dest)
    assert (dest / 'main.py').is_file()
    assert not (dest / scratch).exists()


def test_scratch_directory_names_do_not_hide_nested_source(contracts_module, tmp_path):
    source = tmp_path / 'backend'
    (source / 'utils' / '_segments').mkdir(parents=True)
    (source / 'utils' / '_segments' / 'merge.py').write_text('ok\n', encoding='utf-8')
    (source / 'utils' / '_temp').mkdir()
    (source / 'utils' / '_temp' / 'helper.py').write_text('ok\n', encoding='utf-8')
    dest = tmp_path / 'staged'
    contracts_module._copy_source(source, dest)
    assert (dest / 'utils' / '_segments' / 'merge.py').is_file()
    assert (dest / 'utils' / '_temp' / 'helper.py').is_file()


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


def test_a_commented_smoke_marker_does_not_satisfy_the_workflow_contract(contracts_module, monkeypatch):
    contract = next(c for c in contracts_module.load_contracts() if c.name == 'backend-api')
    commented = 'steps:\n  # runtime_image_contracts.py smoke\n  - name: build backend/Dockerfile.roles\n'
    monkeypatch.setattr(contracts_module, '_workflow_contract_text', lambda _: commented)
    assert contracts_module.workflow_contract_errors([contract]) == [
        'backend-api: .github/workflows/gcp_backend.yml does not smoke its registered runtime image'
    ]
    real = commented + '    run: python3 backend/scripts/role_images.py verify --manifest m\n'
    monkeypatch.setattr(contracts_module, '_workflow_contract_text', lambda _: real)
    assert contracts_module.workflow_contract_errors([contract]) == []


def test_x_connector_sync_import_smoke_supplies_its_required_nonproduction_config(contracts_module):
    x_connector_sync_job = _contract(contracts_module, 'x-connector-sync-job')

    assert dict(x_connector_sync_job.smoke_environment) == {
        'ENCRYPTION_SECRET': '0123456789abcdef0123456789abcdef',
        'OPENAI_API_KEY': 'fake-x-connector-sync-image-smoke-only',
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


def test_import_scans_observe_source_changes_between_invocations(contracts_module, tmp_path):
    (tmp_path / 'main.py').write_text('import package\nimport added\n', encoding='utf-8')
    package = tmp_path / 'package'
    package.mkdir()
    (package / '__init__.py').write_text('import json\n', encoding='utf-8')
    dockerfile = tmp_path / 'Dockerfile'
    dockerfile.write_text('FROM python\nWORKDIR /app\nCOPY main.py ./\nCOPY package/ ./package/\n', encoding='utf-8')
    contract = replace(
        _contract(contracts_module, 'pusher'),
        dockerfile=dockerfile,
        target=None,
        build_context=tmp_path,
        source_root=tmp_path,
        entrypoint_source_root=tmp_path,
        entrypoints=('main',),
    )

    def assert_external():
        assert contracts_module.source_closure_errors(contract) == []
        assert 'added' not in contracts_module.first_party_import_closure(contract, contract.entrypoints)
        assert 'added' in contracts_module.third_party_dependency_modules(contract)

    assert_external()
    added = tmp_path / 'added.py'
    added.write_text('import external_dependency\n', encoding='utf-8')
    assert any("'added'" in error for error in contracts_module.source_closure_errors(contract))
    assert 'added' in contracts_module.first_party_import_closure(contract, contract.entrypoints)
    dependencies = contracts_module.third_party_dependency_modules(contract)
    assert 'external_dependency' in dependencies
    assert 'added' not in dependencies
    added.unlink()
    assert_external()


def test_shared_import_parse_keeps_lazy_imports_and_each_image_copy_surface(contracts_module, tmp_path):
    (tmp_path / 'main.py').write_text(
        'def lazy():\n    import added\nclass Nested:\n    from package import child\n', encoding='utf-8'
    )
    (tmp_path / 'added.py').write_text('import json\n', encoding='utf-8')
    package = tmp_path / 'package'
    package.mkdir()
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / 'child.py').write_text('import json\n', encoding='utf-8')
    contracts = []
    for name, copies in (
        ('complete', 'COPY added.py ./\nCOPY package/ ./package/\n'),
        ('missing-lazy', 'COPY package/ ./package/\n'),
        ('missing-child', 'COPY added.py ./\nCOPY package/__init__.py ./package/__init__.py\n'),
    ):
        dockerfile = tmp_path / name
        dockerfile.write_text('FROM python\nWORKDIR /app\nCOPY main.py ./\n' + copies, encoding='utf-8')
        contracts.append(
            replace(
                _contract(contracts_module, 'pusher'),
                name=name,
                dockerfile=dockerfile,
                target=None,
                build_context=tmp_path,
                source_root=tmp_path,
                entrypoint_source_root=tmp_path,
                entrypoints=('main',),
            )
        )

    errors = contracts_module.check_source_closures(contracts)
    assert not any(error.startswith('complete:') for error in errors)
    assert any(error.startswith('missing-lazy:') and "'added'" in error for error in errors)
    assert any(error.startswith('missing-child:') and "'package.child'" in error for error in errors)


def test_shared_staging_keeps_context_and_entrypoint_boundaries(contracts_module, tmp_path):
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    (first / 'main.py').write_text('import json\n')
    (first / 'other.py').write_text('import json\n')
    (second / 'main.py').write_text('import missing\n')
    (second / 'missing.py').write_text('import json\n')
    dockerfile = tmp_path / 'Dockerfile'
    dockerfile.write_text('FROM python\nWORKDIR /app\nCOPY main.py ./\n')
    template = replace(
        _contract(contracts_module, 'pusher'),
        dockerfile=dockerfile,
        target=None,
        build_context=first,
        source_root=first,
        entrypoint_source_root=first,
        entrypoints=('main',),
    )
    contracts = [
        replace(template, name='complete'),
        replace(template, name='other-entrypoint', entrypoints=('other',)),
        replace(
            template, name='other-context', build_context=second, source_root=second, entrypoint_source_root=second
        ),
    ]

    errors = contracts_module.check_source_closures(contracts)

    assert not any(error.startswith('complete:') for error in errors)
    assert any(error.startswith('other-entrypoint:') and "'other'" in error for error in errors)
    assert any(error.startswith('other-context:') and "'missing'" in error for error in errors)
    # The same COPY key must be restaged after a source edit, even after errors.
    (first / 'main.py').write_text('def lazy():\n    import other\n')
    errors = contracts_module.check_source_closures(contracts)
    assert any(error.startswith('complete:') and "'other'" in error for error in errors)
    (first / 'main.py').write_text('import json\n')
    assert contracts_module.check_source_closures([contracts[0]]) == []


def test_shared_staging_still_validates_each_workdir(contracts_module, tmp_path):
    from pathlib import PurePosixPath

    (tmp_path / 'main.py').write_text('import json\n')
    dockerfile = tmp_path / 'Dockerfile'
    dockerfile.write_text('FROM python\nWORKDIR /app\nCOPY main.py /app/main.py\n')
    contract = replace(
        _contract(contracts_module, 'pusher'),
        dockerfile=dockerfile,
        target=None,
        build_context=tmp_path,
        source_root=tmp_path,
        entrypoint_source_root=tmp_path,
        entrypoints=('main',),
        workdir=PurePosixPath('/app'),
    )

    with pytest.raises(contracts_module.ContractError, match='outside WORKDIR'):
        contracts_module.check_source_closures([contract, replace(contract, workdir=PurePosixPath('/elsewhere'))])


def test_shared_import_summary_observes_edits_and_invalid_syntax(contracts_module, tmp_path):
    source = tmp_path / 'main.py'
    source.write_text('import json\n')
    contract = replace(
        _contract(contracts_module, 'pusher'),
        source_root=tmp_path,
        entrypoint_source_root=tmp_path,
    )
    trees = {}
    assert 'added' not in contracts_module.first_party_import_closure(contract, ('main',), _import_trees=trees)

    source.write_text('class Nested:\n    def lazy(self):\n        from package import child\n')
    package = tmp_path / 'package'
    package.mkdir()
    (package / 'child.py').write_text('import json\n')
    assert 'package.child' in contracts_module.first_party_import_closure(contract, ('main',), _import_trees=trees)
    source.write_text('def broken(:\n')
    with pytest.raises(SyntaxError):
        contracts_module.first_party_import_closure(contract, ('main',), _import_trees=trees)


def test_pusher_dependency_probe_includes_jsonschema(contracts_module):
    pusher = _contract(contracts_module, 'pusher')
    dependencies = contracts_module.third_party_dependency_modules(pusher)
    closure = contracts_module.first_party_import_closure(pusher, pusher.entrypoints)

    assert 'jsonschema' in dependencies
    assert not any(
        dependency == 'omi_plugin_sdk' or dependency.startswith('omi_plugin_sdk.') for dependency in dependencies
    )
    assert 'utils.conversations.transcription_shadow' in closure
    assert 'utils.sync.speaker_identity' in closure
    assert 'utils.sync.pipeline' not in closure
    assert not {dependency.split('.', 1)[0] for dependency in dependencies} & {
        'imageio_ffmpeg',
        'onnxruntime',
        'torch',
        'pyannote',
        'speechbrain',
    }


def test_structured_model_fallback_imports_without_plugin_sdk(tmp_path):
    models_root = tmp_path / 'models'
    models_root.mkdir()
    shutil.copy(BACKEND_DIR / 'models' / '__init__.py', models_root / '__init__.py')
    shutil.copy(BACKEND_DIR / 'models' / 'conversation_enums.py', models_root / 'conversation_enums.py')
    shutil.copy(BACKEND_DIR / 'models' / 'structured.py', models_root / 'structured.py')
    shutil.copy(BACKEND_DIR / 'models' / 'task_due.py', models_root / 'task_due.py')

    probe = '''
import builtins

real_import = builtins.__import__

def block_optional_sdk(name, *args, **kwargs):
    if name == "omi_plugin_sdk" or name.startswith("omi_plugin_sdk."):
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)

builtins.__import__ = block_optional_sdk
from models import structured

assert structured.ActionItem.__module__ == "models.structured"
assert structured.Event.__module__ == "models.structured"
assert structured.Section.__module__ == "models.structured"
assert structured.Structured(title="fallback").title == "fallback"
'''
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, '-c', probe],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        'SDK-absent fallback import failed; ' f'stdout={result.stdout[-2000:]!r} stderr={result.stderr[-2000:]!r}'
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


def test_dependency_probe_reports_the_underlying_import_exception(contracts_module, monkeypatch):
    """Image smoke must show why an installed distribution still fails to import."""

    def raise_audio_metadata(name):
        raise AttributeError("module 'torchaudio' has no attribute 'AudioMetaData'")

    monkeypatch.setattr(importlib.util, 'find_spec', raise_audio_metadata)
    monkeypatch.setattr(importlib, 'import_module', raise_audio_metadata)

    with pytest.raises(
        AssertionError,
        match=(
            "missing installed dependency modules: pyannote.audio.Pipeline; "
            "pyannote.audio.Pipeline: AttributeError: module 'torchaudio' has no attribute 'AudioMetaData'"
        ),
    ):
        exec(contracts_module._dependency_probe_code(('pyannote.audio.Pipeline',)), {})


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


def _requirement_pin(requirements_text: str, package: str) -> str:
    prefix = f'{package}=='
    for line in requirements_text.splitlines():
        if line.startswith(prefix):
            return line
    raise AssertionError(f'{package} pin missing from requirements')


def test_pusher_installs_typesense_because_finalization_indexes_conversations():
    """process_conversation → lifecycle → typesense_index is reachable in the pusher image.

    Auto-deploy smoke failed from 2026-09-01 onward with
    missing installed dependency modules: typesense / typesense.exceptions.ObjectNotFound
    because the module was on backend/requirements.txt but not the pusher subset.
    """
    pusher = (BACKEND_DIR / 'pusher' / 'requirements.txt').read_text(encoding='utf-8')
    backend = (BACKEND_DIR / 'requirements.txt').read_text(encoding='utf-8')
    assert _requirement_pin(pusher, 'typesense') == _requirement_pin(backend, 'typesense')
    pylock = (BACKEND_DIR / 'pusher' / 'pylock.toml').read_text(encoding='utf-8')
    assert 'name = "typesense"' in pylock


def test_pusher_imageio_ffmpeg_exclusion_keeps_its_system_ffmpeg_fallback():
    """PR #22839 made chat_file lazily reach the messaging FFmpeg decoder from pusher.main.

    The pusher image excludes imageio_ffmpeg from its dependency probe instead of
    installing the wheel. That holds only while the wheel import stays inside a
    function (with the system fallback) and the pusher image installs ffmpeg.
    """
    import ast

    decoder = BACKEND_DIR / 'utils' / 'messaging' / 'adapters' / 'decoder.py'
    tree = ast.parse(decoder.read_text(encoding='utf-8'))
    top_level_imports = {alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names} | {
        node.module for node in tree.body if isinstance(node, ast.ImportFrom) and node.module
    }
    assert 'imageio_ffmpeg' not in top_level_imports
    assert "shutil.which('ffmpeg')" in decoder.read_text(encoding='utf-8')

    dockerfile = (BACKEND_DIR / 'pusher' / 'Dockerfile').read_text(encoding='utf-8')
    assert 'install --no-install-recommends ffmpeg' in dockerfile


def test_pusher_posthog_pin_matches_backend_cohort_flag_client():
    """PR #20533 enabled cohort dispatch, but pusher lacked the lazy PostHog SDK."""
    pusher = (BACKEND_DIR / 'pusher' / 'requirements.txt').read_text(encoding='utf-8')
    backend = (BACKEND_DIR / 'requirements.txt').read_text(encoding='utf-8')
    pin = _requirement_pin(backend, 'posthog')
    assert _requirement_pin(pusher, 'posthog') == pin
    lock = tomllib.loads((BACKEND_DIR / 'pusher' / 'pylock.toml').read_text(encoding='utf-8'))
    packages = {package['name']: package['version'] for package in lock['packages']}
    assert packages['posthog'] == pin.split('==', 1)[1]


def test_pusher_lock_covers_mentor_v2_lazy_imports():
    """Packages audited in the pusher-only venv, including function-local imports.

    PR #20533's cohort dispatch exposed a missing lazy PostHog import that the
    static entrypoint smoke did not see. Keep this audited package contract
    independent of the full backend environment, where PostHog was installed.
    Jev dedupe/usefulness use gateway_client's httpx transport, not another SDK.
    """
    module_distributions = {
        'anthropic': 'anthropic',
        'cachetools': 'cachetools',
        'cryptography': 'cryptography',
        'fastapi': 'fastapi',
        'firebase_admin': 'firebase-admin',
        'google.api_core': 'google-api-core',
        'google.auth': 'google-auth',
        'google.oauth2': 'google-auth',
        'google.protobuf': 'protobuf',
        'google.cloud.exceptions': 'google-cloud-core',
        'google.cloud.firestore': 'google-cloud-firestore',
        'google.cloud.firestore_v1': 'google-cloud-firestore',
        'google.cloud.storage': 'google-cloud-storage',
        'google.cloud.tasks_v2': 'google-cloud-tasks',
        'httpx': 'httpx',
        'jsonschema': 'jsonschema',
        'langchain_anthropic': 'langchain-anthropic',
        'langchain_core': 'langchain-core',
        'langchain_google_genai': 'langchain-google-genai',
        'langchain_openai': 'langchain-openai',
        'numpy': 'numpy',
        'openai': 'openai',
        'opuslib': 'opuslib',
        'pinecone': 'pinecone',
        'posthog': 'posthog',
        'prometheus_client': 'prometheus-client',
        'pycountry': 'pycountry',
        'pydantic': 'pydantic',
        'pytz': 'pytz',
        'redis': 'redis',
        'starlette': 'starlette',
        'stripe': 'stripe',
        'tiktoken': 'tiktoken',
        'typesense': 'typesense',
        'ulid': 'python-ulid',
    }
    lock = tomllib.loads((BACKEND_DIR / 'pusher' / 'pylock.toml').read_text(encoding='utf-8'))
    installed_packages = {package['name'] for package in lock['packages']}
    missing = {module: package for module, package in module_distributions.items() if package not in installed_packages}
    assert not missing, f'Mentor v2 modules missing from pusher lock: {missing}'


# Role images (backend target architecture, plan B §B1).

ROLE_DOCKERFILE = 'backend/Dockerfile.roles'
CPU_ROLE_TARGETS = {
    'backend-api': 'api',
    'backend-workers': 'workers',
    'backend-realtime': 'realtime',
    'backend-gateway': 'gateway',
    'backend-pusher': 'pusher',
}


def _registry():
    return json.loads((BACKEND_DIR / 'runtime_images.json').read_text(encoding='utf-8'))


def _image_entry(payload, name):
    return next(image for image in payload['images'] if image['name'] == name)


def _registry_variant(tmp_path, mutate):
    payload = _registry()
    mutate(payload)
    path = tmp_path / 'runtime_images.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_role_map_is_complete(contracts_module):
    assert contracts_module.role_map_errors(contracts_module.load_contracts()) == []


def test_every_declared_service_maps_to_exactly_one_role_image(contracts_module):
    registry = _registry()
    roles_by_image = {}
    for role, spec in registry['roles'].items():
        for image in spec['images']:
            roles_by_image.setdefault(image, []).append(role)
    assert all(len(roles) == 1 for roles in roles_by_image.values()), roles_by_image

    # native_images join the map with the role their own entry declares.
    for name, spec in registry.get('native_images', {}).items():
        roles_by_image.setdefault(name, []).append(spec['role'])

    declared = set(registry['services']) | set(registry['logging_chart_images'])
    assert declared == set(registry['services'])
    for service in declared:
        spec = registry['services'][service]
        assert roles_by_image[spec['image']] == [spec['role']], service


def test_cpu_role_images_build_from_one_dockerfile_and_share_layers(contracts_module):
    contracts = {contract.name: contract for contract in contracts_module.load_contracts()}
    dockerfile = BACKEND_DIR.parent / ROLE_DOCKERFILE
    for name, target in CPU_ROLE_TARGETS.items():
        contract = contracts[name]
        # B2: the gcp_backend.yml build-only train publishes every role image (not deployed until opt-in).
        assert (contract.dockerfile, contract.target, contract.build_only) == (dockerfile, target, False)
        assert contract.deployment_workflows == (BACKEND_DIR.parent / '.github/workflows/gcp_backend.yml',)
        assert contract.dependency_probe_smoke and contract.pull_request_smoke

    # api/workers/realtime/gateway differ from `app` only in metadata (ENV/CMD/ARG/LABEL),
    # so one train pushes their filesystem layers once.
    app = contracts_module.docker_target_instructions(dockerfile, 'app')
    os_base = contracts_module.docker_target_instructions(dockerfile, 'os-base')
    for target in ('api', 'workers', 'realtime', 'gateway', 'pusher'):
        chain = contracts_module.docker_target_instructions(dockerfile, target)
        shared = os_base if target == 'pusher' else app
        assert chain[: len(shared)] == shared
        if target != 'pusher':
            assert {line.split()[0] for line in chain[len(shared) :]} <= {'ENV', 'CMD', 'ARG', 'LABEL'}
        assert chain[-3:] == list(contracts_module.RELEASE_STAMP_LINES)


def test_role_images_keep_todays_dependency_surface(contracts_module):
    """B1 changes image shape, not dependencies: each role target reuses the lock its service ships today."""
    contracts = {contract.name: contract for contract in contracts_module.load_contracts()}
    for name in ('backend-api', 'backend-workers', 'backend-realtime', 'backend-gateway'):
        assert contracts[name].dependency_probe_exclusions == contracts['backend'].dependency_probe_exclusions
        # workers also probes the messaging-maintenance CronJob module, which runs on the backend image today.
        assert set(contracts[name].entrypoints) - {'utils.messaging.maintenance'} <= set(
            contracts['backend'].entrypoints
        )
    assert contracts['backend-pusher'].dependency_probe_exclusions == contracts['pusher'].dependency_probe_exclusions
    assert contracts['backend-pusher'].smoke_entrypoints == contracts['pusher'].smoke_entrypoints
    assert _registry()['roles']['realtime']['images']['backend-pusher'] == 'backend/pusher/pylock.toml'


def test_role_pusher_target_copies_the_pusher_source_surface(contracts_module):
    pusher = [c.sources for c in contracts_module.final_stage_copy_instructions(BACKEND_DIR / 'pusher' / 'Dockerfile')]
    role = [
        c.sources
        for c in contracts_module.final_stage_copy_instructions(BACKEND_DIR.parent / ROLE_DOCKERFILE, 'pusher')
    ]
    assert role == pusher


@pytest.mark.parametrize(
    'mutate,expected',
    [
        (lambda p: p['services'].pop('pusher'), 'chart pusher has no role-image service entry'),
        (
            lambda p: p['roles']['api']['images'].update({'backend-workers': 'backend/pylock.runtime.toml'}),
            'belongs to both',
        ),
        (lambda p: p['services']['backend'].update({'image': 'backend-workers'}), 'is not a role image of api'),
        (lambda p: _image_entry(p, 'plugins').pop('outside_role_split'), 'plugins is neither a role image'),
        (lambda p: _image_entry(p, 'backend-api').update({'outside_role_split': 'x'}), 'both a role image and outside'),
        (
            lambda p: p['roles']['gateway']['images'].update({'backend-gateway': 'backend/pusher/pylock.toml'}),
            'does not install its declared lock',
        ),
        (lambda p: p['services']['vad'].update({'current_image': 'parakeet'}), "!= chart image 'models'"),
        (lambda p: p['services'].pop('llm-gateway'), 'backend-gateway serves no declared service'),
        (
            lambda p: p['services']['llm-gateway'].update({'current_deploy': ['.github/workflows/gcp_parakeet.yml']}),
            'gcp_parakeet.yml never names the service',
        ),
        (
            lambda p: p['services']['pusher'].update(
                {'current_deploy': ['.github/workflows/gcp_backend_listen_helm.yml']}
            ),
            "no current_deploy builds pusher's backend/pusher/Dockerfile",
        ),
        (
            lambda p: _image_entry(p, 'backend').update({'build_only': True, 'deployment_workflows': []}),
            'build_only image backend is the current image of',
        ),
        # Re-review false passes: path segments and prose are not deploy targets.
        (
            lambda p: p['services']['backend'].update({'current_deploy': ['.github/workflows/gcp_llm_gateway.yml']}),
            'gcp_llm_gateway.yml never names the service as a deploy target',
        ),
        (
            lambda p: p['services']['backend-listen'].update(
                {'current_deploy': ['.github/workflows/gcp_llm_gateway.yml']}
            ),
            'gcp_llm_gateway.yml never names the service as a deploy target',
        ),
        (
            lambda p: p['services']['backend'].update(
                {'current_deploy': ['.github/workflows/desktop_backend_prod.yml']}
            ),
            "no current_deploy builds backend's backend/Dockerfile",
        ),
        (
            lambda p: p['services']['backend'].update({'image_built_elsewhere': ''}),
            'image_built_elsewhere must be a non-empty reason',
        ),
        # Third-pass false passes: a quoted assertion, a log filter and an image tag.
        (
            lambda p: p['services']['messaging-maintenance'].update(
                {'current_deploy': ['backend/tests/unit/test_messaging_operations.py']}
            ),
            'test_messaging_operations.py never names the service as a deploy target',
        ),
        (
            lambda p: p['services']['backend-sync']['current_deploy'].append(
                '.github/actions/sync-backfill-lifecycle/action.yml'
            ),
            'sync-backfill-lifecycle/action.yml never names the service as a deploy target',
        ),
        (
            lambda p: p['services']['backend']['current_deploy'].append(
                '.github/workflows/gcp_backend_listen_helm.yml'
            ),
            'gcp_backend_listen_helm.yml never names the service as a deploy target',
        ),
        # Native service entries: the registry's native_images join the role -> image -> service map.
        (
            lambda p: p['services'].pop('listen-edge'),
            'native image listen-edge serves no declared service',
        ),
        (
            lambda p: p['services']['listen-edge'].update({'role': 'gateway'}),
            'is not a role image of gateway',
        ),
        (
            lambda p: p['services']['listen-edge'].pop('image_built_elsewhere'),
            'a native current_image needs an image_built_elsewhere reason',
        ),
    ],
)
def test_role_map_rejects_incomplete_or_ambiguous_maps(contracts_module, tmp_path, mutate, expected):
    registry = _registry_variant(tmp_path, mutate)
    errors = contracts_module.role_map_errors(contracts_module.load_contracts(registry), registry)
    assert any(expected in error for error in errors), errors


def test_role_target_without_release_stamp_is_rejected(contracts_module, tmp_path):
    dockerfile = tmp_path / 'Dockerfile.roles'
    dockerfile.write_text(
        'FROM python AS api\n'
        'COPY backend/pylock.runtime.toml /tmp/pylock.runtime.toml\n'
        'ARG OMI_RELEASE_SHA=unknown\n'
        'ENV OMI_RELEASE_SHA=${OMI_RELEASE_SHA}\n'
        'LABEL org.opencontainers.image.revision=${OMI_RELEASE_SHA}\n'
        'CMD ["uvicorn", "main:app"]\n',
        encoding='utf-8',
    )
    contracts = [
        replace(contract, dockerfile=dockerfile) if contract.name == 'backend-api' else contract
        for contract in contracts_module.load_contracts()
    ]
    errors = contracts_module.role_map_errors(contracts)
    assert any('target api must end with the release stamp' in error for error in errors), errors


def test_dockerfile_and_deploy_target_matches_are_bounded(contracts_module):
    mentions = contracts_module._mentions_dockerfile
    assert mentions('-f backend/diarizer/Dockerfile .', 'backend/diarizer/Dockerfile')
    assert not mentions('-f backend/diarizer/Dockerfile.batch-pipeline .', 'backend/diarizer/Dockerfile')
    assert not mentions('file: backend/Dockerfile.desktop_backend', 'backend/Dockerfile')

    names = contracts_module._names_deploy_target
    assert names('env:\n  SERVICE: llm-gateway\n', 'llm-gateway')
    assert names('gcloud run deploy --service=backend-sync \\', 'backend-sync')
    assert names('"name": "projects/p/locations/l/jobs/messaging-maintenance-job",', 'messaging-maintenance-job')
    assert not names('python backend/scripts/x.py backend/charts/backend-listen/values.yaml', 'backend-listen')
    assert not names('# owns the full backend mutation domain', 'backend')
    assert names("params['jobId'] = 'messaging-maintenance-job'", 'messaging-maintenance-job')
    assert not names("assert params['jobId'] == 'messaging-maintenance-job'", 'messaging-maintenance-job')
    assert names('IMAGE_TAG="$TAG" backend/scripts/deploy-llm-gateway.sh', 'llm-gateway')
    assert not names('gcloud container images describe "gcr.io/p/backend:${TAG}"', 'backend')
    assert not names('filter: service_name="backend-sync"', 'backend-sync')


def _role_errors_for_dockerfile(contracts_module, tmp_path, text, image='backend-api'):
    dockerfile = tmp_path / 'Dockerfile.roles'
    dockerfile.write_text(text, encoding='utf-8')
    contracts = [
        replace(contract, dockerfile=dockerfile) if contract.name == image else contract
        for contract in contracts_module.load_contracts()
    ]
    return contracts_module.role_map_errors(contracts)


_STAMP = (
    'ARG OMI_RELEASE_SHA=unknown\n'
    'ENV OMI_RELEASE_SHA=${OMI_RELEASE_SHA}\n'
    'LABEL org.opencontainers.image.revision=${OMI_RELEASE_SHA}\n'
)


def test_copied_but_uninstalled_lock_is_rejected(contracts_module, tmp_path):
    errors = _role_errors_for_dockerfile(
        contracts_module,
        tmp_path,
        'FROM python AS api\n'
        'COPY backend/pylock.runtime.toml /tmp/pylock.runtime.toml\n'
        'COPY backend/pusher/pylock.toml /tmp/pylock.toml\n'
        'RUN uv pip sync /tmp/pylock.toml\n' + _STAMP,
    )
    assert any('does not install its declared lock backend/pylock.runtime.toml' in error for error in errors), errors


def test_installed_lock_and_trailing_stamp_pass(contracts_module, tmp_path):
    errors = _role_errors_for_dockerfile(
        contracts_module,
        tmp_path,
        'FROM python AS api\n'
        'COPY backend/pylock.runtime.toml /tmp/pylock.runtime.toml\n'
        'RUN uv pip sync /tmp/pylock.runtime.toml\n' + _STAMP,
    )
    assert not [error for error in errors if 'backend-api' in error or 'target api' in error], errors


def test_release_sha_referenced_before_the_stamp_is_rejected(contracts_module, tmp_path):
    errors = _role_errors_for_dockerfile(
        contracts_module,
        tmp_path,
        'FROM python AS api\n'
        'ARG OMI_RELEASE_SHA=unknown\n'
        'COPY backend/pylock.runtime.toml /tmp/pylock.runtime.toml\n'
        'RUN uv pip sync /tmp/pylock.runtime.toml\n' + _STAMP,
    )
    assert any('reference OMI_RELEASE_SHA nowhere earlier' in error for error in errors), errors


def test_target_instructions_follow_the_stage_chain_not_copy_from(contracts_module, tmp_path):
    dockerfile = tmp_path / 'Dockerfile'
    dockerfile.write_text(
        'ARG BASE=python\n'
        'FROM ${BASE} AS deps\n'
        'COPY lock /tmp/lock\n'
        'FROM ${BASE} AS base\n'
        'WORKDIR /app\n'
        'FROM base AS app\n'
        'COPY --from=deps /opt/venv /opt/venv\n'
        'COPY src/ .\n'
        'FROM app AS api\n'
        'CMD ["uvicorn", "main:app"]\n'
        'FROM base AS other\n'
        'COPY other/ .\n',
        encoding='utf-8',
    )

    assert contracts_module.docker_target_instructions(dockerfile, 'api') == [
        'WORKDIR /app',
        'COPY --from=deps /opt/venv /opt/venv',
        'COPY src/ .',
        'CMD ["uvicorn", "main:app"]',
    ]
    assert contracts_module.docker_target_instructions(dockerfile) == ['WORKDIR /app', 'COPY other/ .']
    assert [c.sources for c in contracts_module.final_stage_copy_instructions(dockerfile, 'api')] == [('src/',)]
    with pytest.raises(contracts_module.ContractError, match='no build stage'):
        contracts_module.docker_target_instructions(dockerfile, 'missing')


def test_build_smoke_builds_the_registered_target(contracts_module, monkeypatch):
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setenv('GITHUB_SHA', 'abc1234')
    monkeypatch.setattr(contracts_module, 'third_party_dependency_modules', lambda _: ('fastapi',))
    monkeypatch.setattr(contracts_module.subprocess, 'run', lambda command, check: calls.append(command) or Result())

    assert contracts_module.build_and_smoke_image('omi-api:test', _contract(contracts_module, 'backend-api')) == 0

    assert calls[0] == [
        'docker',
        'build',
        '--file',
        ROLE_DOCKERFILE,
        '--target',
        'api',
        '--build-arg',
        'OMI_RELEASE_SHA=abc1234',
        '--tag',
        'omi-api:test',
        '.',
    ]
    assert len(calls) == 2 and calls[1][:3] == ['docker', 'run', '--rm']


def test_smoke_of_a_multi_target_dockerfile_requires_its_target(contracts_module):
    contracts = contracts_module.load_contracts()
    dockerfile = BACKEND_DIR.parent / ROLE_DOCKERFILE
    with pytest.raises(contracts_module.ContractError, match='pass --target'):
        contracts_module.contracts_for_dockerfile(contracts, dockerfile)
    assert [c.name for c in contracts_module.contracts_for_dockerfile(contracts, dockerfile, 'workers')] == [
        'backend-workers'
    ]
    # Single-target Dockerfiles keep today's behaviour.
    assert [c.name for c in contracts_module.contracts_for_dockerfile(contracts, BACKEND_DIR / 'Dockerfile')] == [
        'backend'
    ]


@pytest.mark.parametrize(
    'override,expected',
    [
        ({'deployment_workflows': ['.github/workflows/gcp_backend.yml']}, 'deployment_workflows as []'),
        ({'pull_request_smoke': False}, 'must be true'),
        ({'target': 'nope'}, "target stage 'nope' is not defined"),
    ],
)
def test_build_only_entries_are_validated(contracts_module, tmp_path, override, expected):
    def mutate(payload):
        entry = next(image for image in payload['images'] if image['name'] == 'backend-api')
        entry.update({'build_only': True, 'deployment_workflows': [], **override})

    with pytest.raises(contracts_module.ContractError, match=re.escape(expected)):
        contracts_module.load_contracts(_registry_variant(tmp_path, mutate))


@pytest.mark.parametrize(
    'name,excluded_modules',
    [
        ('parakeet', {'utils.logging_config', 'utils.speakers.policy'}),
        ('diarizer', {'omi_logging', 'utils.logging_config', 'utils.stt.diarization_turns'}),
        ('nllb-translation', {'omi_logging'}),
    ],
)
def test_copied_gpu_shims_do_not_probe_checkout_only_imports(contracts_module, name, excluded_modules):
    contract = _contract(contracts_module, name)
    assert excluded_modules <= contract.dependency_probe_exclusions
    dependencies = contracts_module.third_party_dependency_modules(contract)
    assert not any(
        module == shim or module.startswith(shim + '.') for module in dependencies for shim in excluded_modules
    )


def test_gpu_batch_retry_cap_does_not_reach_cloud_tasks(contracts_module):
    contract = _contract(contracts_module, 'batch-pipeline-worker')
    # The image also hosts the separate CPU seal-sweeper CronJob. Preserve this
    # process boundary on the GPU entrypoint rather than unioning both hosts.
    gpu_contract = replace(contract, entrypoints=('diarizer.batch_pipeline_runtime',))
    closure = contracts_module.first_party_import_closure(gpu_contract, gpu_contract.entrypoints)
    assert 'utils.capture.retry_cap' in closure
    assert 'utils.sync.retry_hygiene' not in closure
    assert 'utils.cloud_tasks' not in closure
    assert not any(
        module.startswith('google.cloud.tasks')
        for module in contracts_module.third_party_dependency_modules(gpu_contract)
    )
    sweeper = contracts_module.first_party_import_closure(contract, ('scripts.record_seal_sweep',))
    assert 'utils.batch_pipeline.record_seal_repair' in sweeper
    assert 'diarizer.batch_pipeline_runtime' not in sweeper
    assert 'diarizer.batch_pipeline_models' not in sweeper


def _third_party_contract(contracts_module, tmp_path, *, dockerfile_text, entrypoint_text, files):
    (tmp_path / 'entrypoint.py').write_text(entrypoint_text, encoding='utf-8')
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    dockerfile = tmp_path / 'Dockerfile'
    dockerfile.write_text(dockerfile_text, encoding='utf-8')
    return replace(
        _contract(contracts_module, 'pusher'),
        dockerfile=dockerfile,
        target=None,
        build_context=tmp_path,
        source_root=tmp_path,
        entrypoint_source_root=tmp_path,
        entrypoints=('entrypoint',),
        dependency_probe_exclusions=frozenset(),
    )


_PYLOCK_DOCKERFILE = (
    'FROM python:3.11-slim\n'
    'COPY pylock.worker.toml /app/pylock.worker.toml\n'
    'RUN pip install --no-cache-dir uv==0.11.13 && uv pip sync --system /app/pylock.worker.toml\n'
    'WORKDIR /app\n'
    'COPY entrypoint.py ./\n'
)


def _pylock(*names):
    return 'lock-version = "1.0"\n' + ''.join(f'\n[[packages]]\nname = "{name}"\nversion = "1.0"\n' for name in names)


def test_third_party_closure_rejects_an_import_missing_from_the_image_lock(
    contracts_module, dependencies_module, tmp_path
):
    # The #24490 shape: a reachable `from deepgram import ...` while the worker
    # lock lacks deepgram-sdk. The full backend lock had it, so unit CI passed.
    contract = _third_party_contract(
        contracts_module,
        tmp_path,
        dockerfile_text=_PYLOCK_DOCKERFILE,
        entrypoint_text='import numpy\nfrom deepgram import DeepgramClient\nimport langdetect\n',
        files={'pylock.worker.toml': _pylock('numpy', 'uv')},
    )

    errors, installed = dependencies_module.third_party_closure_errors(contract)

    assert installed.sources[0].endswith('pylock.worker.toml')
    assert installed.open_reasons == ()
    assert len(errors) == 1
    assert 'deepgram, langdetect' in errors[0]
    assert 'numpy' not in errors[0].split('(', 1)[0]


def test_third_party_closure_maps_import_names_to_distributions(contracts_module, dependencies_module, tmp_path):
    contract = _third_party_contract(
        contracts_module,
        tmp_path,
        dockerfile_text=_PYLOCK_DOCKERFILE,
        entrypoint_text=(
            'from deepgram import DeepgramClient\n'
            'import yaml\n'
            'from PIL import Image\n'
            'import google\n'
            'from google.cloud import firestore, tasks_v2\n'
            'from google.cloud.exceptions import NotFound\n'
            'from google.protobuf import json_format\n'
            'from pyannote.audio import Pipeline\n'
            'import audioop\n'
        ),
        files={
            'pylock.worker.toml': _pylock(
                'Deepgram_SDK',
                'PyYAML',
                'pillow',
                'google-cloud-firestore',
                'google-cloud-tasks',
                'google-cloud-core',
                'protobuf',
                'pyannote.audio',
            )
        },
    )

    errors, _ = dependencies_module.third_party_closure_errors(contract)

    assert errors == []


def test_third_party_closure_fails_closed_on_an_unmapped_namespace_submodule(contracts_module, dependencies_module):
    assert dependencies_module.module_distribution_candidates('google') is None
    assert dependencies_module.module_distribution_candidates('google.cloud') is None
    # A submodule under a bare namespace must name a real distribution, never
    # fall back to the namespace and pass.
    candidates = dependencies_module.module_distribution_candidates('google.cloud.unmapped_v1.Thing')
    assert candidates is not None
    assert 'google-cloud-unmapped' in candidates
    assert all(candidate != 'google' for candidate in candidates)


def test_third_party_closure_does_not_judge_an_open_dependency_set(contracts_module, dependencies_module, tmp_path):
    # A range-pinned requirements file does not list transitive distributions,
    # so an absent name may still be installed: report it, never fail on it.
    contract = _third_party_contract(
        contracts_module,
        tmp_path,
        dockerfile_text=(
            'FROM python:3.11-slim\n'
            'WORKDIR /app\n'
            'COPY requirements.txt .\n'
            'RUN pip3 install --no-cache-dir -r requirements.txt\n'
            'COPY entrypoint.py .\n'
        ),
        entrypoint_text='import starlette\n',
        files={'requirements.txt': 'fastapi>=0.100.0\n'},
    )

    errors, installed = dependencies_module.third_party_closure_errors(contract)

    assert errors == []
    assert installed.open_reasons and 'unpinned fastapi>=0.100.0' in installed.open_reasons[0]


def test_third_party_closure_follows_requirement_includes_through_directory_copies(
    contracts_module, dependencies_module, tmp_path
):
    contract = _third_party_contract(
        contracts_module,
        tmp_path,
        dockerfile_text=(
            'FROM python:3.11-slim AS builder\n'
            'ENV PATH="/opt/venv/bin:$PATH"\n'
            'RUN python -m venv /opt/venv\n'
            'COPY reqs/ /tmp/reqs/\n'
            'RUN pip install --no-cache-dir -r /tmp/reqs/job/requirements.txt\n'
            'FROM python:3.11-slim\n'
            'COPY --from=builder /opt/venv /opt/venv\n'
            'WORKDIR /app\n'
            'COPY entrypoint.py .\n'
        ),
        entrypoint_text='import requests\nimport jwt\n',
        files={
            'reqs/requirements.txt': (
                '# This file is autogenerated by pip-compile with Python 3.11\n'
                'requests==2.33.0\n# comment\nPyJWT==2.10.1 ; python_version >= "3.9"\n'
                'pywin32==306 ; sys_platform == "win32"\n'
            ),
            'reqs/job/requirements.txt': '-r ../requirements.txt\n',
        },
    )

    errors, installed = dependencies_module.third_party_closure_errors(contract)

    assert installed.open_reasons == ()
    assert installed.distributions == {'requests', 'pyjwt'}
    assert errors == []


def test_third_party_closure_leaves_a_hand_pinned_list_open(contracts_module, dependencies_module, tmp_path):
    # Every line pinned with == still omits whatever its packages pull in.
    contract = _third_party_contract(
        contracts_module,
        tmp_path,
        dockerfile_text=(
            'FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\n'
            'RUN pip install -r requirements.txt\nCOPY entrypoint.py .\n'
        ),
        entrypoint_text='import starlette\n',
        files={'requirements.txt': 'fastapi==0.121.0\n'},
    )

    errors, installed = dependencies_module.third_party_closure_errors(contract)

    assert errors == []
    assert any('pinned by hand' in reason for reason in installed.open_reasons)


def test_third_party_closure_ignores_a_stage_copied_only_for_a_binary(contracts_module, dependencies_module, tmp_path):
    contract = _third_party_contract(
        contracts_module,
        tmp_path,
        dockerfile_text=(
            'FROM python:3.11-slim AS tools\n'
            'COPY pylock.tools.toml /tmp/pylock.tools.toml\n'
            'RUN uv pip sync /tmp/pylock.tools.toml --python /opt/venv/bin/python\n'
            'FROM python:3.11-slim\n'
            'COPY --from=tools /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg\n'
            'COPY pylock.worker.toml /app/pylock.worker.toml\n'
            'RUN uv pip sync --system /app/pylock.worker.toml\n'
            'WORKDIR /app\nCOPY entrypoint.py ./\n'
        ),
        entrypoint_text='import deepgram\n',
        files={'pylock.tools.toml': _pylock('deepgram-sdk'), 'pylock.worker.toml': _pylock('numpy')},
    )

    errors, installed = dependencies_module.third_party_closure_errors(contract)

    assert 'deepgram-sdk' not in installed.distributions
    assert len(errors) == 1 and 'deepgram' in errors[0]


def test_third_party_closure_credits_a_copied_builder_environment(contracts_module, dependencies_module, tmp_path):
    contract = _third_party_contract(
        contracts_module,
        tmp_path,
        dockerfile_text=(
            'FROM python:3.11-slim AS builder\n'
            'COPY pylock.worker.toml /tmp/pylock.worker.toml\n'
            'RUN uv pip sync /tmp/pylock.worker.toml --python /opt/venv/bin/python --compile-bytecode\n'
            'FROM python:3.11-slim\n'
            'COPY --from=builder /opt/venv /opt/venv\n'
            'WORKDIR /app\nCOPY entrypoint.py ./\n'
        ),
        entrypoint_text='from deepgram import DeepgramClient\n',
        files={'pylock.worker.toml': _pylock('deepgram-sdk')},
    )

    assert dependencies_module.third_party_closure_errors(contract)[0] == []


def test_third_party_closure_explicit_mapping_is_authoritative(contracts_module, dependencies_module):
    # An unrelated distribution named like a longer import path must not
    # satisfy a module whose owner is mapped explicitly or by its top level.
    assert dependencies_module.module_distribution_candidates('deepgram.clients.listen') == ('deepgram-sdk',)
    assert dependencies_module.module_distribution_candidates('fastapi.FastAPI') == ('fastapi',)
    assert dependencies_module.module_distribution_candidates('google.protobuf.json_format') == ('protobuf',)
    # API-version suffixes are dropped only under namespace packages.
    assert dependencies_module.module_distribution_candidates('mylib_v2.thing') == ('mylib-v2',)
    assert 'google-cloud-tasks' in dependencies_module.module_distribution_candidates('google.cloud.tasks_v2')


def test_third_party_closure_excludes_lock_entries_whose_marker_misses_the_image(contracts_module, dependencies_module):
    applies = dependencies_module.marker_applies_to_image
    assert applies("platform_machine == 'x86_64' and sys_platform == 'linux'")
    assert applies("python_full_version < '3.13' and platform_machine == 'x86_64'")
    assert applies("implementation_name != 'pypy'")
    assert not applies("sys_platform == 'darwin'")
    assert not applies("python_full_version >= '3.12'")
    assert not applies("extra == 'gpu'")  # undecidable here: never credited


def test_registered_image_dependency_sets_are_classified(contracts_module, dependencies_module):
    # The full closure walk runs in the backend-runtime-image-third-party-closure
    # manifest check; this pins which registered images it judges.
    closed = {
        contract.name
        for contract in contracts_module.load_contracts()
        if not dependencies_module.installed_dependencies(contract).open_reasons
    }
    assert {'batch-pipeline-worker', 'backend', 'backend-api', 'backend-pusher', 'pusher'} <= closed
    assert 'parakeet' not in closed and 'plugins' not in closed


def test_third_party_closure_credits_only_installs_into_the_copied_environment(
    contracts_module, dependencies_module, tmp_path
):
    # The backend builder installs uv into the system interpreter before it
    # activates /opt/venv; only the venv is copied into the image.
    contract = _third_party_contract(
        contracts_module,
        tmp_path,
        dockerfile_text=(
            'FROM python:3.11-slim AS builder\n'
            'RUN python -m venv /opt/venv\n'
            'RUN python3 -m pip install --no-cache-dir "uv==0.11.13"\n'
            'ENV PATH="/opt/venv/bin:$PATH"\n'
            'COPY pylock.worker.toml /tmp/pylock.worker.toml\n'
            'RUN pip install --no-cache-dir "langdetect==1.0.9"\n'
            'FROM python:3.11-slim\n'
            'COPY --from=builder /opt/venv /opt/venv\n'
            'WORKDIR /app\nCOPY entrypoint.py ./\n'
        ),
        entrypoint_text='import langdetect\n',
        files={'pylock.worker.toml': _pylock('numpy')},
    )

    installed = dependencies_module.installed_dependencies(contract)

    assert 'uv' not in installed.distributions
    assert 'langdetect' in installed.distributions


def test_third_party_closure_namespace_matches_only_the_provider_component(dependencies_module):
    candidates = dependencies_module.module_distribution_candidates('google.cloud.tasks_v2.jobs_v1.client.Client')
    assert candidates == ('google-cloud-tasks-v2', 'google-cloud-tasks')
    assert dependencies_module.module_distribution_candidates('google.auth.transport.requests') == ('google-auth',)


def test_third_party_closure_leaves_patch_sensitive_python_markers_undecided(dependencies_module):
    applies = dependencies_module.marker_applies_to_image
    assert applies("python_full_version >= '3.11'")
    assert applies("python_full_version >= '3.10.2'")
    assert not applies("python_full_version >= '3.11.15'")  # depends on the floating patch
    assert not applies("python_full_version < '3.11.4'")
    assert not applies("python_full_version == '3.11'")  # true only for 3.11.0
    assert not applies("python_full_version <= '3.11.99'")
    assert applies("python_full_version != '3.10.4'")
