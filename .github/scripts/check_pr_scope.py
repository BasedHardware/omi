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
  ``scope-approved`` label (label events re-trigger CI). Local lane: export
  ``OMI_SCOPE_APPROVED=1`` to acknowledge and push.
- Revert PRs (body carries GitHub's ``Reverts owner/repo#N`` marker) are
  notice-only: AGENTS.md requires reverts to merge immediately.
- ``push`` events (post-merge main) are notice-only: there is nothing left
  to gate.

Diffing matches ``scripts/changed-files`` policy: ``--no-renames``, so a moved
file cannot escape classification via rename notation, and quoted non-ASCII
paths are unquoted before classification.

Runs from the checks manifest (local + ci lanes). Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

WARN_LINES = 1500
FAIL_LINES = 3000
OVERRIDE_LABEL = 'scope-approved'
LOCAL_OVERRIDE_ENV = 'OMI_SCOPE_APPROVED'

# GitHub's auto-generated revert PR body ("Reverts owner/repo#123").
_REVERT_BODY_RE = re.compile(r'^Reverts \S+/\S+#\d+', re.MULTILINE)

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


def unquote_git_path(path: str) -> str:
    """Undo git's C-style quoting of non-ASCII paths (core.quotePath default)."""
    if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
        inner = path[1:-1]
        decoded = inner.encode('latin-1', 'backslashreplace').decode('unicode_escape')
        return decoded.encode('latin-1', 'replace').decode('utf-8', 'replace')
    return path


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
        path = unquote_git_path(path)
        if not is_production_source(path):
            continue
        changed = int(added) + int(deleted)
        total += changed
        per_file.append((changed, path))
    per_file.sort(reverse=True)
    return total, per_file


def evaluate(total: int, labels: set[str], *, enforce: bool = True, enforce_reason: str = '') -> tuple[str, int]:
    """Return (github annotation line, exit code)."""
    if total >= FAIL_LINES:
        if OVERRIDE_LABEL in labels:
            return (
                f"::notice title=PR scope::{total} changed production-source lines >= {FAIL_LINES}; "
                f"allowed by '{OVERRIDE_LABEL}' label.",
                0,
            )
        if not enforce:
            return (
                f'::notice title=PR scope::{total} changed production-source lines >= {FAIL_LINES}; '
                f'not enforced: {enforce_reason}.',
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
        return (
            f"::warning title=PR scope::{total} changed production-source lines >= {WARN_LINES}. "
            f"Consider splitting; historically PRs above this size shipped regressions.",
            0,
        )
    return (f'::notice title=PR scope::{total} changed production-source lines (limit {FAIL_LINES}).', 0)


def resolve_enforcement(pr_body: str, environ: dict[str, str]) -> tuple[bool, str]:
    """Decide whether the fail threshold is enforced for this invocation."""
    if environ.get('GITHUB_EVENT_NAME', '') == 'push':
        return False, 'push event (already merged; nothing to gate)'
    if _REVERT_BODY_RE.search(pr_body):
        return False, 'revert PR (AGENTS.md: reverts merge immediately)'
    if environ.get(LOCAL_OVERRIDE_ENV) == '1':
        return False, f'{LOCAL_OVERRIDE_ENV}=1 override'
    return True, ''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='diff base ref/sha (merge-base diff: base...HEAD)')
    parser.add_argument('--labels-json', default='[]', help='JSON array of PR label names')
    parser.add_argument('--pr-body-file', default='', help='path to the PR body text (revert detection)')
    args = parser.parse_args()

    # --no-renames mirrors scripts/changed-files: a moved file must not escape
    # classification via rename notation ("dir/{old => new}").
    numstat = subprocess.run(
        ['git', 'diff', '--numstat', '--no-renames', f'{args.base}...HEAD'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    total, per_file = count_production_lines(numstat)

    try:
        labels = {str(label) for label in json.loads(args.labels_json)}
    except (json.JSONDecodeError, TypeError):
        print(f'::warning title=PR scope::could not parse --labels-json {args.labels_json!r}; ignoring labels.')
        labels = set()

    pr_body = ''
    if args.pr_body_file and Path(args.pr_body_file).is_file():
        pr_body = Path(args.pr_body_file).read_text(encoding='utf-8', errors='replace')

    enforce, enforce_reason = resolve_enforcement(pr_body, dict(os.environ))

    for changed, path in per_file[:10]:
        print(f'  {changed:>6}  {path}')
    message, code = evaluate(total, labels, enforce=enforce, enforce_reason=enforce_reason)
    print(message)
    return code


if __name__ == '__main__':
    sys.exit(main())
