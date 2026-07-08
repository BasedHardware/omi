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
_DIFF_HUNK = re.compile(r'^@@')


def _added_lines(path: Path) -> list[str]:
    try:
        import subprocess

        result = subprocess.run(
            ['git', 'diff', '--unified=0', '--', str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return path.read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception:
        return path.read_text(encoding='utf-8', errors='replace').splitlines()

    added: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith('+++') or line.startswith('---') or _DIFF_HUNK.match(line):
            continue
        if line.startswith('+') and not line.startswith('+++'):
            added.append(line[1:])
    return added


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding='utf-8', errors='replace')
    if _RECORD_FALLBACK.search(text):
        return []

    warnings: list[str] = []
    for line_no, line in enumerate(_added_lines(path), start=1):
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
