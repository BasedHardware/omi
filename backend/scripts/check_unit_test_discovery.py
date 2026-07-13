#!/usr/bin/env python3
"""Fail when a backend test file is not discovered by any documented runner.

Motivation (regression research, July 2026): a large PR once rewrote the unit
runner's explicit test list and silently dropped two existing test files from
CI while the files stayed in the tree; the gap was only noticed weeks later.
This check makes that failure mode impossible to repeat quietly:

1. Every ``test_*.py`` / ``*_test.py`` under ``backend/tests/`` and
   ``backend/testing/`` must be either selected by
   ``scripts/select_backend_unit_tests.py --all`` or matched by an entry in
   ``KNOWN_OTHER_RUNNERS`` (suites that run outside the unit lane on purpose).
2. ``LEGACY_UNLISTED_TESTS`` (the selector's known-orphan allowlist) is a
   no-increase ratchet: entries may be removed, never added, and every entry
   must still exist on disk so deletions clean the list up.

Run from ``backend/``: ``python3 scripts/check_unit_test_discovery.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Test trees that intentionally run outside the unit suite. Every prefix must
# name the runner that owns it so a reader can verify coverage in one hop.
KNOWN_OTHER_RUNNERS = {
    'testing/e2e/': 'backend-hermetic-e2e.yml (hermetic E2E harness)',
    'testing/contracts/': 'desktop-backend-contracts.yml (cross-language contracts)',
    'tests/container/': 'parakeet_gpu_tests.yml (nightly GPU suite)',
    'tests/integration/': 'live-service tests; excluded from CI by policy (AGENTS.md Testing)',
    'tests/eval/': 'live-LLM evals; excluded from CI by policy (AGENTS.md Testing)',
}

# Frozen copy of the selector's LEGACY_UNLISTED_TESTS. The ratchet direction is
# shrink-only: fixing one of these means deleting it here AND in the selector.
LEGACY_UNLISTED_BASELINE = frozenset(
    {
        'tests/test_cache_manager.py',
        'tests/unit/test_diarizer_dockerfile.py',
        'tests/unit/test_lazy_conversation_processing.py',
    }
)


def discover_test_files(backend_dir: Path) -> set[str]:
    files: set[str] = set()
    for root_name in ('tests', 'testing'):
        root = backend_dir / root_name
        if not root.is_dir():
            continue
        for pattern in ('test_*.py', '*_test.py'):
            files.update(p.relative_to(backend_dir).as_posix() for p in root.rglob(pattern) if p.is_file())
    return files


def covered_by_other_runner(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in KNOWN_OTHER_RUNNERS)


def find_orphans(all_files: set[str], selected: set[str], legacy_unlisted: set[str]) -> list[str]:
    return sorted(
        path
        for path in all_files
        if path not in selected and path not in legacy_unlisted and not covered_by_other_runner(path)
    )


def check_legacy_ratchet(current_legacy: set[str], all_files: set[str]) -> list[str]:
    errors: list[str] = []
    grown = sorted(current_legacy - LEGACY_UNLISTED_BASELINE)
    if grown:
        errors.append(
            'LEGACY_UNLISTED_TESTS grew (shrink-only ratchet). New entries: '
            + ', '.join(grown)
            + '. Make the test discoverable by the unit runner instead of allowlisting it.'
        )
    stale = sorted(entry for entry in current_legacy if entry not in all_files)
    if stale:
        errors.append(
            'LEGACY_UNLISTED_TESTS lists files that no longer exist: '
            + ', '.join(stale)
            + '. Remove them from the selector and from LEGACY_UNLISTED_BASELINE here.'
        )
    return errors


def main() -> int:
    sys.path.insert(0, str(BACKEND_DIR))
    from scripts.select_backend_unit_tests import LEGACY_UNLISTED_TESTS, discover_unit_tests

    all_files = discover_test_files(BACKEND_DIR)
    selected = set(discover_unit_tests())
    errors: list[str] = []

    orphans = find_orphans(all_files, selected, set(LEGACY_UNLISTED_TESTS))
    if orphans:
        runner_map = '; '.join(f'{prefix} -> {runner}' for prefix, runner in KNOWN_OTHER_RUNNERS.items())
        errors.append(
            'Test files exist but no runner discovers them (they would silently never run):\n  '
            + '\n  '.join(orphans)
            + '\nEither place them under a directory the unit selector discovers '
            + '(see FULL_TEST_ROOTS in scripts/select_backend_unit_tests.py) or, for suites '
            + f'with a dedicated runner, extend KNOWN_OTHER_RUNNERS. Known runners: {runner_map}'
        )

    errors.extend(check_legacy_ratchet(set(LEGACY_UNLISTED_TESTS), all_files))

    if errors:
        for error in errors:
            print(f'ERROR: {error}', file=sys.stderr)
        return 1

    print(
        f'unit test discovery OK: {len(selected)} selected, '
        f'{len(all_files) - len(selected)} covered by other runners/allowlist, 0 orphans'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
