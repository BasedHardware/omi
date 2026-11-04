#!/usr/bin/env python3
"""Build a backend source -> unit-test map from per-test-file coverage data.

usage: build_test_coverage_map.py --data-dir DIR --out MAP.json [--sha SHA]

`backend/test.sh` writes one coverage data file per isolated test file when BACKEND_COVERAGE_MAP_DIR is set
(`<slug>.cov`, plus `<slug>.path` naming the test). For each test, a first-party source file counts as exercised
only when the test executed a line inside one of that file's function or method bodies. Lines run at import time
(module-level code, decorators, class bodies) do not count: every test that imports a hub module runs those, which
is why a static import closure still selects ~70% of the suite (shipspeed 11-01). The map is advisory input for
change-based selection; any source file it does not list keeps today's full-suite fallback.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import sys
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def function_body_lines(path: str) -> frozenset[int]:
    """Line numbers inside function/method bodies of `path` (backend-relative), excluding signatures."""
    try:
        tree = ast.parse((BACKEND_DIR / path).read_text(encoding='utf-8'))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return frozenset()
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0].lineno
            last = max(getattr(child, 'end_lineno', child.lineno) or child.lineno for child in node.body)
            lines.update(range(first, last + 1))
    return frozenset(lines)


def backend_relative(measured: str) -> str | None:
    try:
        rel = Path(measured).resolve().relative_to(BACKEND_DIR).as_posix()
    except ValueError:
        return None
    if not rel.endswith('.py') or rel.startswith(('tests/', '.venv/')) or '/site-packages/' in rel:
        return None
    return rel


def build(data_dir: Path) -> tuple[dict[str, list[str]], list[str], list[str]]:
    from coverage import CoverageData  # installed only in the coverage-map CI job

    files: dict[str, set[str]] = {}
    tests, unreadable = [], []
    for data_file in sorted(data_dir.glob('*.cov')):
        path_file = data_file.with_suffix('.path')
        if not path_file.exists():
            unreadable.append(data_file.name)
            continue
        test = path_file.read_text(encoding='utf-8').strip()
        data = CoverageData(basename=str(data_file))
        try:
            data.read()
        except Exception:  # a crashed test process leaves partial data; count it, never guess
            unreadable.append(test)
            continue
        tests.append(test)
        for measured in data.measured_files():
            rel = backend_relative(measured)
            if rel is None:
                continue
            executed = set(data.lines(measured) or ())
            if executed & function_body_lines(rel):
                files.setdefault(rel, set()).add(test)
    return {path: sorted(found) for path, found in sorted(files.items())}, sorted(tests), unreadable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sha', default='')
    args = parser.parse_args()
    files, tests, unreadable = build(args.data_dir)
    payload = {
        'schema_version': 1,
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'sha': args.sha,
        'tests': tests,
        'unreadable': unreadable,
        'files': files,
    }
    args.out.write_text(json.dumps(payload, sort_keys=True) + '\n', encoding='utf-8')
    sizes = sorted(len(v) for v in files.values())
    median = sizes[len(sizes) // 2] if sizes else 0
    print(
        f'coverage map: {len(tests)} tests, {len(files)} source files, median tests per file {median}, '
        f'unreadable {len(unreadable)}'
    )
    return 1 if not tests else 0


if __name__ == '__main__':
    sys.exit(main())
