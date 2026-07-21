#!/usr/bin/env python3
"""PR scope advisor: report the amount of production source one PR changes.

Motivation (regression research over merged PRs, July 2026): reviewer and CI
effectiveness fall off sharply with diff size. In the last ~30 merged PRs,
every PR above ~2,400 changed production-source lines shipped at least one
production regression (2,475 → 3 regressions; 2,652 → 1; 51,564 → 4+ plus two
test files silently dropped from the CI runner), while defects in small PRs
were reliably caught by review.

Policy — advisory only, never blocks (maintainer decision on #9634: each PR
carries a human verification cost, so a hard gate that forces feature splits
can cost more human time than the regressions it prevents; the size signal
stays because review effectiveness demonstrably collapses with diff size):

- >= WARN_LINES:   warning annotation — flags the PR for extra review depth
  and suggests splitting where a split is free.
- >= REVIEW_COLLAPSE_LINES: stronger warning citing the audit finding, so the
  reviewer sizes their skepticism to the diff. Still exit 0.
- ``push`` events (post-merge main) are notice-only: nothing left to advise.

Diffing matches ``scripts/changed-files`` policy: ``--no-renames``, so a moved
file cannot escape classification via rename notation (a pure move therefore
counts both sides), and ``-z`` output keeps non-ASCII paths raw.

Runs from the checks manifest (local + ci lanes). Stdlib-only.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

WARN_LINES = 1500
REVIEW_COLLAPSE_LINES = 3000

# Paths whose churn does not count toward reviewable production source.
# Covers every test convention present in this repo: Python/Dart (tests/,
# test_*.py), Swift (Desktop/Tests/, *Tests.swift), JS/TS (__tests__/,
# *.test.ts), Flutter integration (integration_test/).
_EXCLUDED_PATTERNS = (
    r'(^|/)[Tt]ests?/',
    r'(^|/)__tests__/',
    r'(^|/)testing/',
    r'(^|/)e2e/',
    r'(^|/)integration_test/',
    r'(^|/)test_[^/]*\.(py|dart|swift|rs|ts|tsx|js|jsx)$',
    r'_test\.(py|go|rs|dart|ts|tsx|js|jsx)$',
    r'\.test\.(ts|tsx|js|jsx|mjs|cjs)$',
    r'Tests\.swift$',
    r'\.md$',
    r'\.mdx$',
    r'^docs/',
    r'\.arb$',  # l10n
    r'\.lock$',
    r'(^|/)pylock[^/]*\.toml$',
    r'package-lock\.json$',
    r'\.g\.dart$',
    r'\.gen\.dart$',
    r'(^|/)generated/',
    r'^\.cursor/',
    r'(^|/)changelog/',
    r'\.snap$',
    r'(^|/)openapi\.json$',
)
_EXCLUDED_RE = re.compile('|'.join(f'(?:{p})' for p in _EXCLUDED_PATTERNS))


def is_production_source(path: str) -> bool:
    return not _EXCLUDED_RE.search(path)


def count_production_lines(numstat_output: str) -> tuple[int, list[tuple[int, str]]]:
    """Sum added+deleted lines over production files from `git diff --numstat -z` output."""
    total = 0
    per_file: list[tuple[int, str]] = []
    # -z records: "added\tdeleted\tpath\0" with the path raw (no C-quoting).
    for record in numstat_output.split('\0'):
        parts = record.split('\t', 2)
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if added == '-' or deleted == '-':  # binary
            continue
        if not is_production_source(path):
            continue
        changed = int(added) + int(deleted)
        total += changed
        per_file.append((changed, path))
    per_file.sort(reverse=True)
    return total, per_file


def evaluate(total: int, *, notice_only: bool = False) -> str:
    """Return the GitHub annotation line for this diff size. Advisory: never fails."""
    if notice_only:
        return f'::notice title=PR scope::{total} changed production-source lines.'
    if total >= REVIEW_COLLAPSE_LINES:
        return (
            f'::warning title=PR scope::{total} changed production-source lines >= '
            f'{REVIEW_COLLAPSE_LINES}. In the audited merge history every PR this size '
            f'shipped at least one regression that review missed — review with that '
            f'expectation, and split if a split does not add verification burden. '
            f'Advisory only; this check never blocks.'
        )
    if total >= WARN_LINES:
        return (
            f'::warning title=PR scope::{total} changed production-source lines >= {WARN_LINES}. '
            f'Historically PRs above this size shipped regressions; consider splitting where '
            f'a split is free. Advisory only; this check never blocks.'
        )
    return f'::notice title=PR scope::{total} changed production-source lines.'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='diff base (pre-resolved to the merge-base by run_checks.py)')
    parser.add_argument('--head', default='HEAD', help='diff head ref/sha')
    args = parser.parse_args()

    # --no-renames mirrors scripts/changed-files: a moved file must not escape
    # classification via rename notation ("dir/{old => new}"); -z keeps
    # non-ASCII paths raw instead of C-quoted.
    diff = subprocess.run(
        ['git', 'diff', '--numstat', '--no-renames', '-z', f'{args.base}...{args.head}'],
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode != 0:
        print(
            f'::error title=PR scope::git diff {args.base}...{args.head} failed '
            f'(is the base fetched?): {diff.stderr.strip()}'
        )
        return 1
    total, per_file = count_production_lines(diff.stdout)

    for changed, path in per_file[:10]:
        print(f'  {changed:>6}  {path}')
    print(evaluate(total, notice_only=os.environ.get('GITHUB_EVENT_NAME', '') == 'push'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
