#!/usr/bin/env python3
"""Lint script to detect blocking I/O patterns in async code.

Scans Python files for patterns that block the event loop:
- requests.* in async functions
- sync httpx.get/post in async functions
- time.sleep() in async functions
- Thread().start() + .join() patterns

Usage:
    python scripts/lint_async_blockers.py [--strict] [paths...]

Exit codes:
    0 — no violations (or only warnings in non-strict mode)
    1 — violations found
"""

import argparse
import ast
import sys
from pathlib import Path

SKIP_DIRS = {'__pycache__', '.git', 'node_modules', 'venv', '.venv', 'testing'}
SKIP_FILES = {'test_', 'conftest.py'}


class AsyncBlockerVisitor(ast.NodeVisitor):
    """AST visitor that detects blocking patterns inside async functions."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.violations = []
        self._in_async = False
        self._thread_join_lines: list[int] = []

    def visit_AsyncFunctionDef(self, node):
        old = self._in_async
        self._in_async = True
        self.generic_visit(node)
        self._in_async = old

    def visit_FunctionDef(self, node):
        old = self._in_async
        self._in_async = False
        self.generic_visit(node)
        self._in_async = old

    def visit_Call(self, node):
        if self._in_async:
            call_str = _get_call_name(node)
            if call_str:
                # requests.post/get/put/delete/patch/head
                if call_str.startswith('requests.') and call_str.split('.')[1] in (
                    'get',
                    'post',
                    'put',
                    'delete',
                    'patch',
                    'head',
                    'request',
                ):
                    self.violations.append(
                        (node.lineno, f'blocking {call_str}() in async function — use httpx.AsyncClient')
                    )
                # time.sleep
                elif call_str == 'time.sleep':
                    self.violations.append((node.lineno, 'time.sleep() in async function — use asyncio.sleep()'))
                # sync httpx.get/post
                elif call_str.startswith('httpx.') and call_str.split('.')[1] in ('get', 'post', 'put', 'delete'):
                    self.violations.append(
                        (node.lineno, f'sync {call_str}() in async function — use httpx.AsyncClient')
                    )
            # Thread().start() + .join() — detect .join() on any call chain containing Thread
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'join':
                self._thread_join_lines.append(node.lineno)
            # Detect Thread(...).start() pattern
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'start':
                inner = node.func.value
                if isinstance(inner, ast.Call):
                    inner_name = _get_call_name(inner)
                    if inner_name in ('Thread', 'threading.Thread'):
                        self.violations.append(
                            (node.lineno, 'Thread().start() in async function — use run_in_executor()')
                        )
        self.generic_visit(node)


def _get_call_name(node: ast.Call) -> str:
    """Extract dotted name from a Call node (e.g., 'requests.post')."""
    if isinstance(node.func, ast.Attribute):
        value = node.func.value
        if isinstance(value, ast.Name):
            return f'{value.id}.{node.func.attr}'
    elif isinstance(node.func, ast.Name):
        return node.func.id
    return ''


def scan_file(filepath: Path) -> list:
    try:
        source = filepath.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    visitor = AsyncBlockerVisitor(str(filepath))
    visitor.visit(tree)
    return visitor.violations


def main():
    parser = argparse.ArgumentParser(description='Detect blocking I/O in async Python code')
    parser.add_argument('paths', nargs='*', default=['.'], help='Files or directories to scan')
    parser.add_argument('--strict', action='store_true', help='Treat all violations as errors')
    args = parser.parse_args()

    all_violations = []

    for path_str in args.paths:
        path = Path(path_str)
        if path.is_file() and path.suffix == '.py':
            violations = scan_file(path)
            for line, msg in violations:
                all_violations.append((path, line, msg))
        elif path.is_dir():
            for py_file in sorted(path.rglob('*.py')):
                # Skip test files and excluded dirs
                if any(skip in py_file.parts for skip in SKIP_DIRS):
                    continue
                if any(py_file.name.startswith(skip) for skip in SKIP_FILES):
                    continue
                violations = scan_file(py_file)
                for line, msg in violations:
                    all_violations.append((py_file, line, msg))

    if all_violations:
        print(f'\n{len(all_violations)} async-blocking violation(s) found:\n')
        for filepath, line, msg in all_violations:
            print(f'  {filepath}:{line}: {msg}')
        print()
        if args.strict:
            return 1
    else:
        print('No async-blocking violations found.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
