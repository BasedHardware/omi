"""The opt-in simulator target stays inside the hermetic test tree."""

import argparse
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from testing.lifecycle_sim import pytest_entry, run
from tests.support.lifecycle_state_table import ORDERING_RULES, durable_titling_rearm, ordering_holds

EXTRA = 'testing/lifecycle_properties/test_properties.py'


@pytest.mark.parametrize('extra', [False, True])
def test_pytest_collection_keeps_default_and_explicit_extra_target(monkeypatch, tmp_path, extra):
    monkeypatch.setenv('LIFECYCLE_SIM_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(pytest_entry, 'preflight', Mock())
    collect = Mock(return_value=0)
    monkeypatch.setattr(pytest_entry.pytest, 'main', collect)
    arguments = ['--extra-test-module', EXTRA] if extra else []
    assert pytest_entry.main(arguments) == 0
    command = collect.call_args.args[0]
    targets = [arg for arg in command if arg.endswith('.py')]
    original = str(Path(pytest_entry.__file__).with_name('test_scenarios.py'))
    assert targets == [original] + ([pytest_entry.extra_test_module_path(EXTRA)] if extra else [])


@pytest.mark.parametrize(
    'target', ['../outside.py', 'tests/unit/test_lifecycle_invariants.py', 'testing/lifecycle_sim', 'testing/absent.py']
)
def test_extra_target_refuses_outside_missing_and_non_module_paths(target):
    with pytest.raises(argparse.ArgumentTypeError):
        pytest_entry.extra_test_module_path(target)


def test_parent_forwards_explicit_extra_without_changing_hermetic_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(run, 'preflight', Mock())
    value = Mock(env={'isolated': 'fixture'})
    monkeypatch.setattr(run, 'Stack', Mock(return_value=value))
    child = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(run.subprocess, 'run', child)
    arguments = SimpleNamespace(runxfail=False, extra_test_module=[EXTRA])
    assert run.run_scenarios(tmp_path, arguments) == 0
    command = child.call_args.args[0]
    assert command[-2:] == ['--extra-test-module', EXTRA]
    environment = child.call_args.kwargs['env']
    assert environment['isolated'] == 'fixture'
    assert environment['LIFECYCLE_SIM_STATE_DIR'] == str(tmp_path)
    assert environment['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
    value.close.assert_called_once_with()


@pytest.mark.parametrize('source', ['backend/utils/fair_use.py', 'backend/database/fair_use.py'])
def test_fair_use_changes_select_generated_ladder_properties(source):
    backend = Path(__file__).resolve().parents[2]
    selector = runpy.run_path(str(backend / 'scripts/select_backend_unit_tests.py'))
    selected, _ = selector['tests_for_changed_paths']([source], selector['discover_all_tests']())
    assert 'tests/unit/test_lifecycle_ladder_properties.py' in selected


def test_existing_gauntlet_explicitly_collects_property_module():
    backend = Path(__file__).resolve().parents[2]
    command = (backend / 'testing/listen_pusher_stack/run.sh').read_text()
    assert command.count('--extra-test-module ' + EXTRA) == 1


def test_late_result_contract_rejects_a_pending_outbox_without_an_increment():
    before = {'version': 7, 'task_token': 'synthetic-wake', 'due_at': 123.0}
    row = {'record_lane_owner': 'batch_live_v1', 'finalization_status': 'completed'}
    assert not ordering_holds(
        ORDERING_RULES[0],
        row,
        completed_before_results=True,
        batch_result_count=1,
        rearm_on_result_commit=durable_titling_rearm(before, dict(before)),
    )
    assert ordering_holds(
        ORDERING_RULES[0],
        row,
        completed_before_results=True,
        batch_result_count=1,
        rearm_on_result_commit=durable_titling_rearm(before, {**before, 'version': 8}),
    )
