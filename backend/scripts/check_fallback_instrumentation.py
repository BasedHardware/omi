#!/usr/bin/env python3
"""Optional ratchet: warn when touched files add fallback branches without record_fallback.

Usage:
  python scripts/check_fallback_instrumentation.py path/to/file.py [more files...]
  git diff --name-only | xargs python scripts/check_fallback_instrumentation.py

Not wired into CI yet — advisory only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_FALLBACK_BRANCH = re.compile(
    r'(?:fallback|fail.?open|degraded)',
    re.IGNORECASE,
)
_RECORD_FALLBACK = re.compile(
    r'record_fallback|recordFallback',
    re.IGNORECASE,
)
_DIFF_HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')


def _added_lines(path: Path) -> list[tuple[int, str]]:
    try:
        import subprocess

        result = subprocess.run(
            ['git', 'diff', '--unified=0', '--', str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return [
                (idx, line)
                for idx, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), start=1)
            ]
    except Exception:
        return [
            (idx, line)
            for idx, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), start=1)
        ]

    added: list[tuple[int, str]] = []
    line_no = 1
    for line in result.stdout.splitlines():
        if line.startswith('+++') or line.startswith('---'):
            continue
        hunk_match = _DIFF_HUNK.match(line)
        if hunk_match:
            line_no = int(hunk_match.group(1))
            continue
        if line.startswith('+') and not line.startswith('+++'):
            added.append((line_no, line[1:]))
            line_no += 1
    return added


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding='utf-8', errors='replace')
    if _RECORD_FALLBACK.search(text):
        return []

    warnings: list[str] = []
    for line_no, line in _added_lines(path):
        if _FALLBACK_BRANCH.search(line):
            warnings.append(f'{path}:{line_no}: fallback-like branch without record_fallback/recordFallback')
    return warnings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    warnings: list[str] = []
    for raw in argv[1:]:
        path = Path(raw)
        if not path.is_file():
            continue
        warnings.extend(check_file(path))

    for warning in warnings:
        print(f'warning: {warning}', file=sys.stderr)

    return 1 if warnings else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
