#!/usr/bin/env python3
"""Replay backend unit-test selection over recent first-parent main commits.

Each first-parent commit on main is one merged PR (or a direct push), so its
first-parent diff is the change set CI selected for. The current selector is
applied to every diff twice, with import-graph selection on and off, and the
script reports how many test files each mode runs and how often it falls back
to the full suite. Use it before changing selection rules, and quote its
output (with the commit range) as the evidence for the change.

    python3 scripts/backtest_backend_unit_selection.py --limit 300 [--json out.json]

It reads git history only; it never runs tests.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import scripts.select_backend_unit_tests as selector  # noqa: E402


def git(*args: str) -> str:
    return subprocess.run(['git', '-C', str(REPO_DIR), *args], check=True, capture_output=True, text=True).stdout


def recent_commits(ref: str, limit: int, since: str | None) -> list[str]:
    args = ['log', '--first-parent', '--format=%H', ref]
    if since:
        args.append(f'--since={since}')
    args += ['--', 'backend']
    return git(*args).split()[:limit]


def changed_paths(commit: str) -> list[str]:
    # Matches scripts/changed-files: no rename detection, deletions included.
    out = git('diff', '--name-only', '--no-renames', '--diff-filter=ACMRTD', f'{commit}^1', commit)
    return [line for line in out.splitlines() if line.strip()]


def summarize(counts: list[int], full: int) -> dict[str, Any]:
    ordered = sorted(counts)
    return {
        'commits': len(counts),
        'mean': round(statistics.mean(counts), 1) if counts else 0,
        'median': ordered[len(ordered) // 2] if ordered else 0,
        'p90': ordered[int(len(ordered) * 0.9)] if ordered else 0,
        'full_suite_runs': sum(1 for count in counts if count >= full),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--limit', type=int, default=300)
    parser.add_argument('--since')
    parser.add_argument('--json', type=Path, help='write per-commit rows and the summary here')
    args = parser.parse_args()

    all_tests = selector.discover_all_tests()
    full = len(all_tests)
    rows = []
    for commit in recent_commits(args.ref, args.limit, args.since):
        paths = changed_paths(commit)
        os.environ[selector.GRAPH_SELECTION_ENV] = '0'
        legacy, legacy_reason = selector.tests_for_changed_paths(paths, all_tests)
        os.environ[selector.GRAPH_SELECTION_ENV] = '1'
        graph, graph_reason = selector.tests_for_changed_paths(paths, all_tests)
        missing = sorted(set(legacy) - set(graph)) if len(legacy) < full else []
        rows.append(
            {
                'commit': commit[:12],
                'legacy': len(legacy),
                'graph': len(graph),
                'legacy_reason': legacy_reason,
                'graph_reason': graph_reason,
                # A narrow legacy selection the graph mode does not include is a
                # regression in coverage; it must stay empty.
                'legacy_narrow_not_in_graph': missing,
            }
        )
    summary: dict[str, Any] = {
        'ref': git('rev-parse', '--short=12', args.ref).strip(),
        'full_suite_files': full,
        'legacy': summarize([row['legacy'] for row in rows], full),
        'graph': summarize([row['graph'] for row in rows], full),
        'commits_losing_narrow_legacy_tests': sum(1 for row in rows if row['legacy_narrow_not_in_graph']),
    }
    if summary['legacy']['mean']:
        summary['file_run_reduction_pct'] = round(100 * (1 - summary['graph']['mean'] / summary['legacy']['mean']), 1)
    print(json.dumps(summary, indent=2))
    if args.json:
        args.json.write_text(json.dumps({'summary': summary, 'rows': rows}, indent=2) + '\n', encoding='utf-8')
    return 1 if summary['commits_losing_narrow_legacy_tests'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
