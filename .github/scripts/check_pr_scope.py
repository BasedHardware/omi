#!/usr/bin/env python3
"""PR scope governor: bound the amount of production source one PR may change.

Motivation (regression research over merged PRs, July 2026): reviewer and CI
effectiveness fall off sharply with diff size. In the last ~30 merged PRs,
every PR above ~2,400 changed production-source lines shipped at least one
production regression (2,475 → 3 regressions; 2,652 → 1; 51,564 → 4+ plus two
test files silently dropped from the CI runner), while defects in small PRs
were reliably caught by review. Bounding reviewable size is the cheapest lever
against the multi-regression PR shape.

Policy (production-source lines = added + deleted, excluding tests, docs,
l10n, lockfiles, and generated files):

- >= WARN_LINES:  warning annotation — consider splitting (silenced by the
  same overrides as the fail tier).
- >= FAIL_LINES:  check fails. Split the PR, or a maintainer applies the
  ``scope-approved`` label (label events re-trigger CI). Local lane: export
  ``OMI_SCOPE_APPROVED=1`` to acknowledge and push. Emergency reverts use the
  same overrides — an author-editable signal (body/title text) must not be
  able to waive a maintainer-controlled gate.
- ``push`` events (post-merge main) are notice-only: there is nothing left
  to gate.

Diffing matches ``scripts/changed-files`` policy: ``--no-renames``, so a moved
file cannot escape classification via rename notation (a pure move therefore
counts both sides — the label/env override is the escape), and ``-z`` output
keeps non-ASCII paths raw.

Runs from the checks manifest (local + ci lanes). Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

WARN_LINES = 1500
FAIL_LINES = 3000
OVERRIDE_LABEL = 'scope-approved'
LOCAL_OVERRIDE_ENV = 'OMI_SCOPE_APPROVED'

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


def evaluate(total: int, labels: set[str], *, waiver_reason: str | None = None) -> tuple[str, int]:
    """Return (github annotation line, exit code). waiver_reason=None means enforce."""
    if OVERRIDE_LABEL in labels:
        waiver_reason = waiver_reason or f"'{OVERRIDE_LABEL}' label"
    if total >= FAIL_LINES:
        if waiver_reason:
            return (
                f'::notice title=PR scope::{total} changed production-source lines >= {FAIL_LINES}; '
                f'allowed: {waiver_reason}.',
                0,
            )
        return (
            f"::error title=PR scope::{total} changed production-source lines >= {FAIL_LINES}. "
            f"PRs this large ship regressions review cannot catch — split into independently "
            f"reviewable PRs, have a maintainer apply the '{OVERRIDE_LABEL}' label, or (local "
            f"pre-push only) export {LOCAL_OVERRIDE_ENV}=1.",
            1,
        )
    if total >= WARN_LINES:
        if waiver_reason:
            return (
                f'::notice title=PR scope::{total} changed production-source lines >= {WARN_LINES}; '
                f'allowed: {waiver_reason}.',
                0,
            )
        return (
            f"::warning title=PR scope::{total} changed production-source lines >= {WARN_LINES}. "
            f"Consider splitting; historically PRs above this size shipped regressions.",
            0,
        )
    return (f'::notice title=PR scope::{total} changed production-source lines (limit {FAIL_LINES}).', 0)


def resolve_waiver(environ: dict[str, str]) -> str | None:
    """Non-None reason means the fail/warn tiers are waived for this invocation."""
    if environ.get('GITHUB_EVENT_NAME', '') == 'push':
        return 'push event (already merged; nothing to gate)'
    if environ.get(LOCAL_OVERRIDE_ENV) == '1':
        return f'{LOCAL_OVERRIDE_ENV}=1 override'
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='diff base (pre-resolved to the merge-base by run_checks.py)')
    parser.add_argument('--head', default='HEAD', help='diff head ref/sha')
    parser.add_argument('--labels-json', default='[]', help='JSON array of PR label names')
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

    try:
        labels = {str(label) for label in json.loads(args.labels_json)}
    except (json.JSONDecodeError, TypeError):
        print(f'::warning title=PR scope::could not parse --labels-json {args.labels_json!r}; ignoring labels.')
        labels = set()

    for changed, path in per_file[:10]:
        print(f'  {changed:>6}  {path}')
    message, code = evaluate(total, labels, waiver_reason=resolve_waiver(dict(os.environ)))
    print(message)
    return code


if __name__ == '__main__':
    sys.exit(main())
