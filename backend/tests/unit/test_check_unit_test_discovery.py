"""Regression tests for scripts/check_unit_test_discovery.py.

Guards the guard: a test file that no runner discovers must fail the check
(this exact failure shipped once — a runner rewrite silently dropped two test
files from CI), and the legacy allowlist must only ever shrink.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from scripts.check_unit_test_discovery import (
    LEGACY_UNLISTED_BASELINE,
    check_legacy_ratchet,
    covered_by_other_runner,
    discover_test_files,
    find_orphans,
)
from scripts.select_backend_unit_tests import LEGACY_UNLISTED_TESTS, discover_unit_tests


def test_orphan_outside_all_runners_is_reported():
    all_files = {'tests/unit/test_known.py', 'tests/newarea/test_orphan.py'}
    selected = {'tests/unit/test_known.py'}
    assert find_orphans(all_files, selected, set()) == ['tests/newarea/test_orphan.py']


def test_selected_and_other_runner_files_are_not_orphans():
    all_files = {
        'tests/unit/test_known.py',
        'testing/e2e/test_flow.py',
        'tests/container/test_gpu.py',
        'tests/integration/test_live.py',
    }
    selected = {'tests/unit/test_known.py'}
    assert find_orphans(all_files, selected, set()) == []


def test_legacy_allowlist_entry_is_not_an_orphan():
    all_files = {'tests/test_legacy.py'}
    assert find_orphans(all_files, set(), {'tests/test_legacy.py'}) == []


def test_other_runner_prefixes_only_match_at_path_start():
    assert covered_by_other_runner('testing/e2e/test_flow.py')
    assert not covered_by_other_runner('tests/unit/testing/e2e_test_helper/test_x.py')


def test_legacy_ratchet_rejects_growth():
    grown = set(LEGACY_UNLISTED_BASELINE) | {'tests/unit/test_newly_allowlisted.py'}
    errors = check_legacy_ratchet(grown, grown)
    assert len(errors) == 1
    assert 'shrink-only' in errors[0]
    assert 'test_newly_allowlisted.py' in errors[0]


def test_legacy_ratchet_rejects_stale_entries():
    errors = check_legacy_ratchet(set(LEGACY_UNLISTED_BASELINE), all_files=set())
    assert len(errors) == 1
    assert 'no longer exist' in errors[0]


def test_legacy_ratchet_allows_shrinking():
    smaller = set(sorted(LEGACY_UNLISTED_BASELINE)[:1])
    assert check_legacy_ratchet(smaller, smaller) == []


def test_real_repo_has_no_orphans_and_frozen_allowlist():
    all_files = discover_test_files(BACKEND_DIR)
    selected = set(discover_unit_tests())
    assert find_orphans(all_files, selected, set(LEGACY_UNLISTED_TESTS)) == []
    assert set(LEGACY_UNLISTED_TESTS) == set(LEGACY_UNLISTED_BASELINE)
    assert check_legacy_ratchet(set(LEGACY_UNLISTED_TESTS), all_files) == []
