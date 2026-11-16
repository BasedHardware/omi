from pathlib import Path
import subprocess
import sys
import runpy

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SELECTOR = BACKEND_DIR / 'scripts' / 'select_backend_unit_tests.py'
SELECTED_TEST = 'tests/unit/test_workflow_contracts.py'


def test_selector_artifacts_use_lf_on_every_platform(tmp_path: Path) -> None:
    input_list = tmp_path / 'input.txt'
    selected_list = tmp_path / 'selected.txt'
    reason_file = tmp_path / 'reason.txt'
    input_list.write_bytes(f'{SELECTED_TEST}\r\n'.encode('utf-8'))

    subprocess.run(
        [
            sys.executable,
            str(SELECTOR),
            '--from-test-list',
            str(input_list),
            '--output',
            str(selected_list),
            '--reason-output',
            str(reason_file),
        ],
        cwd=BACKEND_DIR,
        check=True,
    )

    assert selected_list.read_bytes() == f'{SELECTED_TEST}\n'.encode('utf-8')
    assert reason_file.read_bytes() == b'using provided backend unit test list\n'


@pytest.mark.parametrize(
    'source',
    [
        'backend/charts/backend-listen/templates/deployment.yaml',
        'backend/charts/pusher/templates/deployment.yaml',
        'backend/charts/monitoring/kube-prometheus-stack/prod_omi_monitoring_values.yaml',
    ],
)
def test_monitoring_changes_select_firestore_attribution_charts(tmp_path, source):
    changed = tmp_path / 'changed.txt'
    changed.write_text(source + '\n')
    result = subprocess.run(
        [sys.executable, str(SELECTOR), '--changed-files', str(changed)],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    assert 'tests/unit/test_firestore_attribution_charts.py' in result.stdout.splitlines()


@pytest.fixture(scope='module')
def selector():
    loaded = runpy.run_path(str(SELECTOR))
    loaded['all_tests'] = loaded['discover_all_tests']()
    return loaded


@pytest.mark.parametrize(
    'source',
    [
        'backend/scripts/jobstore_operator/readiness_probe.py',
        'backend/scripts/jobstore_operator/readiness_contract.py',
        'backend/scripts/jobstore_operator/artifact-contract.json',
        'backend/scripts/jobstore_operator/tests/test_readiness_probe.py',
        'backend/scripts/jobstore_operator/tests/fixtures/pod-api-response.json',
    ],
)
def test_operator_changes_select_portable_files_and_retain_generic_guards(selector, source):
    portable = {
        path.relative_to(BACKEND_DIR).as_posix()
        for path in (BACKEND_DIR / 'scripts/jobstore_operator/tests').glob('test_*.py')
    }
    assert 'scripts/jobstore_operator/tests/test_readiness_probe.py' in portable
    assert portable <= set(selector['discover_unit_tests']())
    selected, reason = selector['tests_for_changed_paths']([source], selector['all_tests'])
    assert portable <= set(selected)
    assert len(selected) < 40
    assert 'full backend unit suite' not in reason
    assert 'did not match' not in reason
    assert portable <= set(selector['focused_tests_for_changed_paths']([source], selector['all_tests']))
    if source.endswith('.py'):
        assert 'tests/unit/test_lifecycle_state_table_writers.py' in selected
        assert 'tests/unit/test_reason_label_enums.py' in selected


def test_operator_fixture_cli_selection_matches_portable_discovery(tmp_path):
    changed = tmp_path / 'changed.txt'
    changed.write_text('backend/scripts/jobstore_operator/tests/fixtures/pod-api-response.json\n')
    output = subprocess.run(
        [sys.executable, str(SELECTOR), '--changed-files', str(changed)],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    portable = {
        path.relative_to(BACKEND_DIR).as_posix()
        for path in (BACKEND_DIR / 'scripts/jobstore_operator/tests').glob('test_*.py')
    }
    assert set(output.stdout.splitlines()) == portable


@pytest.mark.parametrize(
    'source',
    [
        'backend/scripts/integration_canary_controller.py',
        'backend/scripts/integration_canary_metrics.py',
        'backend/scripts/runtime_env_canary_ops.py',
        'backend/scripts/runtime_env_validation/manifest.py',
    ],
)
def test_controller_sources_have_focused_contracts(selector, source):
    all_tests = selector['all_tests']
    selected, reason = selector['tests_for_changed_paths']([source], all_tests)
    assert len(selected) < 40
    assert 'requires the full' not in reason
    assert 'did not match' not in reason
    assert 'tests/unit/test_integration_canary_controller.py' in selected
    assert 'tests/unit/test_integration_canary_workflow.py' in selected
    assert 'tests/unit/test_integration_canary_imports.py' in selected


@pytest.mark.parametrize(
    'broad_source',
    ['backend/scripts/select_backend_unit_tests.py', 'backend/unknown_controller.py', 'backend/tests/unit/conftest.py'],
)
def test_broad_selection_keeps_known_contracts_and_changed_tests(selector, broad_source):
    all_tests = selector['all_tests']
    paths = [broad_source, 'backend/scripts/runtime_env_canary_ops.py', 'backend/' + SELECTED_TEST]
    selected, _ = selector['tests_for_changed_paths'](paths, all_tests)
    assert selected == all_tests  # CI must still retain its broad fallback.
    focused = selector['focused_tests_for_changed_paths'](paths, all_tests)
    assert 'tests/unit/test_integration_canary_workflow.py' in focused
    assert SELECTED_TEST in focused
    assert focused[-1] == SELECTED_TEST  # affected contracts precede changed tests
    assert len(focused) == len(set(focused)) < 40
    assert not any(path.endswith('conftest.py') for path in focused)


def test_focused_cli_emits_lf_and_does_not_weaken_broad_selection(tmp_path):
    changed = tmp_path / 'changed.txt'
    changed.write_text('backend/unknown_controller.py\nbackend/scripts/runtime_env_canary_ops.py\n')
    broad, focused = tmp_path / 'broad.txt', tmp_path / 'focused.txt'
    subprocess.run(
        [
            sys.executable,
            str(SELECTOR),
            '--changed-files',
            str(changed),
            '--output',
            str(broad),
            '--focused-output',
            str(focused),
        ],
        cwd=BACKEND_DIR,
        check=True,
    )
    assert len(broad.read_text().splitlines()) > 40
    assert 'tests/unit/test_integration_canary_workflow.py' in focused.read_text().splitlines()
    assert b'\r' not in focused.read_bytes()


def test_focused_unknown_or_empty_inputs_do_not_expand_to_full_suite(selector):
    all_tests = selector['all_tests']
    assert selector['focused_tests_for_changed_paths']([], all_tests) == []
    for paths in (['backend/unknown_controller.py'], ['backend/tests/unit/removed_test.py']):
        focused = selector['focused_tests_for_changed_paths'](paths, all_tests)
        assert len(focused) < 40
        assert 'tests/unit/removed_test.py' not in focused
        # Existing cross-cutting guards still apply to otherwise unknown Python.
        assert 'tests/unit/test_lifecycle_state_table_writers.py' in focused


@pytest.mark.parametrize(
    'source',
    [
        'backend/deploy/compose_runtime_env.py',
        'backend/deploy/runtime_env/prod.overlay.yaml',
        'backend/scripts/render_backend_runtime_env.py',
        'backend/scripts/render_gke_backend_config.py',
    ],
)
def test_runtime_composition_selects_render_and_binding_contracts(selector, source):
    selected, _ = selector['tests_for_changed_paths']([source], selector['all_tests'])
    assert len(selected) < 40
    assert 'tests/unit/test_cross_service_deploy_contract.py' in selected
    assert 'tests/unit/test_render_backend_runtime_env.py' in selected
    assert 'tests/unit/test_render_gke_backend_config.py' in selected
