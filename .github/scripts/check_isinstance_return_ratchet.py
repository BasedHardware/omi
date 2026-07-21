#!/usr/bin/env python3
"""Reject new assigned-call ``isinstance``-then-return flow control."""

import argparse
import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOT = Path('backend/utils/memory')
DEFAULT_BASELINE = Path('.github/scripts/isinstance_return_ratchet_baseline.json')
_FLOW_CONTROL_TYPE_SUFFIXES = ('Response', 'Result')


def _assigned_call_name(statement: ast.stmt) -> str | None:
    if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
        return None
    target = statement.targets[0]
    if not isinstance(target, ast.Name) or not isinstance(statement.value, ast.Call):
        return None
    return target.id


def _is_flow_control_type(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id.endswith(_FLOW_CONTROL_TYPE_SUFFIXES)


def _is_return_guard(statement: ast.stmt, name: str) -> bool:
    if not isinstance(statement, ast.If) or statement.orelse or len(statement.body) != 1:
        return False
    condition = statement.test
    if (
        not isinstance(condition, ast.Call)
        or not isinstance(condition.func, ast.Name)
        or condition.func.id != 'isinstance'
    ):
        return False
    if (
        len(condition.args) != 2
        or not isinstance(condition.args[0], ast.Name)
        or condition.args[0].id != name
        or not _is_flow_control_type(condition.args[1])
    ):
        return False
    returned = statement.body[0]
    return isinstance(returned, ast.Return) and isinstance(returned.value, ast.Name) and returned.value.id == name


class _FlowControlVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.count = 0

    def _visit_statement_list(self, statements: list[ast.stmt]) -> None:
        for previous, current in zip(statements, statements[1:]):
            name = _assigned_call_name(previous)
            if name is not None and _is_return_guard(current, name):
                self.count += 1
        for statement in statements:
            self.visit(statement)

    def visit_Module(self, node: ast.Module) -> None:
        self._visit_statement_list(node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_statement_list(node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_statement_list(node.body)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_statement_list(node.body)

    def visit_If(self, node: ast.If) -> None:
        self._visit_statement_list(node.body)
        self._visit_statement_list(node.orelse)

    def visit_For(self, node: ast.For) -> None:
        self._visit_statement_list(node.body)
        self._visit_statement_list(node.orelse)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_statement_list(node.body)
        self._visit_statement_list(node.orelse)

    def visit_While(self, node: ast.While) -> None:
        self._visit_statement_list(node.body)
        self._visit_statement_list(node.orelse)

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_statement_list(node.body)
        self._visit_statement_list(node.orelse)
        self._visit_statement_list(node.finalbody)
        for handler in node.handlers:
            self._visit_statement_list(handler.body)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self._visit_statement_list(node.body)
        self._visit_statement_list(node.orelse)
        self._visit_statement_list(node.finalbody)
        for handler in node.handlers:
            self._visit_statement_list(handler.body)

    def visit_With(self, node: ast.With) -> None:
        self._visit_statement_list(node.body)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_statement_list(node.body)

    def visit_Match(self, node: ast.Match) -> None:
        for case in node.cases:
            self._visit_statement_list(case.body)


def count_flow_control(source: str, filename: str = '<unknown>') -> int:
    visitor = _FlowControlVisitor()
    visitor.visit(ast.parse(source, filename=filename))
    return visitor.count


def collect_counts(repository_root: Path, scan_root: Path) -> dict[str, int]:
    root = repository_root / scan_root
    counts = {}
    for path in sorted(root.rglob('*.py')):
        count = count_flow_control(path.read_text(encoding='utf-8'), str(path))
        if count:
            counts[path.relative_to(repository_root).as_posix()] = count
    return counts


def load_baseline(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, int) for key, value in payload.items()
    ):
        raise ValueError(f'baseline must be a JSON object of string paths to integer counts: {path}')
    return payload


def violations(counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    errors = []
    for path, count in sorted(counts.items()):
        allowed = baseline.get(path, 0)
        if count > allowed:
            errors.append(f'{path}: found {count}, baseline allows {allowed}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPOSITORY_ROOT)
    parser.add_argument('--scan-root', type=Path, default=DEFAULT_SCAN_ROOT)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args()

    repository_root = args.root.resolve()
    baseline_path = args.baseline if args.baseline.is_absolute() else repository_root / args.baseline
    errors = violations(collect_counts(repository_root, args.scan_root), load_baseline(baseline_path))
    if not errors:
        return 0
    print('FAIL: assigned-call isinstance-return flow control increased:')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
