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

- >= WARN_LINES:  warning annotation — consider splitting.
- >= FAIL_LINES:  check fails. Split the PR, or a maintainer applies the
  ``scope-approved`` label to acknowledge the review cost (label re-triggers
  the check; approval is per-PR).

Stdlib-only. Usage:
  check_pr_scope.py --base <ref> [--labels "a,b"]      # in CI
  check_pr_scope.py --self-test                        # unit checks
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

WARN_LINES = 1500
FAIL_LINES = 3000
OVERRIDE_LABEL = 'scope-approved'

# Paths whose churn does not count toward reviewable production source.
# Kept aligned with what reviewers actually skim vs. verify.
_EXCLUDED_PATTERNS = (
    r'(^|/)tests?/',  # test trees (tests/, test/)
    r'(^|/)testing/',
    r'(^|/)e2e/',
    r'(^|/)test_[^/]*$',  # test files by name
    r'_test\.[^/]*$',
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
    """Sum added+deleted lines over production-source files from `git diff --numstat`."""
    total = 0
    per_file: list[tuple[int, str]] = []
    for line in numstat_output.splitlines():
        parts = line.split('\t')
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


def evaluate(total: int, labels: set[str]) -> tuple[str, int]:
    """Return (github annotation line, exit code)."""
    if total >= FAIL_LINES:
        if OVERRIDE_LABEL in labels:
            return (
                f"::notice title=PR scope::{total} changed production-source lines >= {FAIL_LINES}; "
                f"allowed by '{OVERRIDE_LABEL}' label.",
                0,
            )
        return (
            f"::error title=PR scope::{total} changed production-source lines >= {FAIL_LINES}. "
            f"PRs this large ship regressions review cannot catch — split into independently "
            f"reviewable PRs, or have a maintainer apply the '{OVERRIDE_LABEL}' label.",
            1,
        )
    if total >= WARN_LINES:
        return (
            f"::warning title=PR scope::{total} changed production-source lines >= {WARN_LINES}. "
            f"Consider splitting; historically PRs above this size shipped regressions.",
            0,
        )
    return (f'::notice title=PR scope::{total} changed production-source lines (limit {FAIL_LINES}).', 0)


def self_test() -> int:
    prod = [
        'backend/utils/sync/pipeline.py',
        'app/lib/services/wals/wal.dart',
        'desktop/macos/Backend-Rust/src/routes/proxy.rs',
        '.github/workflows/gcp_backend.yml',
        'backend/testharness.py',  # 'testharness' must not match test excludes
    ]
    excluded = [
        'backend/tests/unit/test_sync_v2.py',
        'backend/testing/e2e/test_crud.py',
        'app/test/widget_test.dart',
        'docs/doc/developer/guide.mdx',
        'AGENTS.md',
        'app/lib/l10n/app_fr.arb',
        'backend/pylock.toml',
        'app/pubspec.lock',
        'web/package-lock.json',
        'app/lib/gen/assets.g.dart',
        '.cursor/plans/x.plan.md',
        'desktop/macos/changelog/unreleased/fix.json',
        'backend/openapi.json',
    ]
    failures = []
    failures += [f'expected production: {p}' for p in prod if not is_production_source(p)]
    failures += [f'expected excluded: {p}' for p in excluded if is_production_source(p)]

    numstat = '10\t5\tbackend/utils/a.py\n3\t0\tbackend/tests/unit/test_a.py\n-\t-\tapp/assets/img.png\n7\t2\tapp/lib/b.dart\n'
    total, per_file = count_production_lines(numstat)
    if total != 24:
        failures.append(f'count_production_lines total {total} != 24')
    if [p for _, p in per_file] != ['backend/utils/a.py', 'app/lib/b.dart']:
        failures.append(f'unexpected per-file set: {per_file}')

    cases = [
        (100, set(), 0, '::notice'),
        (WARN_LINES, set(), 0, '::warning'),
        (FAIL_LINES, set(), 1, '::error'),
        (FAIL_LINES, {OVERRIDE_LABEL}, 0, '::notice'),
        (FAIL_LINES, {'unrelated'}, 1, '::error'),
    ]
    for total_lines, labels, want_code, want_prefix in cases:
        message, code = evaluate(total_lines, labels)
        if code != want_code or not message.startswith(want_prefix):
            failures.append(f'evaluate({total_lines}, {labels}) -> ({message[:24]}…, {code})')

    if failures:
        for failure in failures:
            print(f'SELF-TEST FAIL: {failure}', file=sys.stderr)
        return 1
    print('check_pr_scope self-test OK')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', help='diff base ref/sha (merge-base diff: base...HEAD)')
    parser.add_argument('--labels', default='', help='comma-separated PR label names')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.base:
        parser.error('--base is required unless --self-test')

    numstat = subprocess.run(
        ['git', 'diff', '--numstat', f'{args.base}...HEAD'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    total, per_file = count_production_lines(numstat)
    labels = {label.strip() for label in args.labels.split(',') if label.strip()}

    for changed, path in per_file[:10]:
        print(f'  {changed:>6}  {path}')
    message, code = evaluate(total, labels)
    print(message)
    return code


if __name__ == '__main__':
    sys.exit(main())
