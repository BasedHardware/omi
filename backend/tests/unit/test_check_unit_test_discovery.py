"""Regression tests for scripts/check_unit_test_discovery.py.

Guards the guard: a test file that no runner discovers must fail the check
(this exact failure shipped once — a runner rewrite silently dropped two test
files from CI), workflow coverage claims must describe real workflows, and
the allowlists must only ever shrink. Enforcement against the live tree is
the manifest check `backend-test-discovery`; these tests cover the pure
functions.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from scripts.check_unit_test_discovery import (
    LEGACY_UNLISTED_BASELINE,
    MANUAL_ONLY_TESTS,
    _runs_reference,
    check_legacy_ratchet,
    find_orphans,
    workflow_map_errors,
)

FAKE_WORKFLOWS = {
    'backend-hermetic-e2e.yml': 'run: bash backend/testing/e2e/run.sh',
    'desktop-backend-contracts.yml': 'run: python -m pytest backend/testing/contracts -v',
    'parakeet_gpu_tests.yml': ('python -m pytest tests/container/test_parakeet_smoke.py -v\n'),
}


def test_orphan_outside_all_runners_is_reported():
    all_files = {'tests/unit/test_known.py', 'tests/newarea/test_orphan.py'}
    selected = {'tests/unit/test_known.py'}
    assert find_orphans(all_files, selected, set(), FAKE_WORKFLOWS) == ['tests/newarea/test_orphan.py']


def test_explicit_mode_requires_each_file_to_be_named_in_the_workflow():
    all_files = {
        'tests/container/test_parakeet_smoke.py',  # named in the workflow
        'tests/container/test_parakeet_unwired.py',  # not named -> orphan
    }
    assert find_orphans(all_files, set(), set(), FAKE_WORKFLOWS) == ['tests/container/test_parakeet_unwired.py']


def test_directory_mode_covers_whole_tree():
    all_files = {'testing/e2e/test_new_flow.py', 'testing/contracts/test_new_contract.py'}
    assert find_orphans(all_files, set(), set(), FAKE_WORKFLOWS) == []


def test_policy_excluded_and_allowlisted_files_are_not_orphans():
    all_files = {
        'tests/integration/test_live.py',
        'tests/eval/test_eval.py',
        'tests/test_legacy.py',
    }
    assert find_orphans(all_files, set(), {'tests/test_legacy.py'}, FAKE_WORKFLOWS) == []
    assert MANUAL_ONLY_TESTS == {}  # nothing is currently blessed as manual-only


def test_commented_out_or_deselected_references_are_not_coverage():
    text = (
        '# python -m pytest tests/container/test_parakeet_smoke.py -v\n'
        'python -m pytest tests/container --deselect tests/container/test_parakeet_der_gate.py\n'
        'echo tests/container/test_parakeet_wer_gate.py\n'
    )
    for path in (
        'tests/container/test_parakeet_smoke.py',  # commented out
        'tests/container/test_parakeet_der_gate.py',  # deselected
        'tests/container/test_parakeet_wer_gate.py',  # prose/echo mention
    ):
        assert not _runs_reference(text, path), path
    assert _runs_reference(
        'python -m pytest tests/container/test_parakeet_smoke.py -v', 'tests/container/test_parakeet_smoke.py'
    )


def test_deselecting_one_test_does_not_orphan_a_file_that_still_runs():
    line = (
        'python -m pytest tests/container/test_parakeet_smoke.py -v '
        '--deselect tests/container/test_parakeet_smoke.py::test_flaky'
    )
    assert _runs_reference(line, 'tests/container/test_parakeet_smoke.py')


def test_backslash_continuation_keeps_path_attached_to_its_invocation():
    text = 'python -m pytest \\\n  tests/container/test_parakeet_smoke.py -v \\\n  --tb=short'
    assert _runs_reference(text, 'tests/container/test_parakeet_smoke.py')


def test_missing_workflow_file_is_an_error():
    errors = workflow_map_errors(
        {'backend-hermetic-e2e.yml': '', 'desktop-backend-contracts.yml': 'x', 'parakeet_gpu_tests.yml': 'x'}
    )
    assert any('backend-hermetic-e2e.yml' in e and 'does not exist' in e for e in errors)


def test_directory_workflow_must_reference_its_tree():
    texts = dict(FAKE_WORKFLOWS)
    texts['desktop-backend-contracts.yml'] = 'run: echo no contracts here'
    errors = workflow_map_errors(texts)
    assert any('desktop-backend-contracts.yml' in e and 'testing/contracts' in e for e in errors)


def test_valid_workflow_map_has_no_errors():
    assert workflow_map_errors(FAKE_WORKFLOWS) == []


def test_legacy_ratchet_rejects_growth():
    grown = set(LEGACY_UNLISTED_BASELINE) | {'tests/unit/test_newly_allowlisted.py'}
    errors = check_legacy_ratchet(grown, grown | set(MANUAL_ONLY_TESTS))
    assert len(errors) == 1
    assert 'shrink-only' in errors[0]


def test_legacy_ratchet_requires_baseline_cleanup_on_shrink():
    smaller = set(sorted(LEGACY_UNLISTED_BASELINE)[:1])
    errors = check_legacy_ratchet(smaller, smaller | set(MANUAL_ONLY_TESTS))
    assert len(errors) == 1
    assert 'LEGACY_UNLISTED_BASELINE' in errors[0]


def test_legacy_ratchet_rejects_stale_allowlist_entries():
    errors = check_legacy_ratchet(set(LEGACY_UNLISTED_BASELINE), all_files=set())
    assert any('no longer exist' in e for e in errors)


def test_legacy_ratchet_clean_when_baseline_matches_and_files_exist():
    current = set(LEGACY_UNLISTED_BASELINE)
    assert check_legacy_ratchet(current, current | set(MANUAL_ONLY_TESTS)) == []
