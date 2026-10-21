"""Regression gates for launch-surface discovery and logging adoption."""

import json
from pathlib import PurePosixPath

import pytest

from scripts import check_logging_entrypoints as guard


@pytest.mark.parametrize(
    'argv,expected',
    [
        (['uvicorn', 'main:app'], 'main'),
        (['python3', '-m', 'uvicorn', 'main:app'], 'main'),
        (['python', '-m', 'utils.messaging.maintenance'], 'utils.messaging.maintenance'),
        (['python', '/app/job.py'], '/app/job.py'),
        (['sh', '-c', 'python job.py'], 'job.py'),
    ],
)
def test_launch_forms(argv, expected):
    assert guard.launch_target(argv) == expected


def test_unknown_launcher_fails_closed():
    with pytest.raises(ValueError):
        guard.launch_target(['custom-launcher', 'main'])


def test_dead_setup_does_not_satisfy_adoption():
    assert guard.source_violations('from omi_logging import configure_logging\ndef unused():\n configure_logging("x")')
    assert guard.source_violations('from other import configure_logging\nconfigure_logging("x")')


def test_aliases_and_uvicorn_reconfiguration_are_checked():
    source = '''from omi_logging import configure_logging as setup
import logging as log
from builtins import print as output
from uvicorn import run as serve
setup('x')
log.basicConfig()
output('oops')
serve('main:app')
'''
    assert guard.source_violations(source) == {'basicConfig': 1, 'print': 1, 'uvicorn_reconfigures': 1}
    assert guard.source_violations("import omi_logging as logs\nlogs.configure_logging('x')") == {}


def test_copied_source_and_entrypoint_resolve_actual_runtime_layout(tmp_path):
    app = tmp_path / 'source'
    app.mkdir()
    (app / 'main.py').write_text('')
    docker = tmp_path / 'Dockerfile'
    docker.write_text('FROM python\nWORKDIR /app\nCOPY source/ .\nENTRYPOINT ["python"]\nCMD ["main.py"]\n')
    workdir, target = guard.docker_launch(docker)
    assert guard.source_path(docker, tmp_path, workdir, target) == app / 'main.py'
    with pytest.raises(ValueError):
        guard.source_path(docker, tmp_path, workdir, 'not_copied')
    assert guard.copied_source(docker, tmp_path, workdir, PurePosixPath('/app/omi_logging.py')) is None


def test_pending_only_shrinks_and_cannot_hide_new_launchers():
    pending = {'old.py': {'missing_setup': 1}}
    assert not guard.check_pending(pending, pending, pending)
    assert guard.check_pending({'new.py': {'missing_setup': 1}}, pending, pending)
    assert guard.check_pending({}, {'new.py': {'missing_setup': 1}}, pending)
    assert guard.check_pending({'old.py': {}}, pending, pending)
    assert not guard.check_pending({'old.py': {}}, {}, pending)


def test_real_fleet_inventory_matches_pending_and_includes_non_docker_overrides():
    actual = guard.inventory()
    pending = json.loads((guard.ROOT / guard.PENDING).read_text())
    assert not guard.check_pending(actual, pending)
    for path in (
        'backend/diarizer/batch_main.py',
        'backend/llm_gateway/main.py',
        'backend/utils/messaging/maintenance.py',
        'backend/scripts/finops/cloudrun_entry.py',
    ):
        assert any(key.split('::')[0] == path for key in actual)


def test_helm_inline_block_and_shell_overrides():
    assert list(guard.helm_targets('command: [uvicorn]\nargs: ["llm_gateway.main:app", --port, "8080"]')) == [
        'llm_gateway.main'
    ]
    assert list(guard.helm_targets('command:\n  - python\n  - -m\n  - utils.messaging.maintenance\nenv: []')) == [
        'utils.messaging.maintenance'
    ]
    assert list(guard.helm_targets('command: [sh, -c, "exec python new_job.py"]')) == ['new_job.py']


def test_shell_absolute_paths_and_multiple_commands():
    source = 'command: [sh, -c, "exec /opt/venv/bin/python first.py; /opt/venv/bin/uvicorn other:app"]'
    assert list(guard.helm_targets(source)) == ['first.py', 'other']


def test_app_dir_cannot_redirect_inspected_module():
    with pytest.raises(ValueError, match='app-dir'):
        guard.launch_target(['uvicorn', 'main:app', '--app-dir', '/app/other'])


def test_nested_import_alias_and_local_shadowing():
    assert (
        guard.source_violations('if __name__ == "__main__":\n from uvicorn import run\n run("main:app")')[
            'uvicorn_reconfigures'
        ]
        == 1
    )
    assert 'print' not in guard.source_violations('def function(print):\n print("not builtin")')


def test_invalid_base_cannot_disable_ratchet():
    import subprocess

    with pytest.raises(subprocess.CalledProcessError):
        guard.previous_pending('this-ref-does-not-exist-logging-test')


@pytest.mark.parametrize('suffix', ['yaml', 'yml'])
@pytest.mark.parametrize('copy_worker', [False, True])
def test_helm_module_and_logging_must_exist_in_bound_image(tmp_path, monkeypatch, copy_worker, suffix):
    from types import SimpleNamespace

    root = tmp_path
    source = root / 'backend/service'
    source.mkdir(parents=True)
    (source / 'main.py').write_text('')
    (source / 'worker.py').write_text("from omi_logging import configure_logging\nconfigure_logging('worker')")
    docker = source / 'Dockerfile'
    docker.write_text(
        'FROM python\nWORKDIR /app\nCOPY backend/service/main.py ./main.py\n'
        + ('COPY backend/service/worker.py ./worker.py\n' if copy_worker else '')
        + 'CMD ["uvicorn", "main:app"]\n'
    )
    chart = root / 'backend/charts/worker'
    chart.mkdir(parents=True)
    (chart / f'deployment.{suffix}').write_text('command: [python, worker.py]')
    (root / 'backend/runtime_images.json').write_text(json.dumps({'logging_chart_images': {'worker': 'test'}}))
    contract = SimpleNamespace(
        name='test', source_root=source, dockerfile=docker, build_context=root, entrypoints=('main',)
    )
    monkeypatch.setattr(guard, 'load_contracts', lambda: [contract])
    monkeypatch.setattr(guard, 'ROOT', root)
    with pytest.raises(ValueError, match='missing or shadowed' if copy_worker else 'not copied'):
        guard.inventory(root)


def test_inline_python_is_only_exempt_in_probe_or_init_scope():
    with pytest.raises(ValueError):
        list(guard.helm_targets('command: [python, -c, "import new_app"]'))
    assert list(guard.helm_targets('initContainers:\n  - name: probe\n    command: [python, -c, "print(1)"]')) == []


def test_compound_docker_shell_is_rejected():
    with pytest.raises(ValueError, match='compound'):
        guard.launch_target(['sh', '-c', 'python first.py; python second.py'])


@pytest.mark.parametrize('command', ['[/app/start.sh]', '[gunicorn, "worker:app"]', '[sh, -c, "/app/start.sh"]'])
def test_unknown_helm_application_launcher_is_rejected(command):
    with pytest.raises(ValueError, match='unsupported Helm'):
        list(guard.helm_targets('command: ' + command))


def test_command_first_container_mapping():
    assert list(guard.helm_targets('containers:\n  - command: [python, worker.py]\n    name: worker')) == ['worker.py']


def test_class_attributes_do_not_shadow_module_or_method_globals():
    source = 'from uvicorn import run\nclass Worker:\n def run(self):\n  run("main:app")\nrun("main:app")'
    assert guard.source_violations(source)['uvicorn_reconfigures'] == 2


def test_copy_uses_workdir_at_instruction(tmp_path):
    source = tmp_path / 'backend'
    (source / 'diarizer').mkdir(parents=True)
    (source / 'main.py').write_text('wrong')
    (source / 'diarizer/main.py').write_text('actual')
    docker = tmp_path / 'Dockerfile'
    docker.write_text('FROM python\nWORKDIR /app\nCOPY backend/ .\nWORKDIR /app/diarizer\nCMD ["python", "main.py"]')
    workdir, target = guard.docker_launch(docker)
    assert guard.source_path(docker, tmp_path, workdir, target) == source / 'diarizer/main.py'


def test_stage_copy_cannot_hide_overwritten_shared_module(tmp_path):
    (tmp_path / 'omi_logging.py').write_text('')
    docker = tmp_path / 'Dockerfile'
    docker.write_text(
        'FROM python\nWORKDIR /app\nCOPY omi_logging.py ./omi_logging.py\nCOPY --from=builder /other.py /app/omi_logging.py'
    )
    with pytest.raises(ValueError, match='overwrite'):
        guard.copied_source(docker, tmp_path, PurePosixPath('/app'), PurePosixPath('/app/omi_logging.py'))


def test_docker_shell_form_and_multiline_are_rejected(tmp_path):
    docker = tmp_path / 'Dockerfile'
    docker.write_text('FROM python\nCMD python first.py && python second.py')
    with pytest.raises(ValueError, match='shell-form'):
        guard.docker_launch(docker)
    with pytest.raises(ValueError, match='compound'):
        guard.launch_target(['sh', '-c', 'python first.py\npython second.py'])


def test_mixed_helm_shell_rejects_unknown_application():
    with pytest.raises(ValueError, match='unsupported Helm'):
        list(guard.helm_targets('command: [sh, -c, "uvicorn main:app & /app/start.sh"]'))


def test_directory_copy_merges_contents(tmp_path):
    for name in ('first', 'second'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'main.py').write_text(name)
    docker = tmp_path / 'Dockerfile'
    docker.write_text('FROM python\nWORKDIR /app\nCOPY first/ second/ /app/\nCMD ["python", "main.py"]')
    workdir, target = guard.docker_launch(docker)
    assert guard.source_path(docker, tmp_path, workdir, target) == tmp_path / 'second/main.py'


def test_attribute_assignment_does_not_rebind_logging_module():
    source = 'import logging\nlogging.raiseExceptions = False\nlogging.basicConfig(force=True)'
    assert guard.source_violations(source)['basicConfig'] == 1


@pytest.mark.parametrize('separator', [';\n', '&&\n'])
def test_adjacent_shell_separators_cannot_hide_unknown_command(separator):
    command = json.dumps(['sh', '-c', 'python first.py' + separator + '/app/start.sh'])
    with pytest.raises(ValueError, match='unsupported Helm'):
        list(guard.helm_targets('command: ' + command))


@pytest.mark.parametrize(
    'source',
    [
        'args: [python3, worker.py]',
        'command: {{ .Values.command | toJson }}\nargs: ["--app-dir", "/app/other"]',
        'args: [worker.py]\ncommand: [python3]',
        'command: [python3]\nimage: example\nargs: [worker.py]',
        'containers:\n  - name: worker\n    args: [python3, worker.py]',
    ],
)
def test_unresolved_helm_args_override_fails_closed(source):
    with pytest.raises(ValueError):
        list(guard.helm_targets(source))


def test_new_binding_cannot_inherit_pending_source_exception(tmp_path, monkeypatch):
    from types import SimpleNamespace

    source = tmp_path / 'backend/service'
    source.mkdir(parents=True)
    (source / 'main.py').write_text('')
    docker = source / 'Dockerfile'
    docker.write_text('FROM python\nWORKDIR /app\nCOPY backend/service/main.py ./main.py\nCMD ["python", "main.py"]')
    (tmp_path / 'backend/charts').mkdir()
    (tmp_path / 'backend/runtime_images.json').write_text(json.dumps({'logging_chart_images': {}}))
    contract = SimpleNamespace(
        name='test', source_root=source, dockerfile=docker, build_context=tmp_path, entrypoints=('main',)
    )
    monkeypatch.setattr(guard, 'load_contracts', lambda: [contract])
    monkeypatch.setattr(guard, 'ROOT', tmp_path)
    pending = guard.inventory(tmp_path)
    (source / 'Dockerfile.new').write_text(docker.read_text())
    actual = guard.inventory(tmp_path)
    assert len(actual) == len(pending) + 1
    assert guard.check_pending(actual, pending, pending)
    assert guard.check_pending(actual, actual, pending)


def _multi_target_service(tmp_path, monkeypatch, *, build_only):
    from types import SimpleNamespace

    source = tmp_path / 'backend/service'
    source.mkdir(parents=True)
    (source / 'main.py').write_text('')
    (source / 'worker.py').write_text('')
    docker = source / 'Dockerfile.roles'
    docker.write_text(
        'FROM python AS app\nWORKDIR /app\nCOPY backend/service/ .\n'
        'FROM app AS api\nCMD ["uvicorn", "main:app"]\n'
        'FROM app AS worker\nCMD ["python", "-m", "worker"]\n'
    )
    (tmp_path / 'backend/charts').mkdir()
    (tmp_path / 'backend/runtime_images.json').write_text(json.dumps({'logging_chart_images': {}}))
    contracts = [
        SimpleNamespace(
            name=f'service-{stage}',
            source_root=source,
            dockerfile=docker,
            build_context=tmp_path,
            entrypoints=(module,),
            target=stage,
            build_only=build_only,
        )
        for stage, module in (('api', 'main'), ('worker', 'worker'))
    ]
    monkeypatch.setattr(guard, 'load_contracts', lambda: contracts)
    monkeypatch.setattr(guard, 'ROOT', tmp_path)
    return guard.inventory(tmp_path)


def test_each_registered_build_target_is_its_own_launch_surface(tmp_path, monkeypatch):
    actual = _multi_target_service(tmp_path, monkeypatch, build_only=False)
    assert set(actual) == {
        'backend/service/main.py::docker:backend/service/Dockerfile.roles@api:main',
        'backend/service/worker.py::docker:backend/service/Dockerfile.roles@worker:worker',
    }
    assert guard.check_pending(actual, {}, {})


def test_build_only_targets_have_no_launch_surface_until_deployed(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'dockerfile_shipped_by_github', lambda _: [])
    assert _multi_target_service(tmp_path, monkeypatch, build_only=True) == {}


def test_build_only_flag_cannot_hide_a_dockerfile_a_workflow_ships(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'dockerfile_shipped_by_github', lambda _: ['.github/workflows/ships.yml'])
    assert len(_multi_target_service(tmp_path, monkeypatch, build_only=True)) == 2
