#!/usr/bin/env python3
"""Fail when a backend test file is not discovered by any documented runner.

Motivation (regression research, July 2026): a large PR once rewrote the unit
runner's explicit test list and silently dropped two existing test files from
CI while the files stayed in the tree; the gap was only noticed weeks later.
This check makes that failure mode impossible to repeat quietly:

1. Every ``test_*.py`` / ``*_test.py`` under ``backend/tests/`` and
   ``backend/testing/`` must be selected by
   ``scripts/select_backend_unit_tests.py --all``, verified against a
   dedicated runner workflow (``WORKFLOW_COVERED_PREFIXES`` — the workflow
   file must exist and actually reference the tree or the individual file),
   excluded by written policy (``POLICY_EXCLUDED_PREFIXES``), or allowlisted.
2. Allowlists only shrink: ``LEGACY_UNLISTED_TESTS`` (the selector's
   known-orphan set) is pinned to a frozen baseline in both directions, and
   ``MANUAL_ONLY_TESTS`` entries must exist on disk.

Run from ``backend/``: ``python3 scripts/check_unit_test_discovery.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
WORKFLOWS_DIR = REPO_DIR / '.github' / 'workflows'

sys.path.insert(0, str(BACKEND_DIR))

from scripts.select_backend_unit_tests import LEGACY_UNLISTED_TESTS, discover_unit_tests  # noqa: E402

# Test trees run by a dedicated workflow. mode='directory': the workflow runs
# the whole tree (its text must reference the prefix); mode='explicit': the
# workflow lists files one by one (each file must appear by name, so a file
# missing from the list is an orphan even though the directory is "covered").
WORKFLOW_COVERED_PREFIXES = {
    'testing/e2e/': ('backend-hermetic-e2e.yml', 'directory'),
    'testing/contracts/': ('desktop-backend-contracts.yml', 'directory'),
    'tests/container/': ('parakeet_gpu_tests.yml', 'explicit'),
}

# Excluded from CI by written policy (AGENTS.md Testing: live-service tests
# stay out of the CI suite). No workflow to verify against.
POLICY_EXCLUDED_PREFIXES = {
    'tests/integration/': 'live-service tests; excluded from CI by policy (AGENTS.md Testing)',
    'tests/eval/': 'live-LLM evals; excluded from CI by policy (AGENTS.md Testing)',
}

# On-demand harnesses deliberately outside every scheduled runner. Entries
# must exist on disk; additions are a reviewed diff of this checker itself.
MANUAL_ONLY_TESTS: dict[str, str] = {}

# Frozen copy of the selector's LEGACY_UNLISTED_TESTS. Pinned in both
# directions: the selector's set may not grow past this baseline, and fixing
# an entry means deleting it in the selector AND here in the same PR.
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


def load_workflow_texts(workflows_dir: Path) -> dict[str, str]:
    texts: dict[str, str] = {}
    for workflow_file, _mode in WORKFLOW_COVERED_PREFIXES.values():
        path = workflows_dir / workflow_file
        texts[workflow_file] = path.read_text(encoding='utf-8') if path.is_file() else ''
    return texts


def _runs_reference(text: str, needle: str) -> bool:
    """True when a non-comment invocation line (pytest/run.sh) names the needle
    as a run target — a commented-out mention, a --deselect/--ignore target, or
    prose must not count as coverage. Backslash continuations are joined so a
    path on a wrapped line still belongs to its invocation."""
    joined = text.replace('\\\n', ' ')
    for raw_line in joined.splitlines():
        line = raw_line.strip()
        if line.startswith('#') or needle not in line:
            continue
        if 'pytest' not in line and 'run.sh' not in line:
            continue
        tokens = line.split()
        for index, token in enumerate(tokens):
            if needle not in token:
                continue
            previous = tokens[index - 1] if index else ''
            if previous in ('--deselect', '--ignore') or token.startswith(('--deselect=', '--ignore=')):
                continue
            return True
    return False


def workflow_map_errors(workflow_texts: dict[str, str]) -> list[str]:
    """The runner map must describe reality: workflows exist and run their trees."""
    errors = []
    for prefix, (workflow_file, mode) in WORKFLOW_COVERED_PREFIXES.items():
        text = workflow_texts.get(workflow_file, '')
        if not text:
            errors.append(
                f'WORKFLOW_COVERED_PREFIXES maps {prefix} to .github/workflows/{workflow_file}, '
                'which does not exist. Update the map to the real runner.'
            )
        elif mode == 'directory' and not _runs_reference(text, prefix.rstrip('/')):
            errors.append(
                f'.github/workflows/{workflow_file} no longer references {prefix.rstrip("/")}; '
                f'it cannot be credited with running that tree. Update WORKFLOW_COVERED_PREFIXES.'
            )
    return errors


def find_orphans(
    all_files: set[str],
    selected: set[str],
    legacy_unlisted: set[str],
    workflow_texts: dict[str, str],
) -> list[str]:
    orphans = []
    for path in sorted(all_files):
        if path in selected or path in legacy_unlisted or path in MANUAL_ONLY_TESTS:
            continue
        if any(path.startswith(prefix) for prefix in POLICY_EXCLUDED_PREFIXES):
            continue
        covered = False
        for prefix, (workflow_file, mode) in WORKFLOW_COVERED_PREFIXES.items():
            if not path.startswith(prefix):
                continue
            text = workflow_texts.get(workflow_file, '')
            # directory mode: the tree reference was validated by
            # workflow_map_errors; explicit mode: this very file must appear
            # on a live invocation line (not a comment or --deselect).
            covered = bool(text) and (mode == 'directory' or _runs_reference(text, path))
            break
        if not covered:
            orphans.append(path)
    return orphans


def check_legacy_ratchet(current_legacy: set[str], all_files: set[str]) -> list[str]:
    errors: list[str] = []
    grown = sorted(current_legacy - LEGACY_UNLISTED_BASELINE)
    if grown:
        errors.append(
            'LEGACY_UNLISTED_TESTS grew (shrink-only ratchet). New entries: '
            + ', '.join(grown)
            + '. Make the test discoverable by the unit runner instead of allowlisting it.'
        )
    shrunk_without_baseline_update = sorted(LEGACY_UNLISTED_BASELINE - current_legacy)
    if shrunk_without_baseline_update:
        errors.append(
            'LEGACY_UNLISTED_TESTS shrank — good. Also remove from LEGACY_UNLISTED_BASELINE in '
            'scripts/check_unit_test_discovery.py: ' + ', '.join(shrunk_without_baseline_update)
        )
    stale = sorted(entry for entry in current_legacy if entry not in all_files)
    stale += sorted(entry for entry in MANUAL_ONLY_TESTS if entry not in all_files)
    if stale:
        errors.append(
            'Allowlists reference files that no longer exist: '
            + ', '.join(stale)
            + '. Remove them from the selector/checker allowlists.'
        )
    return errors


def main() -> int:
    all_files = discover_test_files(BACKEND_DIR)
    selected = set(discover_unit_tests())
    workflow_texts = load_workflow_texts(WORKFLOWS_DIR)
    errors: list[str] = []

    errors.extend(workflow_map_errors(workflow_texts))

    orphans = find_orphans(all_files, selected, set(LEGACY_UNLISTED_TESTS), workflow_texts)
    if orphans:
        runner_map = '; '.join(f'{prefix} -> {wf} ({mode})' for prefix, (wf, mode) in WORKFLOW_COVERED_PREFIXES.items())
        errors.append(
            'Test files exist but no runner discovers them (they would silently never run):\n  '
            + '\n  '.join(orphans)
            + '\nEither place them under a directory the unit selector discovers '
            + '(see FULL_TEST_ROOTS in scripts/select_backend_unit_tests.py), add them to their '
            + f'dedicated runner workflow, or extend the maps in this checker. Known runners: {runner_map}'
        )

    errors.extend(check_legacy_ratchet(set(LEGACY_UNLISTED_TESTS), all_files))

    if errors:
        for error in errors:
            print(f'ERROR: {error}', file=sys.stderr)
        return 1

    print(
        f'unit test discovery OK: {len(selected)} selected, '
        f'{len(all_files) - len(selected)} covered by other runners/policy/allowlists, 0 orphans'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
